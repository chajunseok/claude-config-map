"""F1·F2 스캔 테스트."""

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
import scan  # noqa: E402
from helpers import FakeHome, w  # noqa: E402,F401


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
        files, trunc, incomplete = core._walk_md(self.proj, budget=1)
        self.assertFalse(incomplete)
        self.assertTrue(trunc)
        self.assertEqual(core.scan_project(self.proj)["truncated"], False)

    def test_dir_budget_truncates_scan_project(self):
        with mock.patch.object(scan, "DIR_BUDGET", 3):
            proj = core.scan_project(self.proj)
        self.assertTrue(proj["truncated"])

    def test_walk_error_marks_incomplete(self):
        def fake_walk(top, onerror=None, **kw):
            onerror(PermissionError(13, "denied", str(self.proj / "locked")))
            return iter([])

        with mock.patch("scan.os.walk", side_effect=fake_walk):
            proj = core.scan_project(self.proj)
        self.assertTrue(proj["incomplete"])
        self.assertTrue(any("walk failed" in e["error"] for e in core.errors()))
        self.assertTrue(any(e["path"].endswith("/locked") for e in core.errors()))

    def test_no_walk_error_means_complete(self):
        self.assertFalse(core.scan_project(self.proj)["incomplete"])

    def test_stat_race_drops_file(self):
        target = self.proj / "sub" / "CLAUDE.md"
        gone = core._p(target)
        real = Path.stat

        def flaky(self_, *a, **kw):
            if Path(self_) == target:
                raise FileNotFoundError(2, "gone", str(target))
            return real(self_, *a, **kw)

        with mock.patch.object(Path, "stat", flaky):
            proj = core.scan_project(self.proj)
        paths = {e["path"] for e in proj["claude_md"]}
        self.assertNotIn(gone, paths)
        self.assertIn(core._p(self.proj / "CLAUDE.md"), paths)


class TestScan(FakeHome):
    def test_missing_project(self):
        projects = core.scan_projects()
        self.assertEqual(len(projects), 2)
        gone = [p for p in projects if not p.get("exists")]
        self.assertEqual(len(gone), 1)
        self.assertEqual(set(gone[0]), {"path", "exists"})

    def _md(self, proj, path):
        return {e["path"]: e for e in proj["claude_md"]}[core._p(path)]

    def test_imports(self):
        proj = core.scan_project(self.proj)
        e = self._md(proj, self.proj / "CLAUDE.md")
        by_raw = {i["raw"]: i["exists"] for i in e["imports"]}
        self.assertTrue(by_raw["./docs/extra.md"])
        self.assertFalse(by_raw["./missing.md"])

    def test_imports_one_level_only(self):
        w(self.proj / "CLAUDE.md", "# proj\n@./b.md\n")
        w(self.proj / "b.md", "@./c.md\n")
        w(self.proj / "c.md", "leaf\n")
        proj = core.scan_project(self.proj)
        raws = {i["raw"] for e in proj["claude_md"] for i in e["imports"]}
        self.assertIn("./b.md", raws)
        self.assertNotIn("./c.md", raws)

    def test_subdir_imports_resolve_against_own_dir(self):
        w(self.proj / "sub" / "CLAUDE.md", "# sub\n@x.md\n@nope.md\n")
        w(self.proj / "sub" / "x.md", "y\n")
        proj = core.scan_project(self.proj)
        e = self._md(proj, self.proj / "sub" / "CLAUDE.md")
        by_raw = {i["raw"]: i for i in e["imports"]}
        self.assertEqual(by_raw["x.md"]["path"], core._p(self.proj / "sub" / "x.md"))
        self.assertTrue(by_raw["x.md"]["exists"])
        self.assertEqual(by_raw["nope.md"]["path"], core._p(self.proj / "sub" / "nope.md"))
        self.assertFalse(by_raw["nope.md"]["exists"])

    def test_shared_false_without_git(self):
        proj = core.scan_project(self.proj)
        self.assertFalse(proj["git"])
        self.assertTrue(all(not e["shared"] for e in proj["claude_md"]))

    def test_git_ls_files_nul_separated(self):
        r = mock.Mock(returncode=0, stdout="CLAUDE.md\0sub/CLAUDE.md\0")
        with mock.patch("scan.subprocess.run", return_value=r) as m:
            proj = core.scan_project(self.proj)
        args = m.call_args.args[0]
        self.assertIn("-z", args)
        self.assertEqual(m.call_args.kwargs["timeout"], 2)
        self.assertTrue(proj["git"])
        shared = {e["path"]: e["shared"] for e in proj["claude_md"]}
        self.assertTrue(shared[core._p(self.proj / "CLAUDE.md")])
        self.assertTrue(shared[core._p(self.proj / "sub" / "CLAUDE.md")])
        self.assertFalse(shared[core._p(self.proj / "CLAUDE.local.md")])

    def test_local_files_never_shared(self):
        """git이 추적해도 *.local.* 은 개인 설정 (G2)."""
        w(self.proj / ".claude" / "settings.json", "{}")
        w(self.proj / ".claude" / "settings.local.json", "{}")
        r = mock.Mock(returncode=0, stdout=(
            "CLAUDE.md\0CLAUDE.local.md\0"
            ".claude/settings.json\0.claude/settings.local.json\0"))
        with mock.patch("scan.subprocess.run", return_value=r):
            proj = core.scan_project(self.proj)
        shared = {e["path"]: e["shared"] for e in proj["claude_md"]}
        self.assertTrue(shared[core._p(self.proj / "CLAUDE.md")])
        self.assertFalse(shared[core._p(self.proj / "CLAUDE.local.md")])
        self.assertTrue(proj["settings"]["settings.json"]["shared"])
        self.assertFalse(proj["settings"]["settings.local.json"]["shared"])

    def test_git_timeout_means_not_shared(self):
        with mock.patch("scan.subprocess.run",
                        side_effect=subprocess.TimeoutExpired("git", 2)):
            proj = core.scan_project(self.proj)
        self.assertFalse(proj["git"])
        self.assertTrue(all(not e["shared"] for e in proj["claude_md"]))

    def test_claude_version_ok(self):
        r = mock.Mock(returncode=0, stdout="2.1.267 (Claude Code)\n")
        with mock.patch("scan.shutil.which", return_value="/usr/bin/claude"), \
                mock.patch("scan.subprocess.run", return_value=r) as m:
            self.assertEqual(core._claude_version(), "2.1.267 (Claude Code)")
        self.assertEqual(m.call_args.kwargs["timeout"], 3)

    def test_claude_version_timeout(self):
        timeout = subprocess.TimeoutExpired("claude", 3)
        with mock.patch("scan.shutil.which", return_value="/usr/bin/claude"):
            with mock.patch("scan.subprocess.run", side_effect=timeout):
                self.assertIsNone(core._claude_version())

    def test_claude_version_nonzero_returncode(self):
        r = mock.Mock(returncode=1, stdout="2.1.267\n")
        with mock.patch("scan.shutil.which", return_value="/usr/bin/claude"):
            with mock.patch("scan.subprocess.run", return_value=r):
                self.assertIsNone(core._claude_version())

    def test_claude_version_absent(self):
        with mock.patch("scan.shutil.which", return_value=None):
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

    def test_same_dir_registered_twice_is_one_project(self):
        """`C:/x` 와 `c:/x` 처럼 표기만 다른 같은 폴더는 프로젝트 1개 (UI 중복 행 방지)."""
        w(self.home / "proj3" / "CLAUDE.md", "# p3\n")
        a = (self.home / "proj3").as_posix()
        variants = {a: {}, a.replace("/proj3", "//proj3"): {}, "~/proj3/": {}}
        if a[1:2] == ":":
            variants[a[0].swapcase() + a[1:]] = {}
        self.write_registry({"projects": variants})
        projects = core.scan_projects()
        self.assertEqual([p["path"] for p in projects], [core._p(self.home / "proj3")])


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
        with mock.patch("scan._git_tracked", return_value=None) as gt:
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


class TestExcludeUsesRelativePath(unittest.TestCase):
    """홈 자체가 build/ 같은 제외 이름 아래에 있어도 스캔은 정상 (G3)."""

    def test_home_under_excluded_dir_name(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        home = Path(tmp.name) / "build" / "home"
        w(home / ".claude.json", "{}")
        w(home / ".claude" / "skills" / "x" / "SKILL.md", "---\nname: x\n---\n")
        w(home / ".claude" / "skills" / "node_modules" / "SKILL.md", "---\nname: no\n---\n")
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_MAP_HOME": str(home)}):
            g = core.scan_global()
        names = {e["path"] for e in g["skills"]}
        self.assertIn(core._p(home / ".claude" / "skills" / "x" / "SKILL.md"), names)
        self.assertNotIn(
            core._p(home / ".claude" / "skills" / "node_modules" / "SKILL.md"), names)


class TestPluginScan(FakeHome):
    def setUp(self):
        super().setUp()
        self.plugin = Path(self.tmp.name) / "plug"
        w(self.plugin / ".claude-plugin" / "plugin.json", json.dumps({
            "name": "myplug",
            "description": "does things",
            "hooks": "hooks/hooks.json",
            "mcpServers": {"m1": {"command": "node"}},
        }))
        w(self.plugin / "hooks" / "hooks.json", json.dumps({
            "hooks": {"PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "h"}]}]}
        }))
        w(self.plugin / "skills" / "a" / "SKILL.md",
          "---\nname: skill-a\ndescription: sd\n---\nbody\n")
        w(self.plugin / "commands" / "b.md", "---\nname: cmd-b\n---\nbody\n")
        w(self.plugin / "commands" / "c.toml", 'prompt = "x"\n')
        w(self.home / ".claude" / "plugins" / "installed_plugins.json", json.dumps({
            "plugins": {"myplug@repo": [
                {"installPath": self.plugin.as_posix(), "version": "1.2.3",
                 "scope": "user"}]}
        }))

    def test_scan_plugins_full(self):
        plugins = core.scan_plugins()
        self.assertEqual(len(plugins), 1)
        p = plugins[0]
        self.assertTrue(p["exists"])
        self.assertEqual(p["name"], "myplug")
        self.assertEqual(p["version"], "1.2.3")
        self.assertEqual(p["scope"], "user")
        self.assertEqual(p["description"], "does things")

        self.assertEqual(len(p["skills"]), 1)
        self.assertEqual(p["skills"][0]["name"], "SKILL.md")
        self.assertEqual(p["skills"][0]["name_meta"], "skill-a")
        self.assertEqual(p["skills"][0]["description"], "sd")

        self.assertEqual({c["name"] for c in p["commands"]}, {"b.md", "c.toml"})
        by_name = {c["name"]: c for c in p["commands"]}
        self.assertEqual(by_name["b.md"]["name_meta"], "cmd-b")
        self.assertNotIn("name_meta", by_name["c.toml"])

        self.assertEqual(set(p["hooks"]["hooks"]), {"PreToolUse"})
        self.assertEqual(set(p["mcp_servers"]), {"m1"})
        self.assertEqual(core.errors(), [])

    def test_plugin_hooks_reach_scan(self):
        d = core.scan()
        events = {f["event"] for f in d["hooks"] if f["source"] == "plugin:myplug"}
        self.assertEqual(events, {"PreToolUse"})


class TestJsonTypeGuards(FakeHome):
    def test_projects_as_list_is_recorded(self):
        self.write_registry({"projects": ["a", "b"], "mcpServers": {"gm": {}}})
        d = core.scan()
        self.assertEqual(d["projects"], [])
        self.assertEqual([m["name"] for m in d["mcp"]], ["gm"])
        self.assertTrue(any("expected object, got list" in e["error"]
                            for e in d["errors"]))

    def test_registry_root_as_list(self):
        self.write_registry("[1, 2]")
        d = core.scan()
        self.assertEqual(d["projects"], [])
        self.assertEqual(d["mcp"], [])
        self.assertTrue(any("expected object, got list" in e["error"]
                            for e in d["errors"]))

    def test_plugin_entry_not_object(self):
        w(self.home / ".claude" / "plugins" / "installed_plugins.json",
          json.dumps({"plugins": {"x@y": "nope"}}))
        self.assertEqual(core.scan_plugins(), [])
        self.assertTrue(any("expected object, got str" in e["error"]
                            for e in core.errors()))


class TestPublicFunctionsLocked(FakeHome):
    def test_scan_project_standalone(self):
        a = core.scan_project(self.proj)
        b = core.scan()["projects"]
        b = [p for p in b if p["path"] == core._p(self.proj)][0]
        self.assertEqual(a["claude_md"], b["claude_md"])

    def test_public_helpers_do_not_deadlock(self):
        self.assertTrue(core.scan_global()["claude_md"])
        self.assertEqual(core.scan_plugins(), [])
        self.assertTrue(core.scan_mcp())
        self.assertTrue(core.effective_rules(core.scan_project(self.proj)))


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
