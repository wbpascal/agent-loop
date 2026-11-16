import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import report  # noqa: E402


def line(t, mid, model, usage, kind="assistant"):
    return json.dumps({"type": kind, "timestamp": t, "message": {"id": mid, "model": model, "usage": usage}})


def usage(inp, out, read=0, w5=0, w1=0):
    return {
        "input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": read,
        "cache_creation": {"ephemeral_5m_input_tokens": w5, "ephemeral_1h_input_tokens": w1},
    }


class ReportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        report.CONFIG = self.tmp
        self.proj = self.tmp / "projects" / "p"
        self.sub = self.proj / "sess" / "subagents"
        self.sub.mkdir(parents=True)
        self.run = self.tmp / "repo" / ".agent-loop" / "42"
        self.run.mkdir(parents=True)
        (self.run / "run.json").write_text(json.dumps(
            {"base": "main", "sessions": [{"id": "sess", "start": "2026-01-01T10:00:00+00:00"}], "rate_limits": None}))

    def agent(self, aid, agent_type, lines):
        (self.sub / f"agent-{aid}.meta.json").write_text(json.dumps({"agentType": agent_type}))
        (self.sub / f"agent-{aid}.jsonl").write_text("\n".join(lines))

    def test_report(self):
        (self.proj / "sess.jsonl").write_text("\n".join([
            line("2026-01-01T09:00:00Z", "old", "claude-haiku-5-5", usage(1_000_000, 0)),  # before the run
            line("2026-01-01T10:00:01Z", "m1", "claude-haiku-5-5", usage(1_000_000, 0)),  # over 100K: tier 2
        ]))
        self.agent("a", "agent-loop:planner", [
            line("2026-01-01T10:01:00Z", "p1", "claude-fable-5-2", usage(999, 999)),  # superseded by next line
            line("2026-01-01T10:02:05Z", "p1", "claude-fable-5-2", usage(1_000_000, 100_000, read=1_000_000, w5=1_000_000)),
        ])
        self.agent("b", "agent-loop:reviewer", [line("2026-01-01T10:05:00Z", "r1", "claude-opus-5-5", usage(0, 1_000_000))])
        self.agent("c", "general-purpose", [line("2026-01-01T10:06:00Z", "x", "claude-opus-5-5", usage(5, 5))])
        self.agent("d", "agent-loop:executor", [line("2026-01-01T09:30:00Z", "e0", "claude-sonnet-5-5", usage(5, 5))])  # earlier run
        (self.run / "review-1.md").write_text("VERDICT: DONE\n")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            report.report(SimpleNamespace(dir=str(self.run), outcome="done"))
        out = buf.getvalue()

        self.assertIn("issue #42", out)
        # planner: 8 input + 4 output + 0.2 cache read + 10 cache write
        self.assertIn("| 1 | planner 1 | claude-fable-5-2 | 10:01:00 | 1m 05s |  | 1,000,000 | 1,000,000 | 1,000,000 | 100,000 | $22.20 |", out)
        self.assertIn("| 2 | reviewer 1 | claude-opus-5-5 | 10:05:00 | 0m 00s | DONE |", out)
        self.assertIn("| dispatcher | - | 1,000,000 | 0 | 0 | 0 | $0.500 |", out)
        self.assertNotIn("executor", out)
        self.assertTrue(out.strip().endswith("Total: $42.70 API-equivalent, 5,100,000 tokens, 2 agent calls, outcome done"))

    def test_unknown_model_has_no_cost(self):
        (self.proj / "sess.jsonl").write_text(line("2026-01-01T10:00:01Z", "m1", "claude-future-9", usage(10, 10)))
        calls = report.collect(json.loads((self.run / "run.json").read_text()), {})
        self.assertIsNone(calls[0]["cost"])

    def test_plan_usage_skips_reset_window(self):
        (self.tmp / "agent-loop-statusline.json").write_text(json.dumps({"rate_limits": {
            "five_hour": {"used_percentage": 30, "resets_at": 2}, "seven_day": {"used_percentage": 12.5, "resets_at": 9}}}))
        before = {"five_hour": {"used_percentage": 90, "resets_at": 1}, "seven_day": {"used_percentage": 10, "resets_at": 9}}
        self.assertEqual(report.plan_usage(before), ["7d +2.5%"])


if __name__ == "__main__":
    unittest.main()
