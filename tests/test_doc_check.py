import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

# scripts/ is not a package: load the checker by path
_spec = importlib.util.spec_from_file_location("doc_check", Path(__file__).parent.parent / "scripts" / "doc_check.py")
doc_check = sys.modules["doc_check"] = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(doc_check)


def repo(files: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp())
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    return root


class BudgetTest(unittest.TestCase):
    def test_over_budget_fails_and_at_budget_passes(self):
        root = repo({"README.md": "x\n" * 150, "CLAUDE.md": "x\n" * 101, "docs/decisions/0001-a.md": "x\n" * 16})
        got = doc_check.check(root)
        self.assertEqual(len(got), 2)
        self.assertTrue(any(h.startswith("CLAUDE.md: 101 lines, budget 100") for h in got), got)
        self.assertTrue(any(h.startswith("docs/decisions/0001-a.md: 16 lines, budget 15") for h in got), got)


class StaleReferenceTest(unittest.TestCase):
    def test_missing_repo_paths_and_modules_fail(self):
        root = repo({"notes.py": "", "scripts/gate.sh": "", "README.md":
                     "Run `scripts/gate.sh`, then `scripts/gone.sh`.\n"
                     "Search lives in `search.py`; see `python -m memory_stem.notes` and `python -m memory_stem.gone`.\n"})
        got = doc_check.check(root)
        self.assertEqual(sorted(got), ["README.md:1: `scripts/gone.sh` does not exist",
                                       "README.md:2: `python -m memory_stem.gone` names no module",
                                       "README.md:2: `search.py` does not exist"])

    def test_paths_in_fenced_blocks_are_checked(self):
        root = repo({"scripts/gate.sh": "", "README.md": "```sh\nscripts/missing.sh --flag\n```\n"})
        self.assertEqual(doc_check.check(root), ["README.md:2: `scripts/missing.sh` does not exist"])

    def test_bare_names_resolve_next_to_the_doc_or_at_the_root(self):
        root = repo({"notes.py": "", "scripts/run.sh": "", "scripts/run.md": "`run.sh` uses `notes.py`, not `gone.sh`.\n"})
        self.assertEqual(doc_check.check(root), ["scripts/run.md:1: `gone.sh` does not exist"])

    def test_a_folder_not_in_the_repo_is_treated_as_outside_it(self):
        # known gap: if a whole top-level folder is deleted, paths under it are no longer checked
        self.assertEqual(doc_check.check(repo({"README.md": "See `Memory/_evals/tuned.json`.\n"})), [])

    def test_outside_repo_and_symbol_references_pass(self):
        root = repo({"tests/helpers.py": "", "README.md":
                     "Notes go in `Memory/_evals/` and `Profile.md`; config is `~/.hermes/.env` or `$VAULT_DIR/Memory`.\n"
                     "Pages are `About/<subject>.md`, frozen sets `heldout*.json`. Fakes: `tests/helpers.FakeEmbedder`.\n"
                     "```sh\npython -m unittest discover -s memory_stem/tests -t .\n```\n"})
        self.assertEqual(doc_check.check(root), [])


if __name__ == "__main__":
    unittest.main()
