import tempfile
import unittest
from pathlib import Path

from memory_stem import catalog
from memory_stem.embedder import Embedder
from memory_stem.index import Index
from memory_stem.notes import NoteStore
from memory_stem.search import Searcher


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = NoteStore(Path(self.tmp.name) / "Memory")

    def tearDown(self):
        self.tmp.cleanup()

    def test_lists_only_current_notes_grouped_by_tag(self):
        a = self.store.add("Hotel is Harbor Inn. Extra detail.", title="Trip hotel", tags=("travel",), expires="2999-01-01")
        old = self.store.add("Old claim.", title="Old", tags=("travel",))
        self.store.add("New claim.", title="New", tags=("travel",), supersedes=old.id)
        self.store.add("Likes short replies.", title="Style", tags=("preference",))
        text = catalog.render(self.store.all())
        self.assertIn("## travel", text)
        self.assertIn("## preference", text)
        self.assertIn("[[Trip hotel]] (expires 2999-01-01): Hotel is Harbor Inn.", text)
        self.assertIn("[[New]]", text)
        self.assertNotIn("[[Old]]", text)
        self.assertIn("3 current memories", text)
        self.assertEqual(a.id, self.store.get(a.id).id)

    def test_write_is_idempotent(self):
        self.store.add("One fact.", title="A")
        self.assertTrue(catalog.write(self.store.root, self.store.all()))
        self.assertFalse(catalog.write(self.store.root, self.store.all()))

    def test_index_file_is_never_a_memory_or_search_hit(self):
        self.store.add("Hotel is Harbor Inn.", title="Trip")
        catalog.write(self.store.root, self.store.all())
        self.assertTrue((self.store.root / catalog.NAME).exists())
        self.assertEqual([n.title for n in self.store.all()], ["Trip"])
        e = Embedder()
        idx = Index(Path(self.tmp.name) / "i.sqlite", e)
        idx.sync(self.store.all())
        self.assertEqual(len(Searcher(idx, e, 0.5).search("index generated memories", 3)), 0)

    def test_long_first_line_is_truncated(self):
        self.store.add("word " * 60, title="Long")
        line = [ln for ln in catalog.render(self.store.all()).splitlines() if "[[Long]]" in ln][0]
        self.assertTrue(line.endswith("…"))
        self.assertLess(len(line), 140)

    def test_titles_lists_current_only_and_truncates(self):
        old = self.store.add("Old claim.", title="Old")
        self.store.add("New claim.", title="New", supersedes=old.id)
        self.store.add("x", title="A very long title that goes on and on past the limit for sure")
        out = catalog.titles(self.store.all(), width=20)
        self.assertIn("- New", out)
        self.assertNotIn("- Old", out)
        self.assertTrue(any(ln.endswith("…") and len(ln) <= 24 for ln in out.splitlines()))


class HubsTest(unittest.TestCase):
    def test_one_page_per_subject_and_stale_pages_removed(self):
        import tempfile
        from pathlib import Path
        from memory_stem import catalog
        from memory_stem.notes import NoteStore
        d = Path(tempfile.mkdtemp())
        s = NoteStore(d)
        a = s.add("Sam does the taxes.", about=("Sam", "Acme LLC"))
        s.add("Alex lives in Portland.", about=("Alex",))
        self.assertEqual(catalog.write_hubs(d, s.all()), 3)
        self.assertIn(f"[[{a.title}]]", (d / "About" / "Sam.md").read_text())
        s.forget(a.id)
        catalog.write_hubs(d, s.all())
        self.assertFalse((d / "About" / "Sam.md").exists())
        self.assertTrue((d / "About" / "Alex.md").exists())
        self.assertEqual(len(s.all()), 2)  # hub pages are not memories


if __name__ == "__main__":
    unittest.main()
