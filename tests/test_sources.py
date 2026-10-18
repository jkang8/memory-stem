import tempfile
import unittest
from pathlib import Path

from memory_stem.notes import NoteStore
from memory_stem.sources import Recall, scaffolding


class RecallTest(unittest.TestCase):
    def test_vault_notes_are_recalled_and_credentials_listed_as_excluded(self):
        vault = Path(tempfile.mkdtemp())
        (vault / "Garden.md").write_text("Tomatoes go in the south bed every spring, after the last frost.\n")
        (vault / "Bank login.md").write_text("Username and recovery codes for the bank account live here.\n")
        rec = Recall(NoteStore(vault / "Memory"), vault)
        self.assertEqual([n.title for n in rec.all()], ["Garden"])
        self.assertEqual(rec.excluded, ["Bank login.md"])  # the maintenance skill prints this to audit the secret filter



class ScaffoldingTest(unittest.TestCase):
    def test_index_pages_dashboards_and_id_dumps_are_scaffolding(self):
        index = "# People\n- [[Alice Example]]\n- [[Bob Example]]\n- [[Carol Example]]\n- [Dan](https://example.com/dan)\n"
        dashboard = "# Home\n```dataview\nTABLE file.mtime FROM \"Projects\"\n```\n```tasks\nnot done\n```\nWelcome back.\n"
        ids = "Ref list\n" + "\n".join(f"AB12CD{i:04d}XY" for i in range(20))
        callouts = ("> ## `= choice(number(dateformat(date(now), \"H\")) < 12, \"Morning\", \"Evening\")`\n"
                    "```dataview\nTABLE status FROM #project\n```\n" + "> [!todo] Open items\n> [[Inbox]] · [[Today]] · [[Week]]\n" * 6)
        for body in (index, dashboard, ids, callouts):
            self.assertTrue(scaffolding(body), body[:30])

    def test_notes_with_prose_are_kept(self):
        prose = ("The garden plan: tomatoes go in the south bed after the last frost, peppers beside them. "
                 "See [[Seed list]] and [[Watering]] for details.\nCompost in March.\n")
        dashboard_with_writing = "```dataview\nLIST FROM #book\n```\n" + "I read slowly and keep notes on every chapter. " * 10
        for body in (prose, dashboard_with_writing):
            self.assertFalse(scaffolding(body), body[:30])

    def test_scaffolding_notes_are_not_recalled_and_not_counted_as_secrets(self):
        vault = Path(tempfile.mkdtemp())
        (vault / "Garden.md").write_text("Tomatoes go in the south bed every spring, after the last frost.\n")
        (vault / "Index.md").write_text("- [[Garden]]\n- [[Kitchen]]\n- [[Workshop]]\n- [[Car]]\n")
        rec = Recall(NoteStore(vault / "Memory"), vault)
        self.assertEqual([n.title for n in rec.all()], ["Garden"])
        self.assertEqual(rec.excluded, [])  # excluded audits the secret filter only


if __name__ == "__main__":
    unittest.main()
