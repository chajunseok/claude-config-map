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

    def test_only_name_and_description(self):
        fm = core.parse_frontmatter(
            "---\nname: a\ndescription: b\nallowed-tools: Bash\nmodel: opus\n---\n")
        self.assertLessEqual(set(fm), {"name", "description"})
        self.assertEqual(fm, {"name": "a", "description": "b"})

    def test_block_scalar_key_is_skipped(self):
        """멀티라인 값(`|`, `>`)은 키 자체를 넣지 않는다 (G1)."""
        fm = core.parse_frontmatter(
            "---\nname: a\ndescription: |\n  line one\n  line two\n---\nbody")
        self.assertEqual(fm, {"name": "a"})
        self.assertNotIn("description", fm)
        for marker in ("|-", "|+", ">", ">-", ">+"):
            fm = core.parse_frontmatter(
                f"---\nname: a\ndescription: {marker}\n  body\n---\n")
            self.assertEqual(fm, {"name": "a"}, marker)

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
        files, trunc, incomplete = core._walk_md(self.proj, budget=1)
        self.assertFalse(incomplete)
        self.assertTrue(trunc)
        self.assertEqual(core.scan_project(self.proj)["truncated"], False)

    def test_dir_budget_truncates_scan_project(self):
        with mock.patch.object(core, "DIR_BUDGET", 3):
            proj = core.scan_project(self.proj)
        self.assertTrue(proj["truncated"])

    def test_walk_error_marks_incomplete(self):
        def fake_walk(top, onerror=None, **kw):
            onerror(PermissionError(13, "denied", str(self.proj / "locked")))
            return iter([])

        with mock.patch("core.os.walk", side_effect=fake_walk):
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

    def test_local_files_never_shared(self):
        """git이 추적해도 *.local.* 은 개인 설정 (G2)."""
        w(self.proj / ".claude" / "settings.json", "{}")
        w(self.proj / ".claude" / "settings.local.json", "{}")
        r = mock.Mock(returncode=0, stdout=(
            "CLAUDE.md\0CLAUDE.local.md\0"
            ".claude/settings.json\0.claude/settings.local.json\0"))
        with mock.patch("core.subprocess.run", return_value=r):
            proj = core.scan_project(self.proj)
        shared = {e["path"]: e["shared"] for e in proj["claude_md"]}
        self.assertTrue(shared[core._p(self.proj / "CLAUDE.md")])
        self.assertFalse(shared[core._p(self.proj / "CLAUDE.local.md")])
        self.assertTrue(proj["settings"]["settings.json"]["shared"])
        self.assertFalse(proj["settings"]["settings.local.json"]["shared"])

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

    def test_claude_version_timeout(self):
        timeout = subprocess.TimeoutExpired("claude", 3)
        with mock.patch("core.shutil.which", return_value="/usr/bin/claude"):
            with mock.patch("core.subprocess.run", side_effect=timeout):
                self.assertIsNone(core._claude_version())

    def test_claude_version_nonzero_returncode(self):
        r = mock.Mock(returncode=1, stdout="2.1.267\n")
        with mock.patch("core.shutil.which", return_value="/usr/bin/claude"):
            with mock.patch("core.subprocess.run", return_value=r):
                self.assertIsNone(core._claude_version())

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


class TestValidate(FakeHome):
    def test_v1_json_line(self):
        issues = core.validate(self.home / ".claude" / "settings.json",
                               '{\n  "a": 1,\n  oops\n}\n')
        self.assertEqual(len(issues), 1)
        self.assertEqual((issues[0]["level"], issues[0]["rule"]), ("error", "V1"))
        self.assertEqual(issues[0]["line"], 3)

    def test_v1_ok_json_no_issue(self):
        self.assertEqual(core.validate(self.proj / ".mcp.json", '{"a": 1}'), [])

    def test_v2_missing_keys(self):
        sk = self.home / ".claude" / "skills" / "s1" / "SKILL.md"
        issues = core.validate(sk, "---\nname: s1\n---\nbody\n")
        self.assertEqual([(i["rule"], i["level"]) for i in issues], [("V2", "error")])
        self.assertIn("description", issues[0]["message"])
        self.assertNotIn("name,", issues[0]["message"])

        self.assertEqual(core.validate(sk, "---\nname: s1\ndescription: d\n---\n"), [])

        agent = self.home / ".claude" / "agents" / "a.md"
        issues = core.validate(agent, "# no frontmatter\n")
        self.assertEqual(issues[0]["rule"], "V2")
        self.assertIn("name", issues[0]["message"])
        self.assertIn("description", issues[0]["message"])

    def test_v2_command_needs_description_only(self):
        cmd = self.home / ".claude" / "commands" / "c.md"
        self.assertEqual(core.validate(cmd, "---\ndescription: d\n---\nbody\n"), [])
        issues = core.validate(cmd, "---\nname: c\n---\nbody\n")
        self.assertEqual(issues[0]["rule"], "V2")
        self.assertIn("description", issues[0]["message"])

    def test_v2_not_applied_to_plain_markdown(self):
        self.assertEqual(core.validate(self.proj / "sub" / "CLAUDE.md", "# sub\n"), [])

    def test_v3_hook_command_existence(self):
        settings = self.home / ".claude" / "settings.json"
        w(self.home / ".claude" / "hooks" / "there.py", "print()\n")

        def text(cmd):
            return json.dumps({"hooks": {"PreToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": cmd}]}]}})

        self.assertEqual(core.validate(settings, text("hooks/there.py")), [])
        issues = core.validate(settings, text("hooks/gone.py --flag"))
        self.assertEqual([(i["rule"], i["level"]) for i in issues], [("V3", "error")])
        self.assertIn("hooks/gone.py", issues[0]["message"])

    def test_v3_skips_env_vars_and_bare_commands(self):
        settings = self.home / ".claude" / "settings.json"

        def text(cmd):
            return json.dumps({"hooks": {"Stop": [
                {"matcher": "*", "hooks": [{"type": "command", "command": cmd}]}]}})

        for cmd in ("$CLAUDE_PROJECT_DIR/hooks/gone.py", "%USERPROFILE%\\gone.py",
                    "echo hi", "git status"):
            self.assertEqual(core.validate(settings, text(cmd)), [], cmd)

    def test_v3_quoted_absolute_path(self):
        settings = self.home / ".claude" / "settings.json"
        real = w(self.home / ".claude" / "my hooks" / "h.py", "x\n")
        body = json.dumps({"hooks": {"Stop": [{"matcher": "*", "hooks": [
            {"type": "command", "command": '"%s" --run' % real.as_posix()}]}]}})
        self.assertEqual(core.validate(settings, body), [])

    def test_v4_imports_and_relative_links(self):
        md = self.proj / "CLAUDE.md"
        text = ("# proj\n"
                "@./docs/extra.md\n"
                "@./missing.md\n"
                "[ok](./docs/extra.md)\n"
                "[bad](./nope.md)\n"
                "[url](https://example.com/x.md)\n"
                "[anchor](#section)\n")
        issues = core.validate(md, text)
        self.assertTrue(all(i["rule"] == "V4" and i["level"] == "error" for i in issues))
        self.assertEqual([i["line"] for i in issues], [3, 5])
        self.assertIn("./missing.md", issues[0]["message"])
        self.assertIn("./nope.md", issues[1]["message"])

    def test_v4_link_anchor_is_stripped(self):
        self.assertEqual(core.validate(self.proj / "CLAUDE.md",
                                       "[a](./docs/extra.md#top)\n"), [])

    def test_v6_duplicate_star_is_warn(self):
        settings = self.home / ".claude" / "settings.json"
        body = json.dumps({"hooks": {"SessionStart": [
            {"matcher": "startup", "hooks": [{"type": "command", "command": "echo a"}]},
            {"matcher": "*", "hooks": [{"type": "command", "command": "echo b"}]},
        ]}})
        issues = core.validate(settings, body)
        self.assertEqual([(i["level"], i["rule"]) for i in issues], [("warn", "V6")])
        self.assertIn("SessionStart", issues[0]["message"])


class TestSave(FakeHome):
    def test_writes_and_returns_meta(self):
        p = w(self.proj / "notes.md", "old\n")
        before = core.read_text(p)
        r = core.save(p, "new body\n", before["mtime"])
        self.assertEqual(p.read_bytes(), b"new body\n")
        self.assertEqual(r["issues"], [])
        self.assertEqual(r["size"], p.stat().st_size)
        self.assertTrue(Path(r["backup"]).is_file())
        self.assertEqual(Path(r["backup"]).read_bytes(), b"old\n")

    def test_no_expected_mtime_skips_v7(self):
        p = w(self.proj / "notes.md", "old\n")
        core.save(p, "x\n")
        self.assertEqual(p.read_bytes(), b"x\n")

    def test_v7_conflict_does_not_write(self):
        p = w(self.proj / "notes.md", "old\n")
        r = core.save(p, "new\n", 1.0)
        self.assertTrue(r["conflict"])
        self.assertAlmostEqual(r["mtime"], p.stat().st_mtime)
        self.assertEqual(p.read_bytes(), b"old\n")

    def test_validation_error_does_not_write_or_backup(self):
        p = w(self.proj / ".mcp.json", '{"a": 1}')
        r = core.save(p, "{bad", core.read_text(p)["mtime"])
        self.assertEqual(r["issues"][0]["rule"], "V1")
        self.assertNotIn("backup", r)
        self.assertEqual(p.read_bytes(), b'{"a": 1}')
        self.assertFalse(core.backup_root().exists())

    def test_warn_does_not_block(self):
        p = self.home / ".claude" / "settings.json"
        body = json.dumps({"hooks": {"Stop": [
            {"matcher": "m", "hooks": [{"type": "command", "command": "echo a"}]},
            {"matcher": "*", "hooks": [{"type": "command", "command": "echo b"}]},
        ]}})
        r = core.save(p, body, core.read_text(p)["mtime"])
        self.assertEqual([i["rule"] for i in r["issues"]], ["V6"])
        self.assertEqual(json.loads(p.read_text(encoding="utf-8")), json.loads(body))

    def test_crlf_and_bom_preserved(self):
        p = w(self.proj / "win.md", "a\nb\n", newline="\r\n", bom=True)
        core.save(p, "x\ny\n", core.read_text(p)["mtime"])
        self.assertEqual(p.read_bytes(), b"\xef\xbb\xbfx\r\ny\r\n")

        lf = w(self.proj / "unix.md", "a\n")
        core.save(lf, "x\r\ny\n", core.read_text(lf)["mtime"])
        self.assertEqual(lf.read_bytes(), b"x\ny\n")

    def test_backup_keeps_last_ten(self):
        p = w(self.proj / "notes.md", "0\n")
        for i in range(11):
            core.save(p, "%d\n" % i, core.read_text(p)["mtime"])
        d = Path(core._backup(p)).parent
        baks = sorted(d.glob("*.bak"))
        self.assertEqual(len(baks), core.BACKUP_KEEP)
        self.assertEqual(baks[-1].read_bytes(), b"10\n")  # 방금 부른 _backup의 사본

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            core.save(self.proj / "gone.md", "x\n", 1.0)

    def test_replace_failure_leaves_file_and_no_temp(self):
        p = w(self.proj / "notes.md", "old\n")
        with mock.patch("core.os.replace", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                core.save(p, "new\n", core.read_text(p)["mtime"])
        self.assertEqual(p.read_bytes(), b"old\n")
        self.assertEqual(list(p.parent.glob(".config-map-*")), [])


class TestToggle(FakeHome):
    def local(self):
        return self.proj / ".claude" / "settings.local.json"

    def data(self, p=None):
        return json.loads((p or self.local()).read_text(encoding="utf-8-sig"))

    def test_creates_file_and_directory(self):
        fresh = Path(self.tmp.name) / "fresh"
        r = core.toggle(fresh, "skillOverrides", "s1", "off")
        self.assertTrue(r["created"])
        self.assertIsNone(r["backup"])
        self.assertEqual(r["value"], "off")
        p = fresh / ".claude" / "settings.local.json"
        self.assertEqual(r["path"], core._p(p))
        self.assertEqual(self.data(p), {"skillOverrides": {"s1": "off"}})
        self.assertEqual(p.read_bytes(), json.dumps(
            {"skillOverrides": {"s1": "off"}}, indent=2).encode("utf-8") + b"\n")

    def test_updates_existing_key_and_backs_up(self):
        w(self.local(), json.dumps({"skillOverrides": {"s1": "off"}}))
        r = core.toggle(self.proj, "skillOverrides", "s1", "name-only")
        self.assertFalse(r["created"])
        self.assertEqual(self.data(), {"skillOverrides": {"s1": "name-only"}})
        self.assertEqual(json.loads(Path(r["backup"]).read_text(encoding="utf-8")),
                         {"skillOverrides": {"s1": "off"}})

    def test_default_value_deletes_key_and_empty_section(self):
        w(self.local(), json.dumps({"skillOverrides": {"s1": "off"}}))
        r = core.toggle(self.proj, "skillOverrides", "s1", "on")
        self.assertIsNone(r["value"])
        self.assertEqual(self.data(), {})

        w(self.local(), json.dumps({"enabledPlugins": {"a@m": False}}))
        r = core.toggle(self.proj, "enabledPlugins", "a@m", True)
        self.assertIsNone(r["value"])
        self.assertEqual(self.data(), {})

    def test_plugin_false_is_stored(self):
        core.toggle(self.proj, "enabledPlugins", "a@m", False)
        self.assertEqual(self.data(), {"enabledPlugins": {"a@m": False}})

    def test_other_keys_and_sections_are_kept(self):
        w(self.local(), json.dumps({"hooks": {"Stop": []},
                                    "skillOverrides": {"keep": "off", "s1": "off"},
                                    "enabledPlugins": {"a@m": False}}))
        core.toggle(self.proj, "skillOverrides", "s1", "on")
        self.assertEqual(self.data(), {"hooks": {"Stop": []},
                                       "skillOverrides": {"keep": "off"},
                                       "enabledPlugins": {"a@m": False}})

    def test_non_dict_section_is_replaced(self):
        w(self.local(), json.dumps({"skillOverrides": "nope"}))
        core.toggle(self.proj, "skillOverrides", "s1", "off")
        self.assertEqual(self.data(), {"skillOverrides": {"s1": "off"}})

    def test_crlf_and_bom_preserved(self):
        w(self.local(), json.dumps({"skillOverrides": {}}, indent=2) + "\n",
          newline="\r\n", bom=True)
        core.toggle(self.proj, "skillOverrides", "s1", "off")
        raw = self.local().read_bytes()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"\r\n", raw)
        self.assertNotIn(b"\n", raw.replace(b"\r\n", b""))
        self.assertEqual(self.data(), {"skillOverrides": {"s1": "off"}})

    def test_invalid_json_returns_issue_and_keeps_file(self):
        w(self.local(), "{bad")
        r = core.toggle(self.proj, "skillOverrides", "s1", "off")
        self.assertEqual(r["issues"][0]["rule"], "V1")
        self.assertEqual(r["issues"][0]["level"], "error")
        self.assertNotIn("path", r)
        self.assertEqual(self.local().read_bytes(), b"{bad")

    def test_top_level_list_is_issue(self):
        w(self.local(), "[1, 2]")
        r = core.toggle(self.proj, "skillOverrides", "s1", "off")
        self.assertEqual(r["issues"][0]["rule"], "V1")
        self.assertEqual(self.local().read_bytes(), b"[1, 2]")

    def test_target_settings_json(self):
        r = core.toggle(self.proj, "skillOverrides", "s1", "off",
                        target="settings.json")
        self.assertEqual(r["path"], core._p(self.proj / ".claude" / "settings.json"))
        self.assertFalse(self.local().exists())


class TestParseSections(unittest.TestCase):
    def titles(self, text):
        return [(s["level"], s["title"], s["start"], s["end"])
                for s in core.parse_sections(text)]

    def test_levels_and_boundaries(self):
        text = "# A\nx\n## B\ny\n### C\n# D\n"
        self.assertEqual(self.titles(text), [
            (1, "A", 0, 5), (2, "B", 2, 5), (3, "C", 4, 5), (1, "D", 5, 7)])

    def test_preamble(self):
        text = "intro\n\n# A\n"
        self.assertEqual(self.titles(text), [(0, "", 0, 2), (1, "A", 2, 4)])

    def test_no_heading_is_one_preamble(self):
        self.assertEqual(self.titles("just text\n"), [(0, "", 0, 2)])
        self.assertEqual(core.parse_sections(""), [])
        self.assertEqual(core.parse_sections("   \n"), [])

    def test_hash_inside_fence_is_not_heading(self):
        text = "# A\n```\n# not a heading\n```\n## B\n"
        self.assertEqual(self.titles(text), [(1, "A", 0, 6), (2, "B", 4, 6)])

    def test_tilde_fence_and_longer_fence(self):
        text = "# A\n~~~\n# no\n~~~\n````\n# no\n```\n# no\n````\n## B\n"
        self.assertEqual([t[1] for t in self.titles(text)], ["A", "B"])

    def test_unclosed_fence_swallows_rest(self):
        text = "# A\n```\n# never\n## never\n"
        self.assertEqual(self.titles(text), [(1, "A", 0, 5)])

    def test_trailing_hashes_are_stripped(self):
        self.assertEqual(self.titles("## Title ###\n")[0][1], "Title")
        self.assertEqual(self.titles("## a #b\n")[0][1], "a #b")

    def test_crlf_input_uses_logical_lines(self):
        self.assertEqual(self.titles("# A\r\nx\r\n## B\r\n"),
                         [(1, "A", 0, 4), (2, "B", 2, 4)])

    def test_indented_hash_and_seven_hashes_are_not_headings(self):
        self.assertEqual(self.titles("    # deep\n####### seven\n#no-space\n"),
                         [(0, "", 0, 4)])


class TestSectionConflicts(unittest.TestCase):
    def files(self, *pairs):
        return [{"path": p, "scope": "global", "sections": core.parse_sections(t)}
                for p, t in pairs]

    def test_same_title_in_different_files(self):
        c = core.section_conflicts(self.files(("/a.md", "# Rules\n"),
                                              ("/b.md", "## Rules\n")))
        self.assertEqual(len(c), 1)
        self.assertEqual(c[0]["title"], "Rules")
        self.assertEqual([w["path"] for w in c[0]["where"]], ["/a.md", "/b.md"])

    def test_duplicate_inside_one_file_is_not_a_conflict(self):
        self.assertEqual(core.section_conflicts(
            self.files(("/a.md", "# Rules\n# Rules\n"))), [])

    def test_preamble_is_excluded(self):
        self.assertEqual(core.section_conflicts(
            self.files(("/a.md", "intro\n"), ("/b.md", "intro\n"))), [])

    def test_case_sensitive_exact_match(self):
        self.assertEqual(core.section_conflicts(
            self.files(("/a.md", "# Rules\n"), ("/b.md", "# rules\n"))), [])


class TestCompareSections(FakeHome):
    def test_global_and_projects(self):
        w(self.home / ".claude" / "CLAUDE.md", "# Rules\nglobal body\n")
        w(self.proj / "CLAUDE.md", "# Rules\nproject body\n")
        m = core.compare_sections(core.scan(), "Rules")
        self.assertEqual([(x["project"], x["scope"]) for x in m],
                         [(None, "global"), ("proj", "project")])
        self.assertEqual(m[0]["text"], "# Rules\nglobal body\n")
        self.assertEqual(m[1]["text"], "# Rules\nproject body\n")

    def test_rules_dir_and_local_scopes(self):
        w(self.home / ".claude" / "rules" / "r1.md", "# Rules\n")
        w(self.proj / ".claude" / "rules" / "a.md", "# Rules\n")
        w(self.proj / "CLAUDE.local.md", "# Rules\n")
        w(self.proj / "sub" / "CLAUDE.md", "# Rules\n")
        scopes = [x["scope"] for x in core.compare_sections(core.scan(), "Rules")]
        self.assertEqual(sorted(scopes),
                         ["global-rules", "project-local", "project-rules", "subdir"])

    def test_unreadable_file_is_skipped(self):
        w(self.home / ".claude" / "CLAUDE.md", "# Rules\n")
        scan = core.scan()
        real = core.read_text

        def boom(path):
            if str(path).endswith("CLAUDE.md"):
                return core._err(path, "permission denied: boom")
            return real(path)

        with mock.patch.object(core, "read_text", side_effect=boom):
            self.assertEqual(core.compare_sections(scan, "Rules"), [])
        self.assertTrue(any("permission denied" in e["error"] for e in core.errors()))

    def test_empty_title_matches_nothing(self):
        self.assertEqual(core.compare_sections(core.scan(), "  "), [])


class TestReplaceRange(FakeHome):
    def setUp(self):
        super().setUp()
        self.p = w(self.proj / "notes.md", "# A\nbody\n## B\nmore\n")

    def mtime(self, p=None):
        return core.read_text(p or self.p)["mtime"]

    def test_replaces_middle(self):
        r = core.replace_range(self.p, 2, 4, "## B2\nnew\n", self.mtime())
        self.assertEqual(self.p.read_bytes(), b"# A\nbody\n## B2\nnew\n")
        self.assertEqual([s["title"] for s in r["sections"]], ["A", "B2"])
        self.assertTrue(Path(r["backup"]).is_file())

    def test_replaces_first_and_last_lines(self):
        core.replace_range(self.p, 0, 1, "# A2\n", self.mtime())
        self.assertEqual(self.p.read_bytes(), b"# A2\nbody\n## B\nmore\n")
        core.replace_range(self.p, 4, 5, "tail\n", self.mtime())
        self.assertEqual(self.p.read_bytes(), b"# A2\nbody\n## B\nmore\ntail")

    def test_bad_range_does_not_write(self):
        for start, end in ((-1, 2), (3, 2), (0, 99), (99, 99)):
            r = core.replace_range(self.p, start, end, "x\n", self.mtime())
            self.assertTrue(r["bad_range"], (start, end))
        self.assertEqual(self.p.read_bytes(), b"# A\nbody\n## B\nmore\n")

    def test_crlf_and_bom_preserved(self):
        p = w(self.proj / "win.md", "# A\nbody\n", newline="\r\n", bom=True)
        core.replace_range(p, 1, 2, "new\n", self.mtime(p))
        self.assertEqual(p.read_bytes(), b"\xef\xbb\xbf# A\r\nnew\r\n")

    def test_v7_conflict_does_not_write(self):
        r = core.replace_range(self.p, 0, 1, "# X\n", 1.0)
        self.assertTrue(r["conflict"])
        self.assertNotIn("sections", r)
        self.assertEqual(self.p.read_bytes(), b"# A\nbody\n## B\nmore\n")

    def test_validation_error_does_not_write(self):
        p = w(self.proj / ".claude" / "skills" / "s1" / "SKILL.md",
              "---\nname: s1\ndescription: d\n---\nbody\n")
        r = core.replace_range(p, 1, 2, "name:\n", self.mtime(p))
        self.assertEqual(r["issues"][0]["rule"], "V2")
        self.assertNotIn("sections", r)
        self.assertIn(b"name: s1", p.read_bytes())

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            core.replace_range(self.proj / "gone.md", 0, 0, "x\n", 1.0)


if __name__ == "__main__":
    unittest.main()
