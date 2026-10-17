import tempfile
import unittest
from pathlib import Path

import numpy as np

from memory_stem.embedder import Embedder
from memory_stem.index import Index
from memory_stem.notes import NoteStore
from memory_stem.search import Searcher


class Fixed(Embedder):
    """Query vectors are chosen so cosine to the note vector is exactly the value we want."""
    name = "fixed"

    def __init__(self, cos):
        self.cos = cos

    def embed(self, texts):
        out = []
        for t in texts:
            if t.startswith("QUERY"):
                out.append([self.cos, float(np.sqrt(1 - self.cos ** 2))])
            else:
                out.append([1.0, 0.0])
        return np.array(out, dtype="float32")


def run(cos, query):
    with tempfile.TemporaryDirectory() as tmp:
        store = NoteStore(Path(tmp) / "Memory")
        e = Fixed(cos)
        idx = Index(Path(tmp) / "i.sqlite", e)
        store.add("Hotel is Harbor Inn.", title="trip")
        idx.sync(store.all())
        return len(Searcher(idx, e, min_cosine=0.5, strong_cosine=0.7).search(query, 3))


class BandTest(unittest.TestCase):
    def test_strong_passes_without_keyword(self):
        self.assertEqual(run(0.8, "QUERY zzzz"), 1)

    def test_middle_band_needs_keyword(self):
        self.assertEqual(run(0.6, "QUERY zzzz"), 0)
        self.assertEqual(run(0.6, "QUERY hotel"), 1)

    def test_below_floor_dropped_even_with_keyword(self):
        self.assertEqual(run(0.4, "QUERY hotel"), 0)


if __name__ == "__main__":
    unittest.main()
