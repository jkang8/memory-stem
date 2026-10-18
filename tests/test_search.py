import tempfile
import unittest
from pathlib import Path

from memory_stem.embedder import Embedder
from memory_stem.index import Index, fts_query
from memory_stem.notes import NoteStore
from memory_stem.search import Searcher

from .helpers import FakeEmbedder


def build(tmp, embedder):
    store = NoteStore(Path(tmp) / "Memory")
    idx = Index(Path(tmp) / "i.sqlite", embedder)
    return store, idx, Searcher(idx, embedder, min_cosine=0.5)


class SearchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def test_fts_query_drops_stopwords(self):
        self.assertEqual(fts_query("Where is the hotel?"), '"hotel"')
        self.assertEqual(fts_query("the and of"), "")

    def test_very_long_query_does_not_break_fts(self):
        store, idx, s = build(self.tmp.name, Embedder())
        a = store.add("Hotel is Harbor Inn.", title="trip")
        idx.sync(store.all())
        long_q = "hotel " + " ".join(f"word{i}longer" for i in range(600))  # >2000 chars of distinct terms
        self.assertGreater(len(long_q), 2000)
        self.assertEqual([h.id for h in s.search(long_q, 3)], [a.id])

    def test_semantic_finds_paraphrase_without_shared_words(self):
        store, idx, s = build(self.tmp.name, FakeEmbedder())
        a = store.add("Harbor Inn is booked.", title="trip")        # axis 0 via 'pod'
        store.add("Bus to work leaves at nine.", title="bus")   # axis 1
        idx.sync(store.all())
        hits = s.search("where do I stay", limit=3)             # 'stay' -> axis 0, no keyword overlap
        self.assertEqual([h.id for h in hits], [a.id])

    def test_semantic_cutoff_drops_unrelated_keyword_hit(self):
        store, idx, s = build(self.tmp.name, FakeEmbedder())
        store.add("Harbor Inn is booked and I work late.", title="trip")
        idx.sync(store.all())
        # 'late' matches by keyword, but the query vector (tax axis) is unrelated -> dropped
        self.assertEqual(s.search("tax late", limit=3), [])

    def test_query_prefix_only_applies_to_bge_queries(self):
        from memory_stem.embedder import FastEmbedder

        seen = []

        class Spy(FastEmbedder):
            def __init__(self, name):
                self.name = name

            def embed(self, texts):
                seen.extend(texts)
                return [[1.0]]

        Spy("BAAI/bge-small-en-v1.5").embed_query("hello")
        Spy("some/other-model").embed_query("hello")
        self.assertTrue(seen[0].startswith("Represent this sentence"))
        self.assertEqual(seen[1], "hello")

    def test_keyword_only_when_no_embedder(self):
        store, idx, s = build(self.tmp.name, Embedder())
        a = store.add("Hotel is Harbor Inn.", title="trip")
        store.add("Bus is route 7.", title="bus")
        idx.sync(store.all())
        self.assertEqual([h.id for h in s.search("which hotel", limit=3)], [a.id])
        self.assertEqual(s.search("zzzz", limit=3), [])

    def test_superseded_and_forgotten_leave_the_index(self):
        store, idx, s = build(self.tmp.name, Embedder())
        old = store.add("Return is Oct 25.", title="ret")
        idx.sync(store.all())
        self.assertEqual(len(s.search("return", 3)), 1)
        new = store.add("Return is Oct 24.", title="ret2", supersedes=old.id)
        idx.sync(store.all())
        self.assertEqual([h.id for h in s.search("return", 3)], [new.id])
        store.forget(new.id)
        idx.sync(store.all())
        self.assertEqual(s.search("return", 3), [])

    def test_sync_is_incremental(self):
        store, idx, _ = build(self.tmp.name, Embedder())
        store.add("One thing.", title="a")
        self.assertEqual(idx.sync(store.all()), (1, 0))
        self.assertEqual(idx.sync(store.all()), (0, 0))
        store.add("Another thing.", title="b")
        self.assertEqual(idx.sync(store.all()), (1, 0))

    def test_index_rebuilds_after_deletion(self):
        store, idx, _s = build(self.tmp.name, FakeEmbedder())
        a = store.add("Harbor Inn is booked.", title="trip")
        idx.sync(store.all())
        (Path(self.tmp.name) / "i.sqlite").unlink()
        idx2 = Index(Path(self.tmp.name) / "i.sqlite", FakeEmbedder())
        idx2.sync(store.all())
        self.assertEqual([h.id for h in Searcher(idx2, FakeEmbedder(), 0.5).search("stay", 3)], [a.id])

    def test_changed_model_name_clears_old_vectors(self):
        store, idx, _ = build(self.tmp.name, FakeEmbedder())
        store.add("Harbor Inn is booked.", title="trip")
        idx.sync(store.all())

        class Other(FakeEmbedder):
            name = "other-model"

        idx2 = Index(Path(self.tmp.name) / "i.sqlite", Other())
        self.assertEqual(idx2.sync(store.all()), (1, 0))  # re-embedded, not skipped as unchanged

    def test_edit_outside_the_agent_is_picked_up(self):
        store, idx, s = build(self.tmp.name, Embedder())
        n = store.add("Hotel is Harbor Inn.", title="trip")
        idx.sync(store.all())
        assert n.path is not None
        text = n.path.read_text().replace("Harbor Inn", "Lakeside Lodge")
        n.path.write_text(text)
        import os
        os.utime(n.path, (n.mtime + 5, n.mtime + 5))
        idx.sync(store.all())
        self.assertEqual(len(s.search("lakeside", 3)), 1)
        self.assertEqual(s.search("harbor", 3), [])


if __name__ == "__main__":
    unittest.main()
