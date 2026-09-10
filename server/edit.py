"""F4 검증 · F5 저장 · F7 토글 — 파일을 쓰는 쪽."""

import hashlib
import json
import os
import re
import shlex
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from common import _expand, _p, home, log, parse_frontmatter, read_text
from scan import _imports_of_text, hook_flows

# --- F4 검증 -------------------------------------------------------------

# 첫 토큰이 이 확장자면 경로로 본다 (슬래시가 없는 `hook.py` 형태)
SCRIPT_SUFFIXES = frozenset({".py", ".sh", ".js", ".cmd", ".ps1"})
# 마크다운 상대 링크: `](./x)` `](../x)` 만. 절대 URL·앵커는 잡히지 않는다
_REL_LINK = re.compile(r"\]\((\.{1,2}/[^)\s]+)\)")


def _issue(level: str, rule: str, message: str, line=None) -> dict:
    return {"level": level, "rule": rule, "line": line, "message": message}


def _md_kind(p: Path) -> str | None:
    """frontmatter 규칙이 붙는 마크다운 종류. 그 외는 None."""
    if p.name == "SKILL.md":
        return "skill"
    parts = {x.lower() for x in p.parts[:-1]}
    if "agents" in parts:
        return "agent"
    if "commands" in parts:
        return "command"
    return None


def _settings_base(p: Path) -> Path:
    """settings 파일의 상대 경로 기준 디렉터리. 전역이면 `~/.claude`, 프로젝트면 루트."""
    c = home() / ".claude"
    if p.parent.resolve() == c.resolve():
        return c
    if p.parent.name == ".claude":
        return p.parent.parent
    return p.parent


def _command_path(cmd: str) -> str | None:
    """훅 명령의 첫 토큰이 '경로처럼 보이면' 그 토큰. 아니면 None.

    # ponytail: 셸 파싱을 흉내내지 않는다. 첫 토큰만 보고, `$`/`%`가 있으면
    # 환경변수 확장이 필요한 명령이라 검사 자체를 건너뛴다 (§11.4 — 실행하지 않는다).
    """
    try:
        tokens = shlex.split(cmd, posix=False)
    except ValueError:
        tokens = cmd.split()
    if not tokens:
        return None
    token = tokens[0].strip("'\"")
    if not token or "$" in token or "%" in token:
        return None
    if "/" in token or "\\" in token or Path(token).suffix.lower() in SCRIPT_SUFFIXES:
        return token
    return None


def _v3(p: Path, data: dict) -> list:
    out = []
    base = _settings_base(p)
    for flow in hook_flows([{"source": _p(p), "hooks": data.get("hooks")}]):
        for cmd in flow["commands"]:
            token = _command_path(cmd) if isinstance(cmd, str) else None
            if token is None:
                continue
            target = _expand(token)
            if not target.is_absolute():
                target = base / token
            if not target.exists():
                out.append(_issue("error", "V3",
                                  f"{flow['event']} 훅 명령의 파일이 없습니다: {token}"))
    return out


def _v6(p: Path, data: dict) -> list:
    flows = hook_flows([{"source": _p(p), "hooks": data.get("hooks")}])
    events = sorted({f["event"] for f in flows if f.get("warn") == "duplicate-star"})
    return [_issue("warn", "V6",
                   f"{e}: `*` 매처와 구체 매처가 함께 있어 훅이 중복 발화합니다")
            for e in events]


def _v4(p: Path, text: str) -> list:
    out = []
    for imp in _imports_of_text(text, p):
        if not imp["exists"]:
            out.append(_issue("error", "V4", f"@import 대상이 없습니다: {imp['raw']}",
                              imp["line"]))
    for no, line in enumerate(text.splitlines(), 1):
        for raw in _REL_LINK.findall(line):
            target = p.parent / raw.split("#", 1)[0]
            if not target.exists():
                out.append(_issue("error", "V4", f"링크 대상이 없습니다: {raw}", no))
    return out


def validate(path, text: str) -> list:
    """저장 전 검증. Issue 목록 (`error`가 하나라도 있으면 저장 차단)."""
    p = _expand(path)
    if p.suffix.lower() == ".json":
        try:
            data = json.loads(text)
        except ValueError as e:
            return [_issue("error", "V1", f"JSON 파싱 실패: {getattr(e, 'msg', e)}",
                           getattr(e, "lineno", None))]
        if not (p.name.startswith("settings") and isinstance(data, dict)):
            return []
        return _v3(p, data) + _v6(p, data)

    if p.suffix.lower() != ".md":
        return []
    out = []
    kind = _md_kind(p)
    if kind:
        fm = parse_frontmatter(text)
        # commands/*.md의 name은 파일명이 대신한다 (§F4 V2)
        need = ("description",) if kind == "command" else ("name", "description")
        missing = [k for k in need if not fm.get(k)]
        if missing:
            out.append(_issue("error", "V2",
                              "frontmatter 필수 키가 없습니다: " + ", ".join(missing)))
    return out + _v4(p, text)


# --- F5 저장 -------------------------------------------------------------

BACKUP_KEEP = 10


def backup_root() -> Path:
    return home() / ".claude" / "config-map" / "backups"


def _backup(path) -> str:
    """원본 바이트를 백업 폴더에 복사하고 최근 BACKUP_KEEP개만 남긴다.

    # ponytail: 파일당 폴더 이름은 정규 경로 sha1 앞 16자, 파일명은 UTC 타임스탬프.
    # 같은 마이크로초에 두 번 저장하면 덮어쓴다 — 단일 사용자 도구라 허용.
    """
    p = _expand(path)
    d = backup_root() / hashlib.sha1(_p(p).encode("utf-8")).hexdigest()[:16]
    d.mkdir(parents=True, exist_ok=True)
    dest = d / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f") + ".bak")
    shutil.copy2(p, dest)
    for old in sorted(d.glob("*.bak"))[:-BACKUP_KEEP]:
        try:
            old.unlink()
        except OSError as e:
            log.warning("백업 정리 실패 %s: %s", old, e)
    return dest.resolve().as_posix()


def _write_atomic(p: Path, data: bytes) -> None:
    """같은 디렉터리 임시 파일에 쓰고 os.replace로 갈아끼운다.

    실패하면 임시 파일을 지우고 예외를 그대로 올린다 — 원본은 손대지 않는다.
    """
    tmp = tempfile.NamedTemporaryFile(dir=p.parent, prefix=".config-map-", delete=False)
    try:
        tmp.write(data)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.replace(tmp.name, p)
    except BaseException:
        tmp.close()
        Path(tmp.name).unlink(missing_ok=True)
        raise


def save(path, text: str, expected_mtime=None) -> dict:
    """검증 → V7 mtime 비교 → 백업 → 원자적 쓰기.

    - 검증 error가 있으면 `{"issues": [...]}` 만 돌려주고 쓰지 않는다.
    - mtime이 어긋나면 `{"conflict": True, "mtime": 현재}`.
    - 성공하면 `{"mtime", "size", "backup", "issues"(warn만)}`.
    """
    p = _expand(path)
    issues = validate(p, text)
    if any(i["level"] == "error" for i in issues):
        return {"issues": issues}

    raw = p.read_bytes()  # 사라졌으면 FileNotFoundError를 그대로 올린다
    st = p.stat()
    if expected_mtime is not None and abs(st.st_mtime - float(expected_mtime)) > 1e-6:
        return {"conflict": True, "mtime": st.st_mtime}

    body = text.replace("\r\n", "\n")
    if b"\r\n" in raw:  # 원본 줄바꿈·BOM은 서버가 현재 파일에서 다시 판정한다
        body = body.replace("\n", "\r\n")
    data = body.encode("utf-8")
    if raw.startswith(b"\xef\xbb\xbf"):
        data = b"\xef\xbb\xbf" + data

    backup = _backup(p)
    _write_atomic(p, data)
    st = p.stat()
    return {"mtime": st.st_mtime, "size": st.st_size, "backup": backup,
            "issues": [i for i in issues if i["level"] != "error"]}


# --- F7 토글 -------------------------------------------------------------

# 섹션별 허용 값. 첫 값이 "기본값" — 이 값으로 토글하면 키를 지운다(기본 복원).
TOGGLE_SECTIONS = {
    "skillOverrides": ("on", "name-only", "user-invocable-only", "off"),
    "enabledPlugins": (True, False),
}
TOGGLE_TARGETS = ("settings.local.json", "settings.json")


def toggle(project_path, section: str, key: str, value,
           target: str = "settings.local.json") -> dict:
    """프로젝트 settings 파일의 skillOverrides/enabledPlugins 한 키를 설정한다.

    - 파일이 없으면 만든다(디렉터리 포함). 파싱 불가면 `{"issues": [V1]}` 만 돌려준다.
    - 기본값으로 토글하면 키를 지우고, 섹션이 비면 섹션도 지운다.
    - 반환 `{"path", "created", "backup", "value"}` (value는 저장값, 삭제면 None).

    # ponytail: 통째로 재직렬화한다(indent=2). 원본 들여쓰기·주석은 보존하지 않는다.
    # 범위 치환이 필요해지면 그때 파서를 붙인다 — 백업이 있으니 복구는 된다.
    """
    p = _expand(project_path) / ".claude" / target
    meta = read_text(p)
    created = meta is None
    crlf = bom = False
    data: dict = {}
    if meta is not None:
        if "error" in meta:
            return {"issues": [_issue("error", "V1", meta["error"])]}
        crlf, bom = meta["crlf"], meta["bom"]
        try:
            parsed = json.loads(meta["text"])
        except ValueError as e:
            return {"issues": [_issue("error", "V1", f"JSON 파싱 실패: {getattr(e, 'msg', e)}",
                                      getattr(e, "lineno", None))]}
        if not isinstance(parsed, dict):
            return {"issues": [_issue("error", "V1", "최상위가 객체가 아닙니다: "
                                      + type(parsed).__name__)]}
        data = parsed

    sec = data.get(section)
    if not isinstance(sec, dict):
        sec = {}
    data[section] = sec
    stored = None if value == TOGGLE_SECTIONS[section][0] else value
    if stored is None:
        sec.pop(key, None)
    else:
        sec[key] = stored
    if not sec:
        data.pop(section, None)

    body = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    if crlf:
        body = body.replace("\n", "\r\n")
    raw = body.encode("utf-8")
    if bom:
        raw = b"\xef\xbb\xbf" + raw

    backup = None
    if created:
        p.parent.mkdir(parents=True, exist_ok=True)
    else:
        backup = _backup(p)
    _write_atomic(p, raw)
    return {"path": _p(p), "created": created, "backup": backup, "value": stored}
