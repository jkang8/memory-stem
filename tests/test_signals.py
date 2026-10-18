import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

# scripts/ is not a package: load the module by path
_spec = importlib.util.spec_from_file_location("signals", Path(__file__).parent.parent / "scripts" / "signals.py")
assert _spec is not None and _spec.loader is not None
signals = sys.modules["signals"] = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(signals)


class ReplaySummaryTest(unittest.TestCase):
    def write(self, rows) -> Path:
        p = Path(tempfile.mkdtemp()) / "replay_log.jsonl"
        p.write_text("".join(json.dumps(r) + "\n" for r in rows) + "not json\n")
        return p

    def test_counts_entries_notes_and_prompt_like_wording(self):
        p = self.write([{"day": "2026-10-01", "q": "where is the hotel", "id": "a"},
                        {"day": "2026-10-02", "q": "hotel again", "id": "a"},
                        {"day": "2026-10-03", "q": "[SYSTEM: scheduled job] do the thing", "id": "b"}])
        lines = signals.replay_summary(p)
        self.assertEqual(lines[0], "3 entries for 2 notes, 1 starting like a system prompt rather than user wording")
        self.assertIn("a: 2", lines[1])
        self.assertNotIn("hotel", "\n".join(lines))  # wording is personal: counts and note ids only

    def test_missing_log_says_so(self):
        self.assertEqual(signals.replay_summary(Path(tempfile.mkdtemp()) / "nope.jsonl"), ["no replay log"])


if __name__ == "__main__":
    unittest.main()
