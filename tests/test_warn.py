import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from memory_stem.embedder import Embedder
from memory_stem.index import Index
from memory_stem.notes import NoteStore
from memory_stem.search import Searcher
from memory_stem.stale import intent, warn
from memory_stem.tools import Tools

TODAY = dt.date(2026, 10, 14)


class WarnTest(unittest.TestCase):
    def test_future_date_without_expiry_suggests_day_after(self):
        w = warn("Enroll by Oct 30 2026 in Rippling.", today=TODAY)
        self.assertIn("expires=2026-10-31", w)
        self.assertIn("deadline", w)

    def test_expiry_set_or_only_past_dates_is_quiet(self):
        self.assertEqual(warn("Enroll by Oct 30 2026.", expires="2026-10-31", today=TODAY), "")
        self.assertEqual(warn("Moved in 2025-06-12.", today=TODAY), "")
        self.assertEqual(warn("Likes short replies.", today=TODAY), "")

    def test_relative_dates_flagged(self):
        self.assertIn("relative date", warn("Flight is next Friday.", today=TODAY))
        self.assertIn("relative date", warn("Call tomorrow.", today=TODAY))

    def test_intent_cues(self):
        self.assertEqual(intent("Free changes end Oct 15; payment due"), "deadline")
        self.assertEqual(intent("Apartments.com first invited him; moved in June 2025"), "history")
        self.assertEqual(intent("Hotel Harbor Inn on Oct 18"), "unclear")

    def test_tools_return_warning_but_still_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = NoteStore(Path(tmp) / "Memory")
            e = Embedder()
            idx = Index(Path(tmp) / "i.sqlite", e)
            t = Tools(store, Searcher(idx, e, 0.5), lambda: idx.sync(store.all()))
            future = (dt.date.today() + dt.timedelta(days=30)).isoformat()
            r = json.loads(t.handle("ms_remember", {"content": f"Deadline is {future}.", "title": "d"}))
            self.assertTrue(r["ok"])
            self.assertIn("expires=", r["warning"])
            r2 = json.loads(t.handle("ms_draft", {"content": "Call tomorrow.", "title": "c"}))
            self.assertIn("relative date", r2["warning"])
            r3 = json.loads(t.handle("ms_remember", {"content": "Likes tea.", "title": "t"}))
            self.assertNotIn("warning", r3)
            self.assertEqual(len(store.all()), 2)


if __name__ == "__main__":
    unittest.main()
