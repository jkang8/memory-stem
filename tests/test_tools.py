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
    return store, Tools(store, Searcher(idx, e, 0.5), lambda: idx.sync(store.all()), writable)


class ToolsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()

    def call(self, tools, name, **a):
        return json.loads(tools.handle(name, a))

    def test_schemas_are_valid_function_specs(self):
        for s in SCHEMAS:
            self.assertEqual(set(s), {"name", "description", "parameters"})
            self.assertEqual(s["parameters"]["type"], "object")

    def test_remember_then_search(self):
        _, t = make(self.tmp.name)
        r = self.call(t, "ms_remember", content="Bus stop is Market and 55th.", title="bus")
        self.assertTrue(r["ok"])
        found = self.call(t, "ms_search", query="which bus stop")
        self.assertEqual([x["id"] for x in found["results"]], [r["id"]])

    def test_correction_flow(self):
        _, t = make(self.tmp.name)
        a = self.call(t, "ms_remember", content="Return flight Oct 25.", title="ret")
        b = self.call(t, "ms_remember", content="Return flight Oct 24.", title="ret2", supersedes=a["id"])
        res = self.call(t, "ms_search", query="return flight")["results"]
        self.assertEqual([x["id"] for x in res], [b["id"]])

    def test_errors_are_json_not_exceptions(self):
        _, t = make(self.tmp.name)
        self.assertFalse(self.call(t, "ms_remember", content="password: hunter22222")["ok"])
        self.assertFalse(self.call(t, "ms_remember", content="x", supersedes="nope")["ok"])
        self.assertFalse(self.call(t, "ms_forget", id="nope")["ok"])
        self.assertFalse(self.call(t, "ms_remember")["ok"])          # missing arg
        self.assertFalse(self.call(t, "vm_nothing")["ok"])           # unknown tool

    def test_read_only_context_cannot_write(self):
        store, t = make(self.tmp.name, writable=False)
        self.assertFalse(self.call(t, "ms_remember", content="x")["ok"])
        self.assertEqual(store.all(), [])


if __name__ == "__main__":
    unittest.main()


class BasisTest(unittest.TestCase):
    def test_basis_round_trips_and_drafts_default_to_inferred(self):
        import json
        import tempfile
        from pathlib import Path

        from memory_stem.notes import NoteStore
        d = tempfile.mkdtemp()
        store, t = make(d)
        r = json.loads(t.handle("ms_remember", {"content": "Harbor Inn booked Oct 18-23.", "basis": "read: Harbor Inn confirmation, 2026-10-15"}))
        self.assertEqual(store.get(r["id"]).basis, "read: Harbor Inn confirmation, 2026-10-15")
        dr = json.loads(t.handle("ms_draft", {"content": "Sam probably prefers aisle seats."}))
        self.assertEqual(NoteStore(Path(d) / "Memory" / "_inbox").get(dr["id"]).basis, "inferred")


class AboutVerifyTest(unittest.TestCase):
    def test_about_round_trips_carries_over_and_verify_stamps(self):
        import datetime as dt
        d = tempfile.mkdtemp()
        store, t = make(d)
        r = json.loads(t.handle("ms_remember", {"content": "Sam does the taxes.", "about": ["Sam", "Acme LLC"]}))
        n = store.get(r["id"])
        self.assertEqual(n.about, ("Sam", "Acme LLC"))
        self.assertNotIn("Sam, Acme", n.search_text())  # about is keyword-only, not embedded
        r2 = json.loads(t.handle("ms_remember", {"content": "Sam at Acme Tax does the taxes.", "supersedes": n.id}))
        self.assertEqual(store.get(r2["id"]).about, n.about)              # correction keeps the subjects
        old = store.get(r2["id"])
        self.assertEqual(old.confirmed(), old.created)
        v = json.loads(t.handle("ms_verify", {"id": r2["id"]}))
        self.assertEqual(v["verified"], dt.date.today().isoformat())
        self.assertEqual(store.get(r2["id"]).body, old.body)              # verify changes no content
        self.assertFalse(json.loads(t.handle("ms_verify", {"id": n.id}))["ok"])  # superseded notes can't be verified
        _, ro = make(d, writable=False)
        self.assertFalse(json.loads(ro.handle("ms_verify", {"id": r2["id"]}))["ok"])
