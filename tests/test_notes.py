import tempfile
import unittest
from pathlib import Path

from memory_stem.notes import CURRENT, FORGOTTEN, SUPERSEDED, NoteStore, check_secret, parse, render


class NotesTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = NoteStore(Path(self.dir.name) / "Memory")

    def tearDown(self):
        self.dir.cleanup()

    def test_roundtrip(self):
        n = self.store.add("Hotel is Harbor Inn.", title="Boston hotel", tags=("travel",))
        assert n.path is not None
        back = parse(render(n), n.path)
        self.assertEqual((back.id, back.body, back.status), (n.id, "Hotel is Harbor Inn.", CURRENT))
        self.assertIn("travel", back.tags)
        self.assertIn("memory", back.tags)

    def test_file_is_markdown_in_root(self):
        n = self.store.add("Prefers short replies.")
        self.assertTrue(n.path.exists() and n.path.suffix == ".md")
        self.assertTrue(n.path.read_text().startswith("---\n"))

    def test_supersede_keeps_old_and_links_both(self):
        old = self.store.add("Return is Oct 25.", title="Boston return")
        new = self.store.add("Return is Oct 24.", title="Boston return fixed", supersedes=old.id)
        o, n = self.store.get(old.id), self.store.get(new.id)
        self.assertEqual((o.status, o.superseded_by), (SUPERSEDED, new.id))
        self.assertEqual(n.supersedes, old.id)
        self.assertFalse(o.active())
        self.assertTrue(n.active())

    def test_restore_makes_a_superseded_note_current_again(self):
        old = self.store.add("Return is Oct 25.", title="Boston return")
        new = self.store.add("Return is Oct 24.", title="Boston return fixed", supersedes=old.id)
        self.store.forget(new.id)
        self.store.restore(old.id)
        self.assertEqual(self.store.reconcile(), 0)  # stable: nothing supersedes it again
        o = self.store.get(old.id)
        self.assertEqual((o.status, o.superseded_by), (CURRENT, ""))
        with self.assertRaises(KeyError):
            self.store.restore("nope")

    def test_supersede_unknown_id_raises_and_writes_nothing(self):
        with self.assertRaises(KeyError):
            self.store.add("x", supersedes="nope")
        self.assertEqual(self.store.all(), [])

    def test_forget_hides_but_keeps_file(self):
        n = self.store.add("Temporary thing.")
        self.store.forget(n.id)
        got = self.store.get(n.id)
        self.assertEqual(got.status, FORGOTTEN)
        self.assertFalse(got.active())
        self.assertTrue(got.path.exists())

    def test_expired_is_inactive(self):
        n = self.store.add("Old deadline.", expires="2020-01-01")
        self.assertFalse(self.store.get(n.id).active())

    def test_title_collision_gets_suffix(self):
        a = self.store.add("One.", title="Same")
        b = self.store.add("Two.", title="Same")
        self.assertNotEqual(a.path, b.path)
        self.assertEqual(len(self.store.all()), 2)

    def test_bad_filename_chars_stripped(self):
        n = self.store.add("Body.", title='a/b:c*d?"e')
        self.assertTrue(n.path.exists())
        self.assertEqual(n.path.parent, self.store.root)

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            self.store.add("   ")

    def test_secret_guard(self):
        for bad in ("password: hunter22222", "token=abcdef123456", "key sk-abcdefghijklmnopqrstuv",
                    "-----BEGIN PRIVATE KEY-----", "card 4111 1111 1111 1111"):
            with self.assertRaises(ValueError, msg=bad):
                check_secret(bad)
        check_secret("Bank login is in the Hermes vault; password stored there.")
        check_secret("Entity number 200012345678 is the state file number.")  # 12 digits, not a card
        self.assertEqual(self.store.all(), [])

    def test_non_notes_and_broken_files_ignored(self):
        self.store.add("Real.")
        (self.store.root / "README.md").write_text("no frontmatter here")
        (self.store.root / "bad.md").write_bytes(b"\xff\xfe---")
        self.assertEqual(len(self.store.all()), 1)

    def test_fingerprint_changes_on_write(self):
        a = self.store.fingerprint()
        self.store.add("Something.")
        self.assertNotEqual(a, self.store.fingerprint())

    def test_yaml_tag_list_parses(self):
        p = self.store.root
        p.mkdir(parents=True)
        (p / "hand.md").write_text("---\nid: h1\ncreated: 2026-01-01\ntags: [a, b]\n---\nHand written.\n")
        n = self.store.get("h1")
        self.assertEqual((n.body, n.tags), ("Hand written.", ("a", "b")))


if __name__ == "__main__":
    unittest.main()
