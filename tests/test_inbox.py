import json
import tempfile
import unittest
from pathlib import Path

from memory_stem.embedder import Embedder
from memory_stem.index import Index
from memory_stem.notes import NoteStore
from memory_stem.search import Searcher
from memory_stem.tools import SCHEMAS, Tools


def make(tmp, writable=True):
    store = NoteStore(Path(tmp) / "Memory")
    e = Embedder()
    idx = Index(Path(tmp) / "i.sqlite", e)
    return store, idx, Tools(store, Searcher(idx, e, 0.5), lambda: (store.reconcile(), idx.sync(store.all())), writable)


class InboxTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, t, name, **a):
        return json.loads(t.handle(name, a))

    def test_schema_names(self):
        self.assertEqual({s["name"] for s in SCHEMAS}, {"ms_remember", "ms_search", "ms_forget", "ms_draft", "ms_review", "ms_verify"})

    def test_draft_is_not_recalled_until_approved(self):
        store, _, t = make(self.tmp.name)
        d = self.call(t, "ms_draft", content="Hotel is Harbor Inn.", title="trip")
        self.assertTrue(d["ok"])
        self.assertEqual(self.call(t, "ms_search", query="hotel")["results"], [])
        self.assertEqual(store.all(), [])
        self.assertTrue((Path(self.tmp.name) / "Memory/_inbox/trip.md").exists())
        self.assertTrue(self.call(t, "ms_review", action="approve", id=d["id"])["ok"])
        self.assertEqual([r["id"] for r in self.call(t, "ms_search", query="hotel")["results"]], [d["id"]])
        self.assertEqual(self.call(t, "ms_review", action="list")["drafts"], [])

    def test_approve_by_last_four_and_all(self):
        _, _, t = make(self.tmp.name)
        a = self.call(t, "ms_draft", content="Alpha fact.", title="a")
        self.call(t, "ms_draft", content="Beta fact.", title="b")
        self.assertTrue(self.call(t, "ms_review", action="approve", id=a["id"][-4:])["ok"])
        self.assertEqual(len(self.call(t, "ms_review", action="list")["drafts"]), 1)
        self.assertTrue(self.call(t, "ms_review", action="approve", id="all")["ok"])
        self.assertEqual(len(self.call(t, "ms_search", query="fact")["results"]), 2)

    def test_reject_deletes_draft(self):
        store, _, t = make(self.tmp.name)
        d = self.call(t, "ms_draft", content="Wrong guess.", title="w")
        self.call(t, "ms_review", action="reject", id=d["id"])
        self.assertFalse((Path(self.tmp.name) / "Memory/_inbox/w.md").exists())
        self.assertEqual(self.call(t, "ms_search", query="guess")["results"], [])

    def test_approved_draft_retires_the_note_it_supersedes(self):
        store, _, t = make(self.tmp.name)
        old = self.call(t, "ms_remember", content="Return flight Oct 25.", title="ret")
        d = self.call(t, "ms_draft", content="Return flight Oct 24.", title="ret2", supersedes=old["id"])
        self.assertEqual(store.get(old["id"]).status, "current")  # untouched while it is only a draft
        self.call(t, "ms_review", action="approve", id=d["id"])
        self.assertEqual(store.get(old["id"]).status, "superseded")
        self.assertEqual([r["id"] for r in self.call(t, "ms_search", query="return flight")["results"]], [d["id"]])

    def test_draft_moved_by_hand_still_retires_old(self):
        store, _, t = make(self.tmp.name)
        old = self.call(t, "ms_remember", content="Return flight Oct 25.", title="ret")
        d = self.call(t, "ms_draft", content="Return flight Oct 24.", title="ret2", supersedes=old["id"])
        (Path(self.tmp.name) / "Memory/_inbox/ret2.md").rename(Path(self.tmp.name) / "Memory/ret2.md")
        res = self.call(t, "ms_search", query="return flight")["results"]
        self.assertEqual([r["id"] for r in res], [d["id"]])

    def test_bad_input_is_json_error(self):
        _, _, t = make(self.tmp.name)
        self.assertFalse(self.call(t, "ms_draft", content="password: hunter22222")["ok"])
        self.assertFalse(self.call(t, "ms_draft", content="x", supersedes="nope")["ok"])
        self.assertFalse(self.call(t, "ms_review", action="approve", id="zzzz")["ok"])
        self.assertFalse(self.call(t, "ms_review", action="approve")["ok"])
        self.assertFalse(self.call(t, "ms_review", action="explode")["ok"])

    def test_read_only_context_can_draft_but_not_approve(self):
        store, _, t = make(self.tmp.name, writable=False)
        d = self.call(t, "ms_draft", content="Cron noticed a thing.", title="c")
        self.assertTrue(d["ok"])
        self.assertFalse(self.call(t, "ms_review", action="approve", id=d["id"])["ok"])
        self.assertTrue(self.call(t, "ms_review", action="list")["ok"])


if __name__ == "__main__":
    unittest.main()
