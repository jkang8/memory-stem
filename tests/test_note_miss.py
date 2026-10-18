import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

# provider imports Hermes; stub just enough to load it outside the gateway
m = types.ModuleType("agent.memory_provider")
m.MemoryProvider, m.RecallStatus, m.is_trivial_prompt = object, (lambda *a: a), (lambda q: False)
sys.modules.setdefault("agent", types.ModuleType("agent"))
sys.modules.setdefault("agent.memory_provider", m)

from memory_stem import provider, replay  # noqa: E402
from memory_stem.config import Settings  # noqa: E402
from memory_stem.tests.helpers import FakeEmbedder  # noqa: E402

FOUND = json.dumps({"results": [{"id": "hotel-booking", "text": "Hotel booked for the Denver trip."}]})


class NoteMissTest(unittest.TestCase):
    """A miss is the user's wording; cron prompts and subagent tasks are not, so they must not reach the replay log."""

    def miss_logged(self, **init_kwargs) -> bool:
        d = Path(tempfile.mkdtemp())
        (d / "Memory").mkdir()
        s = Settings(notes_dir=d / "Memory", index_path=d / "data" / "index.sqlite", model_cache=d)
        s.index_path.parent.mkdir()
        p = provider.VaultMemoryProvider(s)
        with mock.patch.object(provider, "make_embedder", lambda *a: FakeEmbedder()):
            p.initialize("s1", **init_kwargs)
        p._last_query, p._last_recalled = "which hotel did I book", set()
        p._note_miss(FOUND)
        return (s.index_path.parent / replay.LOG).exists()

    def test_primary_session_logs_a_miss(self):
        self.assertTrue(self.miss_logged(agent_context="primary"))
        self.assertTrue(self.miss_logged())  # Hermes builds without agent_context are primary

    def test_cron_and_subagents_do_not_log(self):
        self.assertFalse(self.miss_logged(agent_context="cron"))
        self.assertFalse(self.miss_logged(agent_context="subagent"))


if __name__ == "__main__":
    unittest.main()
