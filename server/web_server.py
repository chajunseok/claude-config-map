"""config-map 로컬 HTTP 서버 (F6). 읽기 전용 — 상태 파일 하나만 쓴다."""

import sys

if sys.version_info < (3, 11):
    sys.stderr.write(
        "config-map은 Python 3.11 이상이 필요합니다. 현재: %s\n"
        "https://www.python.org/downloads/ 에서 설치한 뒤 새 터미널에서"
        " /config-map 을 다시 실행하세요.\n" % sys.version.split()[0])
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
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core  # noqa: E402

VERSION = "0.1.0"
PORT_TRIES = 20
LOCK_WAIT = 3.0  # 잠금 대기 상한(초). 넘으면 stale lock으로 본다
UI = Path(__file__).resolve().parent / "ui" / "index.html"

log = logging.getLogger("config-map.web")

# ponytail: 직전 스캔 결과와 허용 경로 집합을 모듈 전역 + 락 하나로 보호한다.
# 서버 인스턴스가 프로세스당 하나뿐이라 이걸로 충분. 다중 서버가 필요해지면 인스턴스 속성으로.
_LOCK = threading.Lock()
_scan: dict | None = None
_allowed: set = set()


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
    for pl in scan.get("plugins") or []:
        add(pl.get("manifest"))
        add_all(pl, "skills", "commands")
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "config-map/" + VERSION

    def log_message(self, fmt, *args):  # 요청 로그는 INFO 아래로 (PRD 로깅 기본 INFO)
        log.debug("%s %s", self.address_string(), fmt % args)

    # --- 응답 헬퍼 ---

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
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
        self._err(404, "not found")

    def _post(self):
        if urlparse(self.path).path == "/api/shutdown":
            origin = self.headers.get("Origin")
            if origin and origin not in self._own_origins():
                return self._err(403, "forbidden origin")
            self._json(200, {"ok": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        self._err(404, "not found")

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

    def _scan(self):
        result = core.scan()
        with _LOCK:
            global _scan, _allowed
            _scan = result
            _allowed = _allowed_paths(result)
        self._json(200, result)

    # ponytail: resolve와 open 사이 심링크 교체는 방어하지 않음 — 127.0.0.1 전용·본인 파일 읽기 도구. 필요 시 os.open(O_NOFOLLOW)+fstat 비교로 교체
    def _file(self, raw: str):
        if not raw:
            return self._err(400, "path required")
        with _LOCK:
            scanned = _scan is not None
            allowed = _allowed
        if not scanned:
            return self._err(409, "scan first")
        try:
            path = _norm(raw)
        except (OSError, ValueError):
            return self._err(404, "not found")
        if path not in allowed:
            return self._err(404, "not in scan result")
        meta = core.read_text(path)
        if meta is None:
            return self._err(404, "not found")
        if "error" in meta:
            return self._err(500, meta["error"])
        self._json(200, {"path": path, **meta})

    def _effective(self, raw: str):
        if not raw:
            return self._err(400, "project required")
        with _LOCK:
            projects = (_scan or {}).get("projects") or []
        try:
            path = _norm(raw)
        except (OSError, ValueError):
            return self._err(404, "unknown project")
        for p in projects:
            if p.get("path") == path:
                return self._json(200, core.effective_rules(p))
        self._err(404, "unknown project")


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
    ap = argparse.ArgumentParser(prog="config-map", description="claude-config-map 로컬 서버")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--host", default="127.0.0.1", help="테스트용. 기본 127.0.0.1")
    args = ap.parse_args(argv)

    sf = state_path()
    lock = sf.with_suffix(".lock")
    if not _acquire(lock):
        sys.stderr.write(f"기동 잠금을 얻지 못했습니다: {lock}\n")
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
            sys.stderr.write(f"포트 {args.port}부터 {PORT_TRIES}개가 모두 사용 중입니다."
                             f" --port 로 다른 포트를 지정하세요.\n")
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
