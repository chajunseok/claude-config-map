"""F9 편집 도우미 — 프롬프트 조립·펜스 제거·diff·작업 실행/취소 테스트 (CLI 는 전부 모킹)."""

import json
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import assist  # noqa: E402
from helpers import FakeHome  # noqa: E402


def ok_json(result, cost=0.01, ms=1200):
    return json.dumps({"type": "result", "subtype": "success", "is_error": False,
                       "result": result, "duration_ms": ms, "session_id": "s",
                       "total_cost_usd": cost})


class FakeProc:
    """communicate 로 정해진 결과를 돌려주는 Popen 대역. gate 를 주면 그때까지 막힌다."""

    def __init__(self, out="", err="", code=0, gate=None, timeout=False):
        self.out, self.err, self.returncode = out, err, code
        self.gate, self.timeout = gate, timeout
        self.killed = False

    def communicate(self, prompt=None, timeout=None):
        if self.timeout:
            raise subprocess.TimeoutExpired("claude", timeout or 0)
        if self.gate is not None:
            self.gate.wait(5)
            raise OSError("pipe closed")
        return self.out, self.err

    def kill(self):
        self.killed = True
        if self.gate is not None:
            self.gate.set()


class AssistCase(FakeHome):
    def setUp(self):
        super().setUp()
        assist._JOBS.clear()
        self.addCleanup(assist._JOBS.clear)
        cli = mock.patch.object(assist, "cli_path", return_value="claude")
        cli.start()
        self.addCleanup(cli.stop)

    def run_job(self, proc, text="- a\n", instruction="번호 목록으로", **kw):
        with mock.patch.object(assist.subprocess, "Popen", return_value=proc) as p:
            job_id = assist.start(text, instruction, "x/CLAUDE.md", **kw)
            st = self.wait(job_id)
            self.argv = p.call_args[0][0]
            self.kwargs = p.call_args[1]
            return job_id, st

    def wait(self, job_id, want=("done", "error", "cancelled")):
        for _ in range(200):
            st = assist.status(job_id)
            if st and st["status"] in want:
                return st
            time.sleep(0.01)
        self.fail("작업이 끝나지 않음: %s" % assist.status(job_id))


class TestPure(unittest.TestCase):
    def test_strip_fence(self):
        self.assertEqual(assist.strip_fence("```\n# a\n```\n"), "# a\n")
        self.assertEqual(assist.strip_fence("```markdown\n# a\n```"), "# a")
        self.assertEqual(assist.strip_fence("# a\n"), "# a\n")
        inner = "# a\n\n```py\nx=1\n```\n\n# b\n"  # 본문 안 펜스는 그대로
        self.assertEqual(assist.strip_fence(inner), inner)

    def test_make_diff(self):
        self.assertEqual(assist.make_diff("a\n", "a\n"), "")
        d = assist.make_diff("- a\n- b\n", "1. a\n- b\n")
        self.assertIn("-- a", d)
        self.assertIn("+1. a", d)
        self.assertTrue(d.startswith("--- 현재"))

    def test_build_prompt(self):
        p = assist.build_prompt("본문", "고쳐줘", "x/CLAUDE.md")
        self.assertIn("문서: x/CLAUDE.md", p)
        self.assertIn("지시: 고쳐줘", p)
        self.assertIn("----- 본문 -----\n본문", p)
        self.assertNotIn("섹션:", p)

        p = assist.build_prompt("본문", "고쳐줘", "x/CLAUDE.md",
                                {"title": "규칙", "start": 4, "end": 9})
        self.assertIn("섹션: 규칙 (L5–L9)", p)


class TestRun(AssistCase):
    def test_success_sets_done_and_diff(self):
        job_id, st = self.run_job(FakeProc(ok_json("1. a\n")))
        self.assertEqual(st["status"], "done")
        self.assertEqual(st["result"], "1. a\n")
        self.assertTrue(st["changed"])
        self.assertIn("+1. a", st["diff"])
        self.assertEqual(st["cost_usd"], 0.01)
        self.assertEqual(st["duration_ms"], 1200)
        self.assertEqual(st["id"], job_id)
        self.assertIsInstance(st["elapsed_ms"], int)

    def test_argv_has_no_tools_and_stdin_prompt(self):
        self.run_job(FakeProc(ok_json("- a\n")), model="sonnet")
        self.assertEqual(self.argv[:8],
                         ["claude", "-p", "--tools", "", "--output-format", "json",
                          "--no-session-persistence", "--system-prompt"])
        self.assertEqual(self.argv[-2:], ["--model", "sonnet"])
        self.assertEqual(self.kwargs["stdin"], subprocess.PIPE)
        self.assertTrue(str(self.kwargs["cwd"]).endswith("config-map"))

    def test_unchanged_has_empty_diff(self):
        _, st = self.run_job(FakeProc(ok_json("- a\n")))
        self.assertEqual(st["status"], "done")
        self.assertFalse(st["changed"])
        self.assertEqual(st["diff"], "")

    def test_crlf_source_keeps_crlf(self):
        _, st = self.run_job(FakeProc(ok_json("1. a\n1. b\n")), text="- a\r\n- b\r\n")
        self.assertEqual(st["result"], "1. a\r\n1. b\r\n")

    def test_is_error_becomes_error(self):
        payload = json.dumps({"type": "result", "subtype": "error_during_execution",
                              "is_error": True, "result": "로그인이 필요합니다"})
        _, st = self.run_job(FakeProc(payload))
        self.assertEqual(st["status"], "error")
        self.assertEqual(st["error"], "로그인이 필요합니다")
        self.assertNotIn("result", st)

    def test_non_json_uses_stderr(self):
        _, st = self.run_job(FakeProc("not json", "boom: 실패", 1))
        self.assertEqual(st["status"], "error")
        self.assertEqual(st["error"], "boom: 실패")

    def test_timeout(self):
        _, st = self.run_job(FakeProc(timeout=True))
        self.assertEqual(st["status"], "error")
        self.assertIn("시간 초과", st["error"])

    def test_cancel_kills_process(self):
        gate = threading.Event()
        proc = FakeProc(gate=gate)
        with mock.patch.object(assist.subprocess, "Popen", return_value=proc):
            job_id = assist.start("- a\n", "고쳐줘", "x/CLAUDE.md")
            for _ in range(200):  # Popen 이 작업에 붙을 때까지
                if assist._JOBS[job_id].get("proc") is not None:
                    break
                time.sleep(0.01)
            self.assertTrue(assist.cancel(job_id))
            st = self.wait(job_id)
        self.assertEqual(st["status"], "cancelled")
        self.assertTrue(proc.killed)
        time.sleep(0.05)  # 스레드가 뒤늦게 상태를 덮어쓰지 않는다
        self.assertEqual(assist.status(job_id)["status"], "cancelled")

    def test_cancel_unknown_and_finished(self):
        self.assertFalse(assist.cancel("nope"))
        job_id, _ = self.run_job(FakeProc(ok_json("1. a\n")))
        self.assertTrue(assist.cancel(job_id))
        self.assertEqual(assist.status(job_id)["status"], "done")

    def test_status_unknown_is_none(self):
        self.assertIsNone(assist.status("nope"))

    def test_busy_over_max_running(self):
        gates = [threading.Event() for _ in range(assist.MAX_RUNNING)]
        procs = [FakeProc(gate=g) for g in gates]
        ids = []
        with mock.patch.object(assist.subprocess, "Popen", side_effect=procs):
            for _ in procs:
                ids.append(assist.start("- a\n", "고쳐줘", "x/CLAUDE.md"))
            with self.assertRaises(RuntimeError) as cm:
                assist.start("- a\n", "고쳐줘", "x/CLAUDE.md")
            self.assertEqual(str(cm.exception), "busy")
            for job_id in ids:
                assist.cancel(job_id)
                self.wait(job_id)

    def test_start_without_cli_raises(self):
        with mock.patch.object(assist, "cli_path", return_value=None):
            with self.assertRaises(RuntimeError):
                assist.start("- a\n", "고쳐줘", "x/CLAUDE.md")

    def test_prune_keeps_max_jobs(self):
        for i in range(assist.MAX_JOBS + 5):
            assist._JOBS["j%d" % i] = {"id": "j%d" % i, "status": "done",
                                       "started_at": float(i), "started": 0.0,
                                       "ended": 0.0, "proc": None}
        with assist._LOCK:
            assist._prune()
        self.assertEqual(len(assist._JOBS), assist.MAX_JOBS)
        self.assertNotIn("j0", assist._JOBS)


if __name__ == "__main__":
    unittest.main()
