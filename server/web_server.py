"""config-map 로컬 HTTP 서버 (F6). 쓰기는 상태 파일과 /api/save 뿐이다."""

import sys

if sys.version_info < (3, 11):
    sys.stderr.write(
        "config-map requires Python 3.11 or newer (found %s).\n"
        "Install it from https://www.python.org/downloads/ and run"
        " /config-map again in a new terminal.\n" % sys.version.split()[0])
    sys.exit(2)

import argparse
import json
import logging
import os
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import assist  # noqa: E402
import core  # noqa: E402

VERSION = "0.7.0"
MAX_BODY = 1 << 20  # POST 본문 상한 1 MiB
PORT_TRIES = 20
LOCK_WAIT = 3.0  # 잠금 대기 상한(초). 넘으면 stale lock으로 본다
UI = Path(__file__).resolve().parent / "ui" / "index.html"
UI_DIR = UI.parent
# 정적 서빙 대상은 이 둘뿐. index.html은 `/`로만 나간다 (`/ui/index.html`은 404)
STATIC_TYPES = {".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8"}

log = logging.getLogger("config-map.web")

# ponytail: 직전 스캔 결과와 허용 경로 집합을 모듈 전역 + 락 하나로 보호한다.
# 서버 인스턴스가 프로세스당 하나뿐이라 이걸로 충분. 다중 서버가 필요해지면 인스턴스 속성으로.
_LOCK = threading.Lock()
_scan: dict | None = None
_allowed: set = set()
_readonly: set = set()


def state_path() -> Path:
    return core.home() / ".claude" / "config-map" / "server.json"


def _norm(value: str) -> str:
    """요청 경로 정규화. `..`·심볼릭 링크·상대 경로를 전부 편 뒤 슬래시 표기."""
    return Path(value).resolve().as_posix()


def _allowed_paths(scan: dict) -> set:
    """API 계약이 열거한 위치의 파일 경로 집합. 여기 없는 경로는 읽지 않는다."""
    out = set()

    def add(entry):
        if isinstance(entry, dict) and entry.get("path"):
            out.add(entry["path"])

    def add_all(container, *keys):
        for k in keys:
            for e in container.get(k) or []:
                add(e)

    g = scan.get("global") or {}
    add(g.get("claude_md"))
    add_all(g, "rules", "skills", "agents", "commands")
    for e in (g.get("settings") or {}).values():
        add(e)
    for p in scan.get("projects") or []:
        add_all(p, "claude_md", "rules", "skills", "agents", "commands")
        for e in (p.get("settings") or {}).values():
            add(e)
    out |= _readonly_paths(scan)
    return out


def _readonly_paths(scan: dict) -> set:
    """플러그인 소속 파일. 읽기는 되지만 저장은 막는다 (PRD §9-2)."""
    out = set()
    for pl in scan.get("plugins") or []:
        m = pl.get("manifest")
        if isinstance(m, dict) and m.get("path"):
            out.add(m["path"])
        for k in ("skills", "commands"):
            for e in pl.get(k) or []:
                if isinstance(e, dict) and e.get("path"):
                    out.add(e["path"])
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "config-map/" + VERSION

    def log_message(self, fmt, *args):  # 요청 로그는 INFO 아래로 (PRD 로깅 기본 INFO)
        log.debug("%s %s", self.address_string(), fmt % args)

    # --- 응답 헬퍼 ---

    def _send(self, code: int, body: bytes, ctype: str, cache: str | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if cache:
            self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _err(self, code: int, message: str):
        self._json(code, {"error": message})

    # --- 라우팅 ---

    def do_GET(self):
        try:
            self._get()
        except Exception:
            log.exception("GET %s failed", self.path)
            self._err(500, "internal error")

    def do_POST(self):
        try:
            self._post()
        except Exception:
            log.exception("POST %s failed", self.path)
            self._err(500, "internal error")

    def _get(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/":
            return self._index()
        if u.path == "/api/ping":
            return self._json(200, {"ok": True, "pid": os.getpid(), "version": VERSION})
        if u.path == "/api/scan":
            return self._scan()
        if u.path == "/api/file":
            return self._file((q.get("path") or [""])[0])
        if u.path == "/api/effective":
            return self._effective((q.get("project") or [""])[0])
        if u.path == "/api/sections":
            return self._sections((q.get("path") or [""])[0])
        if u.path == "/api/rules":
            return self._rules((q.get("project") or [""])[0])
        if u.path == "/api/assist":
            return self._assist_status((q.get("id") or [""])[0])
        if u.path == "/api/compare":
            return self._compare((q.get("title") or [""])[0])
        if u.path.startswith("/ui/"):
            return self._static(unquote(u.path[len("/ui/"):]))
        self._err(404, "not found")

    def _post(self):
        origin = self.headers.get("Origin")
        if origin and origin not in self._own_origins():
            return self._err(403, "forbidden origin")
        path = urlparse(self.path).path
        if path == "/api/shutdown":
            self._json(200, {"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        handlers = {"/api/validate": self._validate, "/api/save": self._save,
                    "/api/save-range": self._save_range, "/api/toggle": self._toggle,
                    "/api/assist": self._assist_start,
                    "/api/assist-cancel": self._assist_cancel}
        if path in handlers:
            body = self._body()
            if body is None:
                return
            return handlers[path](body)
        self._err(404, "not found")

    def _body(self) -> dict | None:
        """JSON 본문 → dict. 상한 초과·파싱 실패면 응답까지 보내고 None."""
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = -1
        if n < 0:
            self._err(400, "invalid body")
            return None
        if n > MAX_BODY:
            # ponytail: 응답 전에 본문을 버려 읽는다. 안 읽으면 클라이언트가 413 대신
            # 연결 끊김을 본다. 32 MiB까지만 흘려보내고 그 위는 그냥 끊는다.
            remaining = min(n, 32 << 20)
            while remaining > 0:
                chunk = self.rfile.read(min(remaining, 1 << 16))
                if not chunk:
                    break
                remaining -= len(chunk)
            self._err(413, "body too large")
            return None
        try:
            body = json.loads(self.rfile.read(n).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            self._err(400, "invalid json")
            return None
        if not isinstance(body, dict):
            self._err(400, "invalid json")
            return None
        return body

    def _target(self, raw) -> str | None:
        """쓰기·검증 대상 경로 검사. 실패면 응답까지 보내고 None."""
        if not isinstance(raw, str) or not raw:
            self._err(400, "path required")
            return None
        with _LOCK:
            scanned = _scan is not None
            allowed, readonly = _allowed, _readonly
        if not scanned:
            self._err(409, "scan first")
            return None
        try:
            path = _norm(raw)
        except (OSError, ValueError):
            self._err(404, "not in scan result")
            return None
        if path not in allowed:
            self._err(404, "not in scan result")
            return None
        if path in readonly:
            self._err(403, "plugin files are read-only")
            return None
        return path

    def _own_origins(self) -> set:
        host, port = self.server.server_address[:2]
        return {f"http://127.0.0.1:{port}", f"http://localhost:{port}", f"http://{host}:{port}"}

    # --- 엔드포인트 ---

    def _index(self):
        # ponytail: 매 요청 디스크에서 읽는다. UI 수정 후 새로고침만 하면 되고, 단일 사용자라 캐시가 무의미.
        try:
            body = UI.read_bytes()
        except OSError:
            return self._err(503, "UI not built")
        self._send(200, body, "text/html; charset=utf-8")

    def _static(self, rel: str):
        """`/ui/<상대경로>` → server/ui 아래의 .css/.js 파일. 벗어나면 전부 404."""
        # ponytail: _index와 같이 매 요청 디스크에서 읽고 no-store. 단일 사용자 개발 도구라 캐시가 무의미.
        root = UI_DIR.resolve()
        try:
            if "\x00" in rel:  # resolve() 동작이 플랫폼마다 달라 먼저 막는다
                raise ValueError(rel)
            target = (root / rel).resolve()
        except (OSError, ValueError):
            return self._err(404, "not found")
        ctype = STATIC_TYPES.get(target.suffix)
        if ctype is None or not target.is_relative_to(root):
            return self._err(404, "not found")
        try:
            body = target.read_bytes()
        except OSError:  # 없는 파일·디렉터리·권한 — 존재 여부를 알리지 않고 전부 404
            return self._err(404, "not found")
        self._send(200, body, ctype, cache="no-store")

    def _scan(self):
        result = core.scan()
        with _LOCK:
            global _scan, _allowed, _readonly
            _scan = result
            _allowed = _allowed_paths(result)
            _readonly = _readonly_paths(result)
        self._json(200, result)

    # ponytail: resolve와 open 사이 심링크 교체는 방어하지 않음 — 127.0.0.1 전용·본인 파일 읽기 도구. 필요 시 os.open(O_NOFOLLOW)+fstat 비교로 교체
    def _readable(self, raw: str) -> str | None:
        """읽기 대상 경로 검사(스캔 전 409 / 허용 밖 404). 실패면 응답까지 보내고 None."""
        if not raw:
            self._err(400, "path required")
            return None
        with _LOCK:
            scanned = _scan is not None
            allowed = _allowed
        if not scanned:
            self._err(409, "scan first")
            return None
        try:
            path = _norm(raw)
        except (OSError, ValueError):
            self._err(404, "not found")
            return None
        if path not in allowed:
            self._err(404, "not in scan result")
            return None
        return path

    def _file(self, raw: str):
        path = self._readable(raw)
        if path is None:
            return
        meta = core.read_text(path)
        if meta is None:
            return self._err(404, "not found")
        if "error" in meta:
            return self._err(500, meta["error"])
        out = {"path": path, **meta}
        if path.lower().endswith(".md"):  # 별도 요청 없이 접기가 되도록 같이 실어 준다
            out["sections"] = core.parse_sections(meta["text"])
        self._json(200, out)

    def _sections(self, raw: str):
        path = self._readable(raw)
        if path is None:
            return
        if not path.lower().endswith(".md"):
            return self._err(400, "not markdown")
        meta = core.read_text(path)
        if meta is None:
            return self._err(404, "not found")
        if "error" in meta:
            return self._err(500, meta["error"])
        self._json(200, {"path": path, "mtime": meta["mtime"],
                         "sections": core.parse_sections(meta["text"])})

    def _rules(self, raw: str):
        project = self._project(raw)
        if project is None:
            return
        files = []
        for f in core.effective_rules(project):
            e = dict(f, sections=[])
            meta = core.read_text(f["path"])
            if meta is None:
                e["error"] = "not found"
            elif "error" in meta:
                e["error"] = meta["error"]
            else:
                e["sections"] = core.parse_sections(meta["text"])
            files.append(e)
        self._json(200, {"files": files, "conflicts": core.section_conflicts(files)})

    def _compare(self, raw: str):
        if not raw.strip():
            return self._err(400, "title required")
        with _LOCK:
            scan = _scan
        if scan is None:
            return self._err(409, "scan first")
        self._json(200, {"title": raw.strip(),
                         "matches": core.compare_sections(scan, raw)})

    def _validate(self, body: dict):
        text = body.get("text")
        if not isinstance(text, str):
            return self._err(400, "text required")
        path = self._target(body.get("path"))
        if path is None:
            return
        self._json(200, {"issues": core.validate(path, text)})

    def _save(self, body: dict):
        text, mtime = body.get("text"), body.get("mtime")
        if not isinstance(text, str) or isinstance(mtime, bool)                 or not isinstance(mtime, (int, float)):
            return self._err(400, "text and mtime required")
        path = self._target(body.get("path"))
        if path is None:
            return
        try:
            r = core.save(path, text, mtime)
        except FileNotFoundError:
            return self._err(404, "not found")
        except OSError as e:
            log.warning("save failed %s: %s", path, e)
            return self._err(500, "save failed")
        if r.get("conflict"):
            return self._json(409, {"error": "modified on disk", "mtime": r["mtime"]})
        if any(i["level"] == "error" for i in r["issues"]):
            return self._json(422, {"error": "validation failed", "issues": r["issues"]})
        out = {"path": path, "mtime": r["mtime"], "size": r["size"],
               "backup": r["backup"], "issues": r["issues"]}
        if path.lower().endswith(".md"):
            out["sections"] = core.parse_sections(text)
        self._json(200, out)

    def _save_range(self, body: dict):
        start, end = body.get("start"), body.get("end")
        text, mtime = body.get("text"), body.get("mtime")
        # ponytail: 본문 형태 오류는 전부 한 문자열로 — UI는 어차피 같은 처리를 한다.
        # bool은 int의 하위형이라 따로 막는다.
        if (isinstance(start, bool) or isinstance(end, bool) or isinstance(mtime, bool)
                or not isinstance(start, int) or not isinstance(end, int)
                or not isinstance(mtime, (int, float))
                or start < 0 or start > end
                or not isinstance(text, str) or text == ""):
            return self._err(400, "invalid range")
        path = self._target(body.get("path"))
        if path is None:
            return
        try:
            r = core.replace_range(path, start, end, text, mtime)
        except FileNotFoundError:
            return self._err(404, "not found")
        except OSError as e:
            log.warning("save-range failed %s: %s", path, e)
            return self._err(500, "save failed")
        if r.get("bad_range"):
            return self._err(400, "invalid range")
        if r.get("conflict"):
            return self._json(409, {"error": "modified on disk", "mtime": r["mtime"]})
        if any(i["level"] == "error" for i in r["issues"]):
            return self._json(422, {"error": "validation failed", "issues": r["issues"]})
        self._json(200, {"path": path, "mtime": r["mtime"], "size": r["size"],
                         "backup": r["backup"], "issues": r["issues"],
                         "sections": r["sections"]})

    def _toggle(self, body: dict):
        with _LOCK:
            scanned = _scan is not None
            projects = (_scan or {}).get("projects") or []
        if not scanned:
            return self._err(409, "scan first")

        raw = body.get("project")
        try:
            project = _norm(raw) if isinstance(raw, str) and raw else None
        except (OSError, ValueError):
            project = None
        if project is None or not any(p.get("path") == project and p.get("exists")
                                      for p in projects):
            return self._err(404, "unknown project")

        section, target = body.get("section"), body.get("target") or "settings.local.json"
        key, value = body.get("key"), body.get("value")
        if not isinstance(section, str) or section not in core.TOGGLE_SECTIONS:
            return self._err(400, "invalid section")
        if not isinstance(target, str) or target not in core.TOGGLE_TARGETS:
            return self._err(400, "invalid target")
        if not isinstance(key, str) or not key.strip():
            return self._err(400, "invalid key")
        # bool은 int의 하위형이라 타입을 먼저 못 박는다 (0/1이 false/true로 통과하지 않게)
        typed = isinstance(value, bool) if section == "enabledPlugins" else isinstance(value, str)
        if not typed or value not in core.TOGGLE_SECTIONS[section]:
            return self._err(400, "invalid value")

        try:
            r = core.toggle(project, section, key, value, target)
        except OSError as e:
            log.warning("toggle failed %s: %s", project, e)
            return self._err(500, "save failed")
        if r.get("issues"):
            return self._json(422, {"error": "validation failed", "issues": r["issues"]})
        with _LOCK:  # 새로 만든 파일도 다음 /api/file에서 읽히게 (UI는 어차피 재스캔한다)
            _allowed.add(r["path"])
        self._json(200, {"path": r["path"], "created": r["created"], "backup": r["backup"],
                         "section": section, "key": key, "value": r["value"]})

    # --- F9 편집 도우미 (파일을 읽지도 쓰지도 않는다) ---

    def _assist_start(self, body: dict):
        path, text = body.get("path"), body.get("text")
        instruction, model, range_ = body.get("instruction"), body.get("model"), body.get("range")
        if not isinstance(path, str) or not path or len(path) > 4096:
            return self._err(400, "path required")
        if not isinstance(text, str):
            return self._err(400, "text required")
        if not isinstance(instruction, str) or not instruction.strip():
            return self._err(400, "instruction required")
        if model is not None and model not in assist.MODELS:
            return self._err(400, "invalid model")
        if range_ is not None:
            if (not isinstance(range_, dict)
                    or isinstance(range_.get("start"), bool)
                    or isinstance(range_.get("end"), bool)
                    or not isinstance(range_.get("start"), int)
                    or not isinstance(range_.get("end"), int)):
                return self._err(400, "invalid range")
        if not assist.cli_path():
            return self._err(503, "claude CLI not found")
        try:
            job_id = assist.start(text, instruction, path, range_, model)
        except RuntimeError as e:
            if str(e) == "busy":
                return self._err(429, "busy")
            return self._err(503, "claude CLI not found")
        self._json(202, {"id": job_id})

    def _assist_status(self, raw: str):
        job = assist.status(raw) if raw else None
        if job is None:
            return self._err(404, "unknown job")
        self._json(200, job)

    def _assist_cancel(self, body: dict):
        job_id = body.get("id")
        if not isinstance(job_id, str) or not job_id:
            return self._err(400, "id required")
        if not assist.cancel(job_id):
            return self._err(404, "unknown job")
        self._json(200, {"ok": True})

    def _project(self, raw: str) -> dict | None:
        """스캔 결과의 프로젝트 항목. 실패면 응답까지 보내고 None."""
        if not raw:
            self._err(400, "project required")
            return None
        with _LOCK:
            projects = (_scan or {}).get("projects") or []
        try:
            path = _norm(raw)
        except (OSError, ValueError):
            path = None
        for p in projects:
            if p.get("path") == path:
                return p
        self._err(404, "unknown project")
        return None

    def _effective(self, raw: str):
        project = self._project(raw)
        if project is not None:
            self._json(200, core.effective_rules(project))


def live_url() -> str | None:
    """상태 파일이 가리키는 서버가 살아 있으면 그 URL, 아니면 None."""
    try:
        state = json.loads(state_path().read_text(encoding="utf-8"))
        url = state["url"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    try:
        with urllib.request.urlopen(url + "/api/ping", timeout=1) as r:
            return url if json.load(r).get("ok") else None
    except (OSError, urllib.error.URLError, ValueError, AttributeError):
        return None


def _acquire(lock: Path) -> bool:
    """기동 구간 직렬화용 프로세스 간 잠금. O_EXCL 생성으로 한 프로세스만 통과."""
    lock.parent.mkdir(parents=True, exist_ok=True)

    def create():
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return True
        except FileExistsError:
            return False

    deadline = time.monotonic() + LOCK_WAIT
    while not create():
        if time.monotonic() >= deadline:
            log.warning("잠금 파일이 %.1f초 넘게 남아 stale로 보고 제거: %s", LOCK_WAIT, lock)
            # ponytail: 두 프로세스가 동시에 deadline을 넘기면 서로의 잠금을 지울 수 있음 — 3초 창, 허용
            try:  # 잠금 주인이 죽은 경우 — 지우고 한 번만 다시 잡는다
                lock.unlink()
            except OSError:
                pass
            return create()
        time.sleep(0.1)
    return True


def bind(host: str, port: int) -> ThreadingHTTPServer | None:
    """port부터 +1 하며 최대 20회 시도. port=0이면 OS 임의 포트로 한 번만."""
    for p in range(port, port + (PORT_TRIES if port else 1)):
        httpd = ThreadingHTTPServer((host, p), Handler, bind_and_activate=False)
        httpd.daemon_threads = True
        # 기본 True면 Windows에서 사용 중인 포트를 가로챈다 — 자동 이동이 동작하려면 꺼야 한다
        httpd.allow_reuse_address = False
        try:
            httpd.server_bind()
            httpd.server_activate()
            return httpd
        except OSError as e:
            httpd.server_close()
            log.debug("port %d unavailable: %s", p, e)
    return None


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser(prog="config-map",
                                 description="claude-config-map local server")
    ap.add_argument("--port", type=int, default=8765,
                    help="Port to listen on. Moves to the next free port if taken. Default 8765")
    ap.add_argument("--no-browser", action="store_true",
                    help="Print the URL without opening a browser")
    ap.add_argument("--host", default="127.0.0.1", help="For testing. Default 127.0.0.1")
    args = ap.parse_args(argv)

    sf = state_path()
    lock = sf.with_suffix(".lock")
    if not _acquire(lock):
        sys.stderr.write(f"Could not acquire startup lock: {lock}\n")
        return 1
    try:  # 여기부터 server.json 쓰기까지가 동시 기동 직렬화 구간
        existing = live_url()
        if existing:
            print(existing, flush=True)
            if not args.no_browser:
                webbrowser.open(existing)
            return 0

        httpd = bind(args.host, args.port)
        if httpd is None:
            sys.stderr.write(f"Ports {args.port}..{args.port + PORT_TRIES - 1} are all in use."
                             f" Pass --port to choose another.\n")
            return 1

        url = "http://{}:{}".format(args.host, httpd.server_address[1])
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(json.dumps({"port": httpd.server_address[1], "pid": os.getpid(),
                                  "url": url}), encoding="utf-8")
    finally:
        try:
            lock.unlink()
        except OSError:
            pass
    log.info("serving %s", url)
    print(url, flush=True)  # 커맨드 파일이 이 첫 줄을 읽는다
    try:
        if not args.no_browser:  # 서빙과 병행 — 브라우저 기동이 느려도 ping 응답을 막지 않는다
            threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        try:  # 남의 상태 파일은 지우지 않는다 — 내 pid가 적혀 있을 때만
            if json.loads(sf.read_text(encoding="utf-8")).get("pid") == os.getpid():
                sf.unlink()
        except (OSError, ValueError):
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
