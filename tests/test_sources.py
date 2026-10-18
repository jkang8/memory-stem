import tempfile
import unittest
from pathlib import Path

from memory_stem.notes import NoteStore
from memory_stem.sources import Recall


class RecallTest(unittest.TestCase):
    def test_vault_notes_are_recalled_and_credentials_listed_as_excluded(self):
        vault = Path(tempfile.mkdtemp())
        (vault / "Garden.md").write_text("Tomatoes go in the south bed every spring, after the last frost.\n")
        (vault / "Bank login.md").write_text("Username and recovery codes for the bank account live here.\n")
        rec = Recall(NoteStore(vault / "Memory"), vault)
        self.assertEqual([n.title for n in rec.all()], ["Garden"])
        self.assertEqual(rec.excluded, ["Bank login.md"])  # the maintenance skill prints this to audit the secret filter


if __name__ == "__main__":
    unittest.main()
