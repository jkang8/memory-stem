"""Fail if the repo contains personal data. The repo is public; personal terms live outside it.

Checks tracked text files for: emails other than noreply, secrets (notes.check_secret), and any term
listed in $MEMORY_STEM_DENYLIST (a local file, one term per line, never committed).
usage: python scripts/privacy_guard.py [repo_dir] [--text file ...]   (--text: check only those files, e.g. a PR body)
"""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
ALLOWED_EMAIL = re.compile(r"(noreply|example\.(com|org)|users\.noreply\.github\.com)", re.I)


def files(root: Path) -> list[Path]:
    """Tracked plus untracked-but-not-ignored, so a new file is checked before it is committed."""
    out = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                         capture_output=True, text=True).stdout.split("\0")
    return [root / f for f in dict.fromkeys(out) if f and not f.endswith((".png", ".jpg", ".sqlite"))]


def denylist() -> list[str]:
    p = os.environ.get("MEMORY_STEM_DENYLIST")
    if not p or not Path(p).expanduser().exists():
        return []
    return [t.strip() for t in Path(p).expanduser().read_text().splitlines() if t.strip() and not t.startswith("#")]


def _secret_re(root: Path):
    # by path, not `import memory_stem`: a worktree's folder is named after its branch
    spec = importlib.util.spec_from_file_location("_ms_notes", root / "notes.py")
    notes = sys.modules["_ms_notes"] = importlib.util.module_from_spec(spec)  # dataclasses look the module up
    spec.loader.exec_module(notes)
    return notes._SECRET


def check(where: str, text: str, pats: list, secret, code: bool = True) -> list[str]:
    hits = []
    for n, line in enumerate(text.splitlines(), 1):
        at = f"{where}:{n}"
        hits += [f"{at}: email {e}" for e in EMAIL.findall(line) if not ALLOWED_EMAIL.search(e)]
        if secret.search(line) and not (code and ("re.compile" in line or line.lstrip().startswith(("r\"", "r'", "#")))):
            hits.append(f"{at}: looks like a secret")
        hits += [f"{at}: denylisted term" for p in pats if p.search(line)]
    return hits


def scan(root: Path, terms: list[str], texts: list[Path] = ()) -> list[str]:
    """Repo files under root, or with texts, just those files (a PR title, body or commit messages)."""
    secret = _secret_re(root)
    pats = [re.compile(r"\b" + re.escape(t) + r"\b", re.I) for t in terms]
    if texts:
        return [h for f in texts for h in check(str(f), f.read_text(encoding="utf-8"), pats, secret, code=False)]
    hits = []
    for f in files(root):
        if f.name == "privacy_guard.py":
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        no_secrets = re.compile("(?!)") if "tests/" in str(f) else secret  # tests hold fake secrets on purpose
        hits += check(str(f.relative_to(root)), text, pats, no_secrets)
    return hits


if __name__ == "__main__":
    args = sys.argv[1:]
    texts = [Path(a) for a in args[args.index("--text") + 1:]] if "--text" in args else []
    args = args[:args.index("--text")] if "--text" in args else args
    root = Path(args[0] if args else Path(__file__).parent.parent).resolve()
    terms = denylist()
    print(f"privacy guard: {len(terms)} denylist terms" if terms else "privacy guard: no denylist set (MEMORY_STEM_DENYLIST)")
    hits = scan(root, terms, texts)
    print("\n".join(hits) or "privacy guard: clean")
    sys.exit(1 if hits else 0)
