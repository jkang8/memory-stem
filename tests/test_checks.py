import unittest

from memory_stem import checks

DESIGN = ("Memory system decision: Sam owns the memory. memory_stem stores one markdown note per memory in the vault's "
          "Memory folder; SQLite is only a disposable search index. No auto-capture. Drafts go to the inbox and are "
          "recalled only after Sam approves. A nightly dreaming cron proposes drafts.")
MNEMO = "Legacybase was deleted: plugin, config entry, pip packages and data directory are gone. A tar of its database is kept."
STYLE_OLD = "Reply style: concise, human-voiced, conversational replies; no recaps/menus unless asked."
STYLE_NEW = "Reply style: short and conversational, answer first, a little personality."


class ChecksTest(unittest.TestCase):
    def test_off_topic_supersede_is_flagged(self):
        w = checks.review_supersede(DESIGN, MNEMO, others=[], answers=[])
        self.assertTrue(any("different topic" in x for x in w))

    def test_ordinary_rewrite_is_not_flagged_as_off_topic(self):
        new = DESIGN + " Legacybase was removed; there is no fallback."
        self.assertEqual(checks.review_supersede(DESIGN, new, others=[], answers=[]), [])

    def test_rewrite_that_drops_eval_answer_is_flagged(self):
        w = checks.review_supersede(STYLE_OLD, STYLE_NEW, others=[], answers=["no recaps/menus unless asked"])
        self.assertTrue(any("eval answers" in x for x in w))

    def test_answer_still_in_another_note_is_not_flagged(self):
        bad = checks.broken_cases(STYLE_OLD, STYLE_NEW, others=["...no recaps/menus unless asked..."],
                                  answers=["no recaps/menus unless asked"])
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
