import ast
import io
import json
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import web_server  # noqa: E402


def get(url):
    """(status, body) — 4xx/5xx도 예외 대신 값으로 돌려준다."""
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return r.status, r.read().decode("utf-8"), r.headers.get("Content-Type")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8"), e.headers.get("Content-Type")


class ServerCase(unittest.TestCase):
    """임시 홈에 상태 파일을 격리하고, core.scan을 가짜 결과로 대체한 서버를 띄운다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.home = root / "home"
        (self.home / ".claude").mkdir(parents=True)
        env = mock.patch.dict("os.environ", {"CLAUDE_CONFIG_MAP_HOME": str(self.home)})
        env.start()
        self.addCleanup(env.stop)

        self.proj = root / "proj"
        self.allowed = self.proj / "CLAUDE.md"
        self.allowed.parent.mkdir(parents=True)
        self.allowed.write_bytes(b"# project rules\n")  # 줄바꿈 변환 없이 LF 고정
        self.outside = root / "secret.txt"
        self.outside.write_text("nope\n", encoding="utf-8")

        p = lambda f: Path(f).resolve().as_posix()  # noqa: E731
        self.proj_path = p(self.proj)
        self.fake_scan = {
            "scanned_at": "2026-09-10T00:00:00+00:00",
            "home": p(self.home),
            "claude_version": None,
            "global": {"claude_md": None, "rules": [], "settings": {},
                       "skills": [], "agents": [], "commands": []},
            "projects": [{
                "path": self.proj_path, "exists": True, "name": "proj",
                "coverage": "full", "git": False,
                "claude_md": [{"path": p(self.allowed), "name": "CLAUDE.md",
                               "scope": "root", "shared": False}],
                "rules": [], "settings": {},
                "skills": [], "agents": [], "commands": [],
            }],
            "plugins": [], "mcp": [], "hooks": [], "errors": [],
        }
        scan = mock.patch.object(web_server.core, "scan", return_value=self.fake_scan)
        scan.start()
        self.addCleanup(scan.stop)

        web_server._scan = None
        web_server._allowed = set()
        self.addCleanup(setattr, web_server, "_scan", None)

        self.httpd = web_server.bind("127.0.0.1", 0)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        self.url = "http://127.0.0.1:%d" % self.httpd.server_address[1]

    def scan(self):
        code, body, _ = get(self.url + "/api/scan")
        self.assertEqual(code, 200)
        return json.loads(body)



class TestEndpoints(ServerCase):
    def test_ping(self):
        code, body, ctype = get(self.url + "/api/ping")
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(body)["ok"])
        self.assertIn("application/json", ctype)

    def test_file_before_scan_is_409(self):
        code, body, _ = get(self.url + "/api/file?path=" + self.allowed.as_posix())
        self.assertEqual(code, 409)
        self.assertEqual(json.loads(body)["error"], "scan first")

    def test_scan_then_file(self):
        d = self.scan()
        self.assertEqual(len(d["projects"]), 1)

        code, body, _ = get(self.url + "/api/file?path=" + self.allowed.as_posix())
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)["text"], "# project rules\n")

        code, _, _ = get(self.url + "/api/file?path=" + self.outside.as_posix())
        self.assertEqual(code, 404)

    def test_file_traversal_is_404(self):
        self.scan()
        sneaky = (self.proj / ".." / "secret.txt").as_posix()
        code, _, _ = get(self.url + "/api/file?path=" + sneaky)
        self.assertEqual(code, 404)

    def test_effective_before_scan_is_404(self):
        code, body, _ = get(self.url + "/api/effective?project=" + self.proj_path)
        self.assertEqual(code, 404)
        self.assertEqual(json.loads(body)["error"], "unknown project")

    def test_effective(self):
        self.scan()
        code, body, _ = get(self.url + "/api/effective?project=" + self.proj_path)
        self.assertEqual(code, 200)
        rules = json.loads(body)
        self.assertIsInstance(rules, list)
        self.assertIn(Path(self.allowed).resolve().as_posix(),
                      [r["path"] for r in rules])

        code, _, _ = get(self.url + "/api/effective?project=" + self.outside.as_posix())
        self.assertEqual(code, 404)

    def test_index_missing_then_present(self):
        with mock.patch.object(web_server, "UI", Path(self.tmp.name) / "nope.html"):
            code, body, ctype = get(self.url + "/")
            self.assertEqual(code, 503)
            self.assertIn("application/json", ctype)
            self.assertEqual(json.loads(body)["error"], "UI not built")

        ui = Path(self.tmp.name) / "index.html"
        ui.write_text("<h1>hi</h1>", encoding="utf-8")
        with mock.patch.object(web_server, "UI", ui):
            code, body, ctype = get(self.url + "/")
            self.assertEqual(code, 200)
            self.assertIn("text/html", ctype)
            self.assertEqual(body, "<h1>hi</h1>")

    def test_shutdown_stops_server(self):
        req = urllib.request.Request(self.url + "/api/shutdown", method="POST")
        with urllib.request.urlopen(req, timeout=5) as r:
            self.assertEqual(r.status, 200)
            self.assertTrue(json.load(r)["ok"])
        self.thread.join(timeout=5)
        self.assertFalse(self.thread.is_alive())

    def test_second_start_reuses_live_instance(self):
        sf = web_server.state_path()
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(json.dumps({"port": self.httpd.server_address[1],
                                  "pid": 1, "url": self.url}), encoding="utf-8")
        out = io.StringIO()
        with redirect_stdout(out):
            rc = web_server.main(["--no-browser", "--port", "0"])
        self.assertEqual(rc, 0)
        self.assertEqual(out.getvalue().strip(), self.url)

    def test_handler_exception_is_500_json_and_server_survives(self):
        with mock.patch.object(web_server.core, "scan", side_effect=RuntimeError("boom")):
            code, body, ctype = get(self.url + "/api/scan")
        self.assertEqual(code, 500)
        self.assertIn("application/json", ctype)
        self.assertEqual(json.loads(body)["error"], "internal error")

        code, _, _ = get(self.url + "/api/ping")
        self.assertEqual(code, 200)

    def test_null_byte_in_path_is_400(self):
        self.scan()
        code, body, _ = get(self.url + "/api/file?path=" + self.allowed.as_posix() + "%00")
        self.assertEqual(code, 400)
        self.assertIn("bad path", json.loads(body)["error"])

        code, body, _ = get(self.url + "/api/effective?project=" + self.proj_path + "%00")
        self.assertEqual(code, 400)
        self.assertIn("bad path", json.loads(body)["error"])

    def _run_main(self):
        """별도 스레드에서 main 실행 → (thread, rc list, url). 상태 파일 생성까지 대기."""
        sf = web_server.state_path()
        rc = []
        t = threading.Thread(
            target=lambda: rc.append(web_server.main(["--no-browser", "--port", "0"])),
            daemon=True)
        t.start()
        deadline = time.time() + 5
        while not sf.exists() and time.time() < deadline:
            time.sleep(0.02)
        self.assertTrue(sf.exists(), "server.json이 생성되지 않았다")
        return t, rc, json.loads(sf.read_text(encoding="utf-8"))["url"]

    def test_main_end_to_end(self):
        sf = web_server.state_path()
        opened = []
        out = io.StringIO()
        with mock.patch.object(web_server.webbrowser, "open", opened.append),                 redirect_stdout(out):
            t, rc, url = self._run_main()
            req = urllib.request.Request(url + "/api/shutdown", method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                self.assertEqual(r.status, 200)
            t.join(timeout=5)
        self.assertFalse(t.is_alive())
        self.assertEqual(rc, [0])
        self.assertEqual(out.getvalue().strip(), url)
        self.assertEqual(opened, [])  # --no-browser
        self.assertFalse(sf.exists(), "종료 시 server.json이 삭제되지 않았다")

    def test_foreign_state_file_survives_shutdown(self):
        sf = web_server.state_path()
        with mock.patch.object(web_server.webbrowser, "open", lambda u: None),                 redirect_stdout(io.StringIO()):
            t, rc, url = self._run_main()
            sf.write_text(json.dumps({"port": 1, "pid": 999999,
                                      "url": "http://127.0.0.1:1"}), encoding="utf-8")
            req = urllib.request.Request(url + "/api/shutdown", method="POST")
            urllib.request.urlopen(req, timeout=5).close()
            t.join(timeout=5)
        self.assertEqual(rc, [0])
        self.assertTrue(sf.exists(), "다른 pid의 server.json을 지웠다")
        self.assertEqual(json.loads(sf.read_text(encoding="utf-8"))["pid"], 999999)

    def test_stale_state_file_is_ignored(self):
        sf = web_server.state_path()
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(json.dumps({"port": 1, "pid": 1,
                                  "url": "http://127.0.0.1:1"}), encoding="utf-8")
        self.assertIsNone(web_server.live_url())


class TestVersionGuard(unittest.TestCase):
    """sys.version_info는 patch가 어려워 소스 배치만 검증한다 (가드가 import보다 먼저)."""

    def test_guard_is_first_statement_after_import_sys(self):
        body = ast.parse(Path(web_server.__file__).read_text(encoding="utf-8")).body
        i = next(i for i, n in enumerate(body)
                 if isinstance(n, ast.Import) and any(a.name == "sys" for a in n.names))
        guard = body[i + 1]
        self.assertIsInstance(guard, ast.If)
        self.assertIn("version_info", ast.unparse(guard.test))
        src = ast.unparse(guard)
        self.assertIn("https://www.python.org/downloads/", src)
        self.assertIn("sys.exit(2)", src)


if __name__ == "__main__":
    unittest.main()
