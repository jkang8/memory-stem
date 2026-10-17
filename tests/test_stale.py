import datetime as dt
import tempfile
import unittest
from pathlib import Path

from memory_stem.notes import NoteStore
from memory_stem.stale import dates_in, stale

TODAY = dt.date(2026, 10, 14)


class StaleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = NoteStore(Path(self.tmp.name) / "Memory")

    def tearDown(self):
        self.tmp.cleanup()

    def titles(self):
        return [n.title for n, _ in stale(self.store.all(), TODAY)]

    def test_parses_iso_and_named_dates(self):
        d = dates_in("Free changes end Oct 15 and 2026-11-03, also Jan 4, 2027.", "2026-10-14")
        self.assertEqual(sorted(d), [dt.date(2026, 10, 15), dt.date(2026, 11, 3), dt.date(2027, 1, 4)])

    def test_flags_only_past_dates_without_expiry(self):
        self.store.add("Gala was Sat Oct 10 2026.", title="past", created="2026-10-01")
        self.store.add("Flight leaves Oct 18.", title="future", created="2026-10-01")
        self.store.add("Gala was Oct 10.", title="has expiry", expires="2026-12-01", created="2026-10-01")
        self.store.add("Likes short replies.", title="no date")
        self.assertEqual(self.titles(), ["past"])

    def test_note_with_past_and_future_dates_is_not_flagged(self):
        self.store.add("Booked 2026-09-01, trip is Nov 3.", title="mixed", created="2026-09-01")
        self.assertEqual(self.titles(), [])

    def test_superseded_notes_ignored(self):
        old = self.store.add("Return Oct 5.", title="old", created="2026-10-01")
        self.store.add("Return Oct 24.", title="new", supersedes=old.id, created="2026-10-01")
        self.assertEqual(self.titles(), [])


if __name__ == "__main__":
    unittest.main()
