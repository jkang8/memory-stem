import tempfile
import unittest
from pathlib import Path

from memory_stem import aliases
from memory_stem.embedder import Embedder
from memory_stem.index import Index
from memory_stem.notes import NoteStore
from memory_stem.search import Searcher


class AliasTest(unittest.TestCase):
    def test_load_and_expand(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "Aliases.md").write_text("# Aliases\n- the shop = Acme Bike Repair\n* HQ = Head Office\nnot a rule\n")
            a = aliases.load(Path(tmp))
            self.assertEqual(a, {"the shop": "Acme Bike Repair", "hq": "Head Office"})
            self.assertEqual(aliases.expand("who owns the shop?", a), "who owns the shop? Acme Bike Repair")
            self.assertEqual(aliases.expand("tell me about Acme Bike Repair and the shop", a), "tell me about Acme Bike Repair and the shop")
            self.assertEqual(aliases.expand("hqtown email", a), "hqtown email")  # whole words only
            self.assertEqual(aliases.load(Path(tmp) / "nope"), {})

    def test_alias_makes_search_find_the_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = NoteStore(Path(tmp) / "Memory")
            e = Embedder()
            idx = Index(Path(tmp) / "i.sqlite", e)
            n = store.add("Acme Bike Repair holds the downtown storefront.", title="triplex")
            idx.sync(store.all())
            self.assertEqual(Searcher(idx, e, 0.5).search("tell me about the shop", 3), [])
            hits = Searcher(idx, e, 0.5, aliases={"the shop": "Acme Bike Repair"}).search("tell me about the shop", 3)
            self.assertEqual([h.id for h in hits], [n.id])


if __name__ == "__main__":
    unittest.main()
