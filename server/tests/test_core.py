import json
import os
import subprocess
import sys
import tempfile
import threading
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
        self.addCleanup(self.tmp.cleanup)
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
        self.write_registry({
            "projects": {self.proj.as_posix(): {"mcpServers": {"pm": {"command": "x"}}},
                         self.missing.as_posix(): {}},
            "mcpServers": {"gm": {"command": "y"}},
        })

        self.env = mock.patch.dict(os.environ,
                                   {"CLAUDE_CONFIG_MAP_HOME": str(self.home)})
        self.env.start()
        self.addCleanup(self.env.stop)

        # 외부 프로세스 호출은 기본적으로 전부 실패시킨다 (git 없음 / claude 없음 환경)
        self.run_patch = mock.patch("core.subprocess.run", side_effect=OSError("no exe"))
        self.run_patch.start()
        self.addCleanup(self.run_patch.stop)

        core._errors.clear()

    def write_registry(self, obj):
        w(self.home / ".claude.json", json.dumps(obj) if isinstance(obj, dict) else obj)


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

    def test_mtime_and_size(self):
        p = w(self.proj / "sized.md", "abcde\n")
        m = core.read_text(p)
        self.assertIsInstance(m["mtime"], float)
        self.assertEqual(m["size"], p.stat().st_size)
        self.assertEqual(m["size"], 6)

    def test_permission_denied_is_error(self):
        with mock.patch.object(Path, "read_bytes", side_effect=PermissionError("nope")):
            r = core.read_text(self.proj / "CLAUDE.md")
        self.assertIn("permission denied", r["error"])
        self.assertTrue(any("permission denied" in e["error"] for e in core.errors()))

    def test_tilde_expands_to_fake_home(self):
        self.assertEqual(core._p("~/x"), core._p(self.home / "x"))


class TestIterMd(FakeHome):
    def test_exclude_and_depth(self):
        found = {Path(p).as_posix() for p in core.iter_md(self.proj)}
        self.assertIn((self.proj / "CLAUDE.md").as_posix(), found)
        self.assertIn((self.proj / "sub" / "CLAUDE.md").as_posix(), found)
        self.assertIn((self.proj / "CLAUDE.local.md").as_posix(), found)
        self.assertNotIn((self.proj / "node_modules" / "x" / "CLAUDE.md").as_posix(), found)
        self.assertNotIn(self.deep.as_posix(), found)

    def test_dot_dirs_are_scanned(self):
        """PRD F1 제외 목록에 없는 점 디렉터리는 빠지지 않는다 (C7)."""
        w(self.proj / ".cache" / "CLAUDE.md", "# dot\n")
        found = {Path(p).as_posix() for p in core.iter_md(self.proj)}
        self.assertIn((self.proj / ".cache" / "CLAUDE.md").as_posix(), found)

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

    def test_imports_one_level_only(self):
        w(self.proj / "CLAUDE.md", "# proj\n@./b.md\n")
        w(self.proj / "b.md", "@./c.md\n")
        w(self.proj / "c.md", "leaf\n")
        raws = {i["raw"] for i in core.scan_project(self.proj)["imports"]}
        self.assertIn("./b.md", raws)
        self.assertNotIn("./c.md", raws)

    def test_shared_false_without_git(self):
        proj = core.scan_project(self.proj)
        self.assertFalse(proj["git"])
        self.assertTrue(all(not e["shared"] for e in proj["claude_md"]))

    def test_git_ls_files_nul_separated(self):
        r = mock.Mock(returncode=0, stdout="CLAUDE.md\0sub/CLAUDE.md\0")
        with mock.patch("core.subprocess.run", return_value=r) as m:
            proj = core.scan_project(self.proj)
        args = m.call_args.args[0]
        self.assertIn("-z", args)
        self.assertEqual(m.call_args.kwargs["timeout"], 2)
        self.assertTrue(proj["git"])
        shared = {e["path"]: e["shared"] for e in proj["claude_md"]}
        self.assertTrue(shared[core._p(self.proj / "CLAUDE.md")])
        self.assertTrue(shared[core._p(self.proj / "sub" / "CLAUDE.md")])
        self.assertFalse(shared[core._p(self.proj / "CLAUDE.local.md")])

    def test_git_ls_files_bytes_stdout(self):
        r = mock.Mock(returncode=0, stdout=b"CLAUDE.md\0sub/CLAUDE.md\0")
        with mock.patch("core.subprocess.run", return_value=r):
            proj = core.scan_project(self.proj)
        shared = {e["path"]: e["shared"] for e in proj["claude_md"]}
        self.assertTrue(shared[core._p(self.proj / "CLAUDE.md")])

    def test_git_timeout_means_not_shared(self):
        with mock.patch("core.subprocess.run",
                        side_effect=subprocess.TimeoutExpired("git", 2)):
            proj = core.scan_project(self.proj)
        self.assertFalse(proj["git"])
        self.assertTrue(all(not e["shared"] for e in proj["claude_md"]))

    def test_claude_version_ok(self):
        r = mock.Mock(returncode=0, stdout="2.1.267 (Claude Code)\n")
        with mock.patch("core.shutil.which", return_value="/usr/bin/claude"), \
                mock.patch("core.subprocess.run", return_value=r) as m:
            self.assertEqual(core._claude_version(), "2.1.267 (Claude Code)")
        self.assertEqual(m.call_args.kwargs["timeout"], 3)

    def test_claude_version_absent(self):
        with mock.patch("core.shutil.which", return_value=None):
            self.assertIsNone(core._claude_version())

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

    def test_plugin_without_install_path(self):
        p = core._scan_plugin("x@y", {"version": "1"})
        self.assertEqual(p, {"name": "x@y", "exists": False})
        self.assertEqual(core._scan_plugin("x@y", {"installPath": ""}),
                         {"name": "x@y", "exists": False})

    def test_scan_full(self):
        d = core.scan()
        self.assertIsNone(d["claude_version"])
        self.assertEqual(len(d["projects"]), 2)
        self.assertEqual(d["home"], core._p(self.home))
        self.assertEqual(d["errors"], [])
        self.assertTrue(d["scanned_at"])
        json.dumps(d)  # JSON 직렬화 가능해야 한다

    def test_hook_source_names_file(self):
        d = core.scan()
        self.assertTrue(all(f["source"] == "global:settings.json" for f in d["hooks"]))

    def test_scan_survives_broken_settings(self):
        w(self.home / ".claude" / "settings.json", "{ not json")
        d = core.scan()
        self.assertIn("error", d["global"]["settings"]["settings.json"])
        self.assertEqual(d["hooks"], [])
        self.assertEqual(len(d["projects"]), 2)
        self.assertTrue(any(e["path"].endswith(".claude/settings.json")
                            for e in d["errors"]))

    def test_scan_survives_broken_registry(self):
        self.write_registry("{ not json")
        d = core.scan()
        self.assertEqual(d["projects"], [])
        self.assertEqual(d["mcp"], [])
        self.assertTrue(any(e["path"] == core._p(self.home / ".claude.json")
                            for e in d["errors"]))

    def test_empty_json_is_error(self):
        w(self.home / ".claude" / "settings.local.json", "   \n")
        r = core._read_json(self.home / ".claude" / "settings.local.json")
        self.assertIn("error", r)

    def test_tilde_project_path(self):
        w(self.home / "proj2" / "CLAUDE.md", "# p2\n")
        self.write_registry({"projects": {"~/proj2": {}}})
        projects = core.scan_projects()
        self.assertEqual(len(projects), 1)
        self.assertTrue(projects[0]["exists"])
        self.assertEqual(projects[0]["path"], core._p(self.home / "proj2"))


class TestCoverage(FakeHome):
    def test_ancestor_is_root_only(self):
        a = Path(self.tmp.name) / "a"
        b = a / "b"
        w(a / "CLAUDE.md", "# a\n")
        w(a / "deep" / "CLAUDE.md", "# a-deep\n")
        w(b / "CLAUDE.md", "# b\n")
        w(b / "deep" / "CLAUDE.md", "# b-deep\n")
        self.write_registry({"projects": {a.as_posix(): {}, b.as_posix(): {}}})
        by_path = {p["path"]: p for p in core.scan_projects()}

        pa = by_path[core._p(a)]
        self.assertEqual(pa["coverage"], "root-only")
        self.assertEqual(pa["coverage_reason"], "ancestor")
        self.assertEqual({e["name"] for e in pa["claude_md"]}, {"CLAUDE.md"})

        pb = by_path[core._p(b)]
        self.assertEqual(pb["coverage"], "full")
        self.assertNotIn("coverage_reason", pb)
        self.assertIn(core._p(b / "deep" / "CLAUDE.md"),
                      {e["path"] for e in pb["claude_md"]})

    def test_home_is_root_only(self):
        w(self.home / "CLAUDE.md", "# home\n")
        w(self.home / "nested" / "CLAUDE.md", "# nested\n")
        self.write_registry({"projects": {self.home.as_posix(): {}}})
        p = core.scan_projects()[0]
        self.assertEqual(p["coverage"], "root-only")
        self.assertEqual(p["coverage_reason"], "home")
        self.assertEqual({e["name"] for e in p["claude_md"]}, {"CLAUDE.md"})

    def test_drive_root_is_root_only(self):
        anchor = Path(self.tmp.name).anchor
        cov, reason = core._coverage_of(core._p(anchor), {core._p(anchor)},
                                        core._p(self.home))
        self.assertEqual((cov, reason), ("root-only", "drive-root"))

    def test_normal_project_is_full(self):
        p = core.scan_projects()
        full = [x for x in p if x.get("exists")]
        self.assertEqual(full[0]["coverage"], "full")


class TestGitTrackedParallel(FakeHome):
    def test_called_once_per_project(self):
        p2 = Path(self.tmp.name) / "p2"
        p3 = Path(self.tmp.name) / "p3"
        for d in (p2, p3):
            w(d / "CLAUDE.md", "# x\n")
        self.write_registry({"projects": {self.proj.as_posix(): {},
                                          p2.as_posix(): {}, p3.as_posix(): {}}})
        with mock.patch("core._git_tracked", return_value=None) as gt:
            projects = core.scan_projects()
        self.assertEqual(len(projects), 3)
        self.assertEqual(gt.call_count, 3)
        called = {core._p(c.args[0]) for c in gt.call_args_list}
        self.assertEqual(called, {core._p(self.proj), core._p(p2), core._p(p3)})


class TestScanLock(FakeHome):
    def test_concurrent_scan(self):
        out = []
        errs = []

        def go():
            try:
                out.append(core.scan())
            except BaseException as e:  # noqa: BLE001
                errs.append(e)

        ts = [threading.Thread(target=go) for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(30)
        self.assertEqual(errs, [])
        self.assertEqual(len(out), 2)
        self.assertTrue(all(isinstance(d, dict) and "projects" in d for d in out))


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
