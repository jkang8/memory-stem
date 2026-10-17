import datetime as dt
import tempfile
import unittest
from pathlib import Path

from memory_stem import timewindow as links
from memory_stem.notes import NoteStore

TODAY = dt.date(2026, 10, 16)


class TimeWindowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        s = NoteStore(Path(self.tmp.name) / "Memory")
        self.new = s.add("Maya is Sam's manager.", title="Maya", created="2026-10-15")
        self.sep = s.add("Flights for Boston trip 1.", title="Trip", created="2026-09-02")
        self.aug = s.add("Old fact.", title="Old", created="2026-08-10")
        self.notes = s.all()

    def tearDown(self):
        self.tmp.cleanup()

    def test_windows(self):
        self.assertEqual(links.window("what did we decide this week", TODAY), (dt.date(2026, 10, 9), TODAY))
        self.assertEqual(links.window("anything since september?", TODAY), (dt.date(2026, 9, 1), TODAY))
        self.assertEqual(links.window("what happened in august", TODAY), (dt.date(2026, 8, 1), dt.date(2026, 8, 31)))
        self.assertEqual(links.window("what happened in december", TODAY), (dt.date(2025, 12, 1), dt.date(2025, 12, 31)))
        self.assertIsNone(links.window("who is my manager", TODAY))
        self.assertIsNone(links.window("may I ask something", TODAY))  # "may" alone is not a month
        self.assertIsNone(links.window("what is the weather today", TODAY))  # not about our history
        self.assertEqual(links.window("what did we decide today", TODAY), (TODAY, TODAY))

    def test_extra_picks_range_newest_first_and_respects_room(self):
        ids = lambda q, have=(), room=4: [n.id for n in links.extra(q, self.notes, set(have), room, TODAY)]
        self.assertEqual(ids("anything since september"), [self.new.id, self.sep.id])
        self.assertEqual(ids("what happened in august"), [self.aug.id])
        self.assertEqual(ids("since september", room=1), [self.new.id])
        self.assertEqual(ids("since september", have=[self.new.id]), [self.sep.id])
        self.assertEqual(ids("who is my manager"), [])
