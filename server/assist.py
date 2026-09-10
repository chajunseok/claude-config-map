"""F9. Markdown 편집 도우미 — 설치된 Claude Code CLI(`claude -p`)를 도구 없이 호출한다.

서버는 이 기능에서 어떤 파일도 읽거나 쓰지 않는다. 본문은 요청의 `text` 가 전부이고,
결과는 메모리 작업 저장소에만 남는다 (cwd 폴더 생성만 예외).
"""

import difflib
import json
import os
import secrets
import shutil
import subprocess
import threading
import time

from common import home, log

MODELS = ("sonnet", "opus", "haiku")
MAX_RUNNING = 3
MAX_JOBS = 100
TIMEOUT_S = 180
SYSTEM = ("You are a Markdown editor. Return ONLY the full revised Markdown text, "
          "with no code fences, no explanation, no preamble. Preserve every part the "
          "instruction does not ask to change, including headings, line order, and blank lines. "
          "Keep the language of the document.")

# ponytail: 작업 저장소는 모듈 전역 dict + 락 하나. 서버가 프로세스당 하나뿐이라 이걸로 충분.
_LOCK = threading.Lock()
_JOBS: dict = {}

_PUBLIC = ("id", "status", "started_at", "result", "diff", "changed",
           "error", "cost_usd", "duration_ms")


def cli_path() -> str | None:
    return shutil.which("claude")


def work_dir():
    """CLI 를 돌릴 작업 폴더. 프로젝트 CLAUDE.md 가 딸려 들어가지 않게 config-map 홈."""
    d = home() / ".claude" / "config-map"
    d.mkdir(parents=True, exist_ok=True)
    return d


def build_prompt(text: str, instruction: str, path: str, range_=None) -> str:
    lines = ["Document: %s" % path]
    if isinstance(range_, dict):
        title = range_.get("title") or ""
        start, end = range_.get("start"), range_.get("end")
        if isinstance(start, int) and isinstance(end, int):
            lines.append("Section: %s (L%d–L%d)" % (title, start + 1, end))
        else:
            lines.append("Section: %s" % title)
    lines += ["Instruction: %s" % instruction, "----- BODY -----", text]
    return "\n".join(lines)


def strip_fence(s: str) -> str:
    """응답 전체를 감싼 ``` 펜스만 벗긴다. 본문 안의 펜스는 건드리지 않는다."""
    body = s.strip("\n")
    lines = body.split("\n")
    if len(lines) < 2 or not lines[0].startswith("```") or lines[-1].strip() != "```":
        return s
    if "```" in lines[0][3:]:  # ```x``` 한 줄짜리
        return s
    out = "\n".join(lines[1:-1])
    return out + "\n" if s.endswith("\n") else out


def make_diff(orig: str, new: str) -> str:
    if orig == new:
        return ""
    return "\n".join(difflib.unified_diff(
        orig.splitlines(), new.splitlines(),
        fromfile="before", tofile="after", lineterm=""))


def _prune():
    """끝난 작업부터 오래된 순으로 잘라 MAX_JOBS 를 지킨다. 호출자가 _LOCK 을 쥔다."""
    if len(_JOBS) <= MAX_JOBS:
        return
    done = sorted((j for j in _JOBS.values() if j["status"] != "running"),
                  key=lambda j: j["started_at"])
    for j in done[:len(_JOBS) - MAX_JOBS]:
        _JOBS.pop(j["id"], None)


def _finish(job_id: str, **fields):
    """실행 중일 때만 결과를 쓴다. 취소된 작업의 상태는 덮어쓰지 않는다."""
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None or job["status"] != "running":
            return
        job.update(fields)
        job["ended"] = time.monotonic()


def _argv(cli: str, model) -> list:
    argv = [cli, "-p", "--tools", "", "--output-format", "json",
            "--no-session-persistence", "--system-prompt", SYSTEM]
    if model:
        argv += ["--model", model]
    return argv


def _parse(out: str, err: str, code: int, text: str) -> dict:
    """CLI stdout JSON → 완료 필드. 실패면 error."""
    try:
        data = json.loads(out)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        msg = (err or out or "").strip()[:300]
        return {"status": "error", "error": msg or "CLI 응답을 해석하지 못했습니다 (종료 코드 %d)" % code}
    result = data.get("result")
    if data.get("is_error") or data.get("subtype") != "success" or not isinstance(result, str):
        msg = result if isinstance(result, str) and result.strip() else (err or "").strip()
        return {"status": "error", "error": (msg or "CLI 오류").strip()[:300]}
    new = strip_fence(result)
    if "\r\n" in text:  # 원문 줄바꿈에 맞춘다
        new = new.replace("\r\n", "\n").replace("\n", "\r\n")
    return {"status": "done", "result": new, "changed": new != text,
            "diff": make_diff(text, new),
            "cost_usd": data.get("total_cost_usd"), "duration_ms": data.get("duration_ms")}


def _run(job_id: str, cli: str, prompt: str, text: str, model):
    try:
        proc = subprocess.Popen(
            _argv(cli, model), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
            cwd=os.fspath(work_dir()))
    except OSError as e:
        log.warning("assist %s: CLI 실행 실패: %s", job_id, e)
        return _finish(job_id, status="error", error="CLI 실행 실패: %s" % e)

    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None or job["status"] != "running":  # 시작 직후 취소
            proc.kill()
            return
        job["proc"] = proc

    try:
        out, err = proc.communicate(prompt, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        proc.kill()
        log.warning("assist %s: 시간 초과", job_id)
        return _finish(job_id, status="error", error="시간 초과 (%d초)" % TIMEOUT_S)
    except OSError as e:  # 취소로 파이프가 끊긴 경우 포함 — _finish 가 running 만 덮는다
        return _finish(job_id, status="error", error="CLI 통신 실패: %s" % e)

    fields = _parse(out or "", err or "", proc.returncode or 0, text)
    _finish(job_id, **fields)
    log.info("assist %s: %s", job_id, fields["status"])


def start(text: str, instruction: str, path: str, range_=None, model=None) -> str:
    """작업을 시작하고 id 를 돌려준다. 실행 중이 MAX_RUNNING 이상이면 RuntimeError("busy")."""
    cli = cli_path()
    if not cli:
        raise RuntimeError("cli not found")
    job_id = secrets.token_hex(6)
    with _LOCK:
        if sum(1 for j in _JOBS.values() if j["status"] == "running") >= MAX_RUNNING:
            raise RuntimeError("busy")
        _JOBS[job_id] = {"id": job_id, "status": "running", "started_at": time.time(),
                         "started": time.monotonic(), "ended": None, "proc": None}
        _prune()
    log.info("assist %s: 시작 (본문 %d자, 지시 %d자, model=%s)",
             job_id, len(text), len(instruction), model or "default")
    prompt = build_prompt(text, instruction, path, range_)
    threading.Thread(target=_run, args=(job_id, cli, prompt, text, model),
                     daemon=True).start()
    return job_id


def status(job_id: str) -> dict | None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return None
        end = job["ended"] if job["ended"] is not None else time.monotonic()
        out = {k: job[k] for k in _PUBLIC if job.get(k) is not None}
        out["id"], out["status"] = job["id"], job["status"]
        out["started_at"] = job["started_at"]
        out["elapsed_ms"] = int((end - job["started"]) * 1000)
        if job["status"] == "done":  # 계약상 필수 — changed=False 여도 내려간다
            out.setdefault("result", "")
            out.setdefault("diff", "")
            out["changed"] = bool(job.get("changed"))
        return out


def cancel(job_id: str) -> bool:
    """모르는 id → False. 실행 중이면 kill 후 cancelled, 이미 끝났으면 그대로 True."""
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return False
        if job["status"] != "running":
            return True
        job["status"] = "cancelled"
        job["ended"] = time.monotonic()
        proc = job.get("proc")
    if proc is not None:
        try:
            proc.kill()
        except OSError as e:
            log.debug("assist %s: kill 실패: %s", job_id, e)
    log.info("assist %s: 취소", job_id)
    return True
