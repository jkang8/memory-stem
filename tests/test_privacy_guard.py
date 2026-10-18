import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# scripts/ is not a package: load the guard by path
_REPO = Path(__file__).parent.parent
_spec = importlib.util.spec_from_file_location("privacy_guard", _REPO / "scripts" / "privacy_guard.py")
assert _spec is not None and _spec.loader is not None
guard = sys.modules["privacy_guard"] = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


def tree(files: dict[str, str]) -> Path:
    root = Path(tempfile.mkdtemp())
    shutil.copy(_REPO / "notes.py", root / "notes.py")  # the guard reuses its secret pattern
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    return root


class FilesTest(unittest.TestCase):
    def test_lists_repo_files_including_dot_folders_but_not_caches_or_binaries(self):
        root = tree({"a.py": "", "pkg/b.md": "", ".github/workflows/ci.yml": "", "__pycache__/a.pyc": "", "x.pyc": "",
                     ".git/config": "", "sub/.git": "gitdir: /elsewhere/worktrees/x", "idx.sqlite": "", "logo.png": "", ".venv/lib/c.py": "", "node_modules/d.js": ""})
        got = sorted(f.relative_to(root).as_posix() for f in guard.files(root))
        self.assertEqual(got, [".github/workflows/ci.yml", "a.py", "notes.py", "pkg/b.md"])


class ScanTest(unittest.TestCase):
    def test_flags_emails_secrets_and_denylisted_terms(self):
        key = "api" + "_key = " + "abcdef123456789"  # built here so this file isn't itself a hit
        addr = "someone" + "@" + "gmail.com"  # built here so this file isn't itself a hit
        root = tree({"doc.md": f"write to {addr}\nnoreply@example.com is fine\nnothing here\n",
                     "code.py": key + "\n", "tests/t.py": key + "\n", "notes2.md": "Visit the Springfield office\n"})
        hits = guard.scan(root, ["springfield"])
        self.assertIn(f"doc.md:1: email {addr}", hits)
        self.assertNotIn("doc.md:2", " ".join(hits))
        self.assertIn("code.py:1: looks like a secret", hits)
        self.assertFalse([h for h in hits if h.startswith("tests/")])  # tests hold fake secrets on purpose
        self.assertIn("notes2.md:1: denylisted term", hits)

    def test_clean_tree_has_no_hits(self):
        self.assertEqual(guard.scan(tree({"ok.md": "nothing personal\n"}), ["springfield"]), [])


if __name__ == "__main__":
    unittest.main()
