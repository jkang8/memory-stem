import sys
import tempfile
import types
import unittest
from pathlib import Path

# provider imports Hermes; stub just enough to load it outside the gateway
m = types.ModuleType("agent.memory_provider")
m.MemoryProvider, m.RecallStatus, m.is_trivial_prompt = object, (lambda *a: a), (lambda q: False)
sys.modules.setdefault("agent", types.ModuleType("agent"))
sys.modules.setdefault("agent.memory_provider", m)

from memory_stem import recall as provider  # noqa: E402  (rules moved to recall.py)
from memory_stem.config import Settings  # noqa: E402
from memory_stem.notes import NoteStore  # noqa: E402


class ProfileTest(unittest.TestCase):
    def test_profile_bullets_load_and_are_not_a_memory(self):
        d = Path(tempfile.mkdtemp()) / "Memory"
        d.mkdir()
        (d / "Profile.md").write_text("---\ntags:\n  - profile\n---\nIntro line.\n\n- Lives in Springfield.\n- Office 100 Main St.\n")
        s = Settings(notes_dir=d, index_path=d / "i.sqlite", model_cache=d)
        out = provider.profile(s)
        self.assertIn("100 Main", out)
        self.assertNotIn("Intro line", out)
        self.assertEqual(NoteStore(d).all(), [])

    def test_missing_profile_is_empty(self):
        d = Path(tempfile.mkdtemp())
        self.assertEqual(provider.profile(Settings(notes_dir=d, index_path=d / "i", model_cache=d)), "")


if __name__ == "__main__":
    unittest.main()


class UpcomingTest(unittest.TestCase):
    def test_only_near_future_events_surface_in_date_order(self):
        import datetime as dt

        from memory_stem.notes import NoteStore
        d = Path(tempfile.mkdtemp())
        st = NoteStore(d)
        t = dt.date.today()
        day = lambda n: (t + dt.timedelta(n)).isoformat()  # relative: active() checks expiry against the real clock
        far = st.add("Trip to Tokyo in March.", title="tokyo", tags=("event",), expires=day(150))
        st.add("Gala Saturday 6pm.", title="gala", tags=("event",), expires=day(3))
        st.add("Taxes due today.", title="taxes", tags=("event",), expires=day(1))
        st.add("Not an event but dated.", title="plain", expires=day(2))
        got = [n.title for n in provider.upcoming(st.all(), today=t)]
        self.assertEqual(got, ["taxes", "gala"])
        self.assertNotIn(far.title, got)


class ContentlessTest(unittest.TestCase):
    def test_go_on_replies_skip_search_but_real_questions_do_not(self):
        skip = ["Go", "Let's go", "Approve", "Yes", "Ok", "?", "Vo", "Approve but", "k its in", "Yes. And", "Go!"]
        keep = ["Room 12", "Delete the old plugin", "Don't hide it", "restart the router", "Ok and let's also research accounts receivables",
                "Approve but make it read less llmey", "Who is Priya", "3k and under", "Submitted my taxes"]
        for s in skip:
            self.assertTrue(provider.contentless(s), s)
        for s in keep:
            self.assertFalse(provider.contentless(s), s)


class ContentlessCodesTest(unittest.TestCase):
    def test_pasted_codes_urls_and_hashes_skip_search(self):
        skip = [
            "4/0AeanS0ZqX8vLk2mTq9Rw7yHb3NcPdUe5FgJhKs1LmNoPq-rStUvWxYz0123AbCdEf",  # OAuth code
            "http://localhost:8080/callback?code=4/0AeanS0ZqX8vLk2m&scope=email%20openid&state=a1b2c3d4e5#state",
            "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",  # sha256
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0",  # base64 / JWT
            "code=4/0AeanS0ZqX8vLk2m&state=a1b2c3d4e5",
            "#state",
            "ok 4/0AeanS0ZqX8vLk2mTq9Rw7yHb3Nc",
            "https://example.com/oauth?x=1",
        ]
        keep = ["Where is order 113-4455667-8899001", "Look up tracking 1Z999AA10123456784", "relationship counseling notes",
                "iPhone 15 battery", "Taxes due 2026-04-15", "what is at https://example.com/pricing for the plan"]
        for s in skip:
            self.assertTrue(provider.contentless(s), s)
        for s in keep:
            self.assertFalse(provider.contentless(s), s)


class HabituateTest(unittest.TestCase):
    def test_once_a_day_even_when_close(self):
        import datetime as dt
        from types import SimpleNamespace as N
        gala = N(id="g", expires="2026-10-18")
        trip = N(id="t", expires="2026-10-26")
        seen, d15 = {}, dt.date(2026, 10, 15)
        self.assertEqual([n.id for n in provider.habituate([gala, trip], seen, d15)], ["g", "t"])
        self.assertEqual(provider.habituate([gala, trip], seen, d15), [])          # second turn same day: quiet
        d17 = dt.date(2026, 10, 17)
        self.assertEqual([n.id for n in provider.habituate([gala, trip], seen, d17)], ["g", "t"])  # new day
        self.assertEqual(provider.habituate([gala, trip], seen, d17), [])          # gala is today: still once

    def test_when_counts_to_the_event_not_expires(self):
        import datetime as dt

        from memory_stem.recall import when
        d17 = dt.date(2026, 10, 17)
        self.assertEqual(when("2026-10-18", d17), "today")
        self.assertEqual(when("2026-10-19", d17), "tomorrow")
        self.assertEqual(when("2026-10-24", d17), "in 6 days")


class StatusLabelTest(unittest.TestCase):
    def test_titles_shown_trimmed_and_counted(self):
        self.assertEqual(provider.status_label([]), "Vault memory")
        self.assertEqual(provider.status_label(["Gala", "Hotel"]), "Vault memory: Gala · Hotel")
        self.assertEqual(provider.status_label(["Gala", "Hotel", "Bus"]), "Vault memory: Gala · Hotel +1 more")
        self.assertEqual(provider.status_label(["x" * 40]), "Vault memory: " + "x" * 29 + "…")
