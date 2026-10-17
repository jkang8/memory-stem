import datetime as dt
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as N

from memory_stem import usage


class UsageTest(unittest.TestCase):
    def test_bump_counts_and_report_finds_idle(self):
        d = Path(tempfile.mkdtemp())
        s = N(index_path=d / "index.sqlite")
        usage.bump(s, ["a", "b"])
        usage.bump(s, ["a"], "searched")
        data = usage.load(s)
        self.assertEqual(data["a"], {"recalled": 1, "searched": 1, "last": dt.date.today().isoformat()})
        today = dt.date(2026, 12, 1)
        old = lambda i: N(id=i, title=i, created="2026-09-01", active=lambda: True)
        data["b"]["last"] = "2026-09-15"
        rows = usage.report([old("a"), old("b"), old("c"), N(id="new", title="new", created="2026-11-25", active=lambda: True)],
                            {"a": {"last": "2026-11-20"}, "b": data["b"]}, today)
        self.assertEqual([r.split()[0] for r in rows], ["c", "b"])  # never used first; recent and new notes skipped
