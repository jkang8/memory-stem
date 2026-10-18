"""Fail if the repo contains personal data. The repo is public; personal terms live outside it.

Checks tracked text files for: emails other than noreply, secrets (notes.check_secret), and any term
listed in $MEMORY_STEM_DENYLIST (a local file, one term per line, never committed).
usage: python scripts/privacy_guard.py [repo_dir]
"""
from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
ALLOWED_EMAIL = re.compile(r"(noreply|example\.(com|org)|users\.noreply\.github\.com)", re.I)


SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox"}


def files(root: Path) -> list[Path]:
    """Every file under root except caches, VCS and virtualenv folders, compiled files and binaries, so a new file is
    checked before it is committed. Walks the tree itself: no git needed, and nothing is executed."""
    out = []
    for folder, dirs, names in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        # in a worktree `.git` is a file (it holds an absolute path), so names are checked against SKIP_DIRS too
        out += [Path(folder) / n for n in sorted(names) if n not in SKIP_DIRS and not n.endswith((".png", ".jpg", ".sqlite", ".pyc"))]
    return out


def denylist() -> list[str]:
    p = os.environ.get("MEMORY_STEM_DENYLIST")
    if not p or not Path(p).expanduser().exists():
        return []
    return [t.strip() for t in Path(p).expanduser().read_text().splitlines() if t.strip() and not t.startswith("#")]


def scan(root: Path, terms: list[str]) -> list[str]:
    # by path, not `import memory_stem`: a worktree's folder is named after its branch
    spec = importlib.util.spec_from_file_location("_ms_notes", root / "notes.py")
    notes = sys.modules["_ms_notes"] = importlib.util.module_from_spec(spec)  # dataclasses look the module up
    spec.loader.exec_module(notes)
    _SECRET = notes._SECRET
    hits = []
    pats = [re.compile(r"\b" + re.escape(t) + r"\b", re.I) for t in terms]
    for f in files(root):
        if f.name == "privacy_guard.py":
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            where = f"{f.relative_to(root)}:{n}"
            hits += [f"{where}: email {e}" for e in EMAIL.findall(line) if not ALLOWED_EMAIL.search(e)]
            if _SECRET.search(line) and "tests/" not in str(f) and "re.compile" not in line and not line.lstrip().startswith(("r\"", "r'", "#")):
                hits.append(f"{where}: looks like a secret")
            hits += [f"{where}: denylisted term" for p in pats if p.search(line)]
    return hits


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    terms = denylist()
    print(f"privacy guard: {len(terms)} denylist terms" if terms else "privacy guard: no denylist set (MEMORY_STEM_DENYLIST)")
    hits = scan(root, terms)
    print("\n".join(hits) or "privacy guard: clean")
    sys.exit(1 if hits else 0)
