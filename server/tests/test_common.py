"""공용 기반(read_text·parse_frontmatter·home) 테스트."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core  # noqa: E402
from helpers import FakeHome, w  # noqa: E402,F401


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

if __name__ == "__main__":
    unittest.main()
