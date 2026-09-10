import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core  # noqa: E402


def w(path: Path, text: str, newline="\n", bom=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = text.replace("\n", newline).encode("utf-8")
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + data)
    return path


class FakeHome(unittest.TestCase):
    """가짜 홈을 만들고 CLAUDE_CONFIG_MAP_HOME으로 주입. git/claude 호출은 막는다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "home"
        self.proj = Path(self.tmp.name) / "proj"

        w(self.home / ".claude" / "CLAUDE.md", "# global\n")
        w(self.home / ".claude" / "rules" / "r1.md", "# global rule\n")
        w(self.home / ".claude" / "settings.json", json.dumps({
            "hooks": {
                "SessionStart": [
                    {"matcher": "startup", "hooks": [{"type": "command", "command": "a"}]},
                    {"matcher": "*", "hooks": [{"type": "command", "command": "b"}]},
                ],
                "PreToolUse": [
                    {"matcher": "Grep", "hooks": [{"type": "command", "command": "c"}]},
                ],
            }
        }))
        w(self.home / ".claude" / "skills" / "s1" / "SKILL.md",
          "---\nname: s1\ndescription: d1\n---\nbody\n")

        w(self.proj / "CLAUDE.md", "# proj\n@./docs/extra.md\n@./missing.md\n", newline="\r\n")
        w(self.proj / "CLAUDE.local.md", "# local\n")
        w(self.proj / "docs" / "extra.md", "x\n")
        w(self.proj / ".claude" / "rules" / "a.md", "# proj rule\n")
        w(self.proj / "sub" / "CLAUDE.md", "# sub\n")
        w(self.proj / "node_modules" / "x" / "CLAUDE.md", "# excluded\n")
        deep = self.proj.joinpath(*[f"d{i}" for i in range(9)]) / "CLAUDE.md"
        w(deep, "# too deep\n")
        self.deep = deep

        self.missing = Path(self.tmp.name) / "gone"
        w(self.home / ".claude.json", json.dumps({
            "projects": {self.proj.as_posix(): {"mcpServers": {"pm": {"command": "x"}}},
                         self.missing.as_posix(): {}},
            "mcpServers": {"gm": {"command": "y"}},
        }))

        os.environ["CLAUDE_CONFIG_MAP_HOME"] = str(self.home)
        # 외부 프로세스 호출은 테스트에서 전부 실패시킨다 (git 없음 / claude 없음 환경)
        self.run_patch = mock.patch("core.subprocess.run", side_effect=OSError("no exe"))
        self.run_patch.start()

    def tearDown(self):
        self.run_patch.stop()
        os.environ.pop("CLAUDE_CONFIG_MAP_HOME", None)
        self.tmp.cleanup()


class TestFrontmatter(unittest.TestCase):
    def test_ok(self):
        fm = core.parse_frontmatter("---\nname: a\ndescription: b c\n---\nbody")
        self.assertEqual(fm, {"name": "a", "description": "b c"})

    def test_none(self):
        self.assertEqual(core.parse_frontmatter("# just markdown\n"), {})
        self.assertEqual(core.parse_frontmatter(""), {})

    def test_broken(self):
        # 닫는 --- 없음
        self.assertEqual(core.parse_frontmatter("---\nname: a\nbody without close"), {})
        # 콜론 없는 줄은 무시
        self.assertEqual(core.parse_frontmatter("---\nname: a\ngarbage\n---\n"), {"name": "a"})


class TestReadText(FakeHome):
    def test_crlf_and_bom(self):
        m = core.read_text(self.proj / "CLAUDE.md")
        self.assertTrue(m["crlf"])
        self.assertFalse(m["bom"])

        p = w(self.proj / "bom.md", "hi\n", bom=True)
        m2 = core.read_text(p)
        self.assertTrue(m2["bom"])
        self.assertFalse(m2["crlf"])
        self.assertEqual(m2["text"], "hi\n")

    def test_missing(self):
        self.assertIsNone(core.read_text(self.proj / "nope.md"))


class TestIterMd(FakeHome):
    def test_exclude_and_depth(self):
        found = {Path(p).as_posix() for p in core.iter_md(self.proj)}
        self.assertIn((self.proj / "CLAUDE.md").as_posix(), found)
        self.assertIn((self.proj / "sub" / "CLAUDE.md").as_posix(), found)
        self.assertIn((self.proj / "CLAUDE.local.md").as_posix(), found)
        self.assertNotIn((self.proj / "node_modules" / "x" / "CLAUDE.md").as_posix(), found)
        self.assertNotIn(self.deep.as_posix(), found)

    def test_dot_dirs_skipped(self):
        w(self.proj / ".cache" / "CLAUDE.md", "# dot\n")
        found = {Path(p).as_posix() for p in core.iter_md(self.proj)}
        self.assertNotIn((self.proj / ".cache" / "CLAUDE.md").as_posix(), found)

    def test_budget_truncates(self):
        files, trunc = core._walk_md(self.proj, budget=1)
        self.assertTrue(trunc)
        self.assertEqual(core.scan_project(self.proj)["truncated"], False)


class TestScan(FakeHome):
    def test_missing_project(self):
        projects = core.scan_projects()
        self.assertEqual(len(projects), 2)
        gone = [p for p in projects if not p.get("exists")]
        self.assertEqual(len(gone), 1)
        self.assertEqual(set(gone[0]), {"path", "exists"})

    def test_imports(self):
        proj = core.scan_project(self.proj)
        by_raw = {i["raw"]: i["exists"] for i in proj["imports"]}
        self.assertTrue(by_raw["./docs/extra.md"])
        self.assertFalse(by_raw["./missing.md"])

    def test_shared_false_without_git(self):
        proj = core.scan_project(self.proj)
        self.assertFalse(proj["git"])
        self.assertTrue(all(not e["shared"] for e in proj["claude_md"]))

    def test_effective_rules_order(self):
        rules = core.effective_rules(core.scan_project(self.proj))
        self.assertEqual([r["scope"] for r in rules],
                         ["global", "global-rules", "project", "project-local",
                          "project-rules", "subdir"])
        self.assertTrue(rules[-1]["lazy"])
        self.assertTrue(all(not r["lazy"] for r in rules[:-1]))
        self.assertTrue(rules[-1]["path"].endswith("sub/CLAUDE.md"))

    def test_mcp_sources(self):
        mcp = core.scan_mcp()
        self.assertIn(("gm", "global"), {(m["name"], m["source"]) for m in mcp})
        self.assertTrue(any(m["name"] == "pm" and m["source"].startswith("project:")
                            for m in mcp))

    def test_plugins_empty(self):
        self.assertEqual(core.scan_plugins(), [])

    def test_scan_full(self):
        d = core.scan()
        self.assertIsNone(d["claude_version"])
        self.assertEqual(len(d["projects"]), 2)
        self.assertEqual(d["home"], core._p(self.home))
        self.assertTrue(d["scanned_at"])
        json.dumps(d)  # JSON 직렬화 가능해야 한다

    def test_scan_survives_broken_settings(self):
        w(self.home / ".claude" / "settings.json", "{ not json")
        d = core.scan()
        self.assertIn("error", d["global"]["settings"]["settings.json"])
        self.assertEqual(d["hooks"], [])
        self.assertEqual(len(d["projects"]), 2)


class TestHookFlows(unittest.TestCase):
    def test_duplicate_star(self):
        flows = core.hook_flows([{"source": "global", "hooks": {
            "SessionStart": [
                {"matcher": "startup", "hooks": [{"type": "command", "command": "a"}]},
                {"matcher": "*", "hooks": [{"type": "command", "command": "b"}]},
            ],
            "PreToolUse": [
                {"matcher": "Grep", "hooks": [{"type": "command", "command": "c"}]},
            ],
        }}])
        ss = [f for f in flows if f["event"] == "SessionStart"]
        self.assertEqual(len(ss), 2)
        self.assertTrue(all(f["warn"] == "duplicate-star" for f in ss))
        pre = [f for f in flows if f["event"] == "PreToolUse"]
        self.assertNotIn("warn", pre[0])

    def test_star_only_no_warn(self):
        flows = core.hook_flows([{"source": "global", "hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": "a"}]}]}}])
        self.assertEqual(flows[0]["matcher"], "*")
        self.assertNotIn("warn", flows[0])

    def test_bad_shapes_skipped(self):
        self.assertEqual(core.hook_flows(None), [])
        self.assertEqual(core.hook_flows([{"source": "x", "hooks": "nope"}]), [])
        self.assertEqual(core.hook_flows([{"source": "x", "hooks": {"E": "nope"}}]), [])
        self.assertEqual(core.hook_flows([{"source": "x", "hooks": {"E": [{"matcher": "m"}]}}]), [])


if __name__ == "__main__":
    unittest.main()
