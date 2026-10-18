import json
import tempfile
import unittest
from pathlib import Path

from memory_stem.embedder import Embedder
from memory_stem.index import Index
from memory_stem.notes import NoteStore, parse, render
from memory_stem.search import Searcher
from memory_stem.tools import Tools


class QuestionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = NoteStore(Path(self.tmp.name) / "Memory")

    def tearDown(self):
        self.tmp.cleanup()

    def test_roundtrip_with_colons_and_quotes(self):
        n = self.store.add("Hotel is Harbor Inn.", title="trip", questions=('Where am I staying: which hotel?', 'What\'s my "hotel"?'))
        back = parse(render(n), n.path)
        self.assertEqual(back.questions, ("Where am I staying: which hotel?", "What's my 'hotel'?"))
        self.assertEqual(back.tags, ("memory",))

    def test_questions_make_note_findable_by_keyword(self):
        e = Embedder()
        idx = Index(Path(self.tmp.name) / "i.sqlite", e)
        a = self.store.add("Harbor Inn is booked.", title="trip", questions=("Where am I lodging?",))
        idx.sync(self.store.all())
        self.assertEqual([h.id for h in Searcher(idx, e, 0.5).search("lodging", 3)], [a.id])

    def test_tools_accept_questions(self):
        e = Embedder()
        idx = Index(Path(self.tmp.name) / "i.sqlite", e)
        t = Tools(self.store, Searcher(idx, e, 0.5), lambda: idx.sync(self.store.all()))
        r = json.loads(t.handle("ms_remember", {"content": "Harbor Inn.", "title": "x", "questions": ["Where do I sleep?"]}))
        self.assertTrue(r["ok"])
        self.assertEqual(self.store.get(r["id"]).questions, ("Where do I sleep?",))
        d = json.loads(t.handle("ms_draft", {"content": "Draft fact.", "title": "y", "questions": ["What draft?"]}))
        self.assertTrue(d["ok"])


if __name__ == "__main__":
    unittest.main()
