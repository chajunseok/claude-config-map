import io
import json
import sys
import tempfile
import threading
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
            code, body, _ = get(self.url + "/")
            self.assertEqual(code, 503)
            self.assertEqual(body, "UI not built")

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

    def test_stale_state_file_is_ignored(self):
        sf = web_server.state_path()
        sf.parent.mkdir(parents=True, exist_ok=True)
        sf.write_text(json.dumps({"port": 1, "pid": 1,
                                  "url": "http://127.0.0.1:1"}), encoding="utf-8")
        self.assertIsNone(web_server.live_url())


class TestVersionGuard(unittest.TestCase):
    """sys.version_info는 patch가 어려워 소스 배치만 검증한다 (가드가 import보다 먼저)."""

    def test_guard_precedes_other_imports(self):
        src = Path(web_server.__file__).read_text(encoding="utf-8")
        guard = src.index("sys.version_info < (3, 11)")
        self.assertLess(src.index("import sys"), guard)
        self.assertLess(guard, src.index("import argparse"))
        self.assertIn("https://www.python.org/downloads/", src[guard:guard + 400])
        self.assertIn("sys.exit(2)", src[guard:guard + 400])


if __name__ == "__main__":
    unittest.main()
