"""테스트 공용: 가짜 홈 픽스처와 파일 쓰기 헬퍼."""

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import core  # noqa: E402
import scan  # noqa: E402


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
        self.run_patch = mock.patch("scan.subprocess.run", side_effect=OSError("no exe"))
        self.run_patch.start()
        self.addCleanup(self.run_patch.stop)

        core._errors.clear()

    def write_registry(self, obj):
        w(self.home / ".claude.json", json.dumps(obj) if isinstance(obj, dict) else obj)
