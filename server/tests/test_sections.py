"""F8 섹션 테스트."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core  # noqa: E402
import sections  # noqa: E402
from helpers import FakeHome, w  # noqa: E402,F401


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

        with mock.patch.object(sections, "read_text", side_effect=boom):
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
