"""F4 검증 · F5 저장 · F7 토글 테스트."""

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core  # noqa: E402
import edit  # noqa: E402
from helpers import FakeHome, w  # noqa: E402,F401


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
        with mock.patch("edit.os.replace", side_effect=OSError("boom")):
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

if __name__ == "__main__":
    unittest.main()
