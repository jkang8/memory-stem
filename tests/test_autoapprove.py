import os
import tempfile
import unittest
from pathlib import Path

from memory_stem import autoapprove
from memory_stem.notes import NoteStore

DESIGN = ("Memory system decision: Sam owns the memory. memory_stem stores one markdown note per memory in the vault's "
          "Memory folder; SQLite is only a disposable search index. No auto-capture. A nightly dreaming cron proposes drafts.")


class AutoApproveTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.mem = self.tmp / "Memory"
        os.environ["VAULT_MEMORY_DIR"], os.environ["HERMES_HOME"] = str(self.mem), str(self.tmp / "h")
        self.store, self.inbox = NoteStore(self.mem), NoteStore(self.mem / "_inbox")

    def tearDown(self):
        os.environ.pop("VAULT_MEMORY_DIR")
        os.environ.pop("HERMES_HOME")

    def test_safe_drafts_are_approved_and_logged(self):
        old = self.store.add(DESIGN, title="design")
        self.inbox.add(DESIGN + " Drafts are approved automatically each night.", title="design v2",
                       supersedes=old.id, source="ms_draft", mark_old=False)
        self.inbox.add("Sam's gym is on Elm St.", title="gym", source="ms_draft", mark_old=False)
        out = autoapprove.run()
        self.assertIn("Saved 2", out)
        self.assertEqual(self.inbox.all(), [])
        self.assertFalse(self.store.get(old.id).active())
        self.assertTrue((self.tmp / "h" / "vault_memory" / autoapprove.LOG).exists())

    def test_off_topic_supersede_is_held(self):
        old = self.store.add(DESIGN, title="design")
        self.inbox.add("Legacybase was deleted along with its pip packages and data.", title="mnemo",
                       supersedes=old.id, source="ms_draft", mark_old=False)
        out = autoapprove.run()
        self.assertIn("HELD", out)
        self.assertTrue(self.store.get(old.id).active())
        self.assertEqual(len(self.inbox.all()), 1)

    def test_eval_drop_reverts_batch(self):
        old = self.store.add(DESIGN, title="design")
        self.inbox.add(DESIGN + " Small update.", title="design v2", supersedes=old.id, source="ms_draft", mark_old=False)
        scores = iter([19, 17])
        out = autoapprove.run(evaluate=lambda: next(scores))
        self.assertIn("reverted", out)
        self.assertTrue(self.store.get(old.id).active())

    def test_revert_restores_replaced_note(self):
        old = self.store.add(DESIGN, title="design")
        new = self.store.add(DESIGN + " v2", title="design v2", supersedes=old.id)
        msg = autoapprove.revert(self.store, new.id[-4:])
        self.assertIn("restored", msg)
        self.assertTrue(self.store.get(old.id).active())
        self.assertFalse(self.store.get(new.id).active())


if __name__ == "__main__":
    unittest.main()
