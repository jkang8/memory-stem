#!/usr/bin/env python3
# Vendored from github.com/jkang8/skills: skills/doc-writing/scripts/doc_check.py (branch agent/b2-1-checks, 8a1f132). Change it upstream.
"""Fail on doc-writing violations in a repo: line budgets and stale backticked paths. Stdlib only.

usage: doc_check.py <repo>
A backticked path is checked when its first segment exists next to the doc or at the repo root, so
`src/app.py` is checked in a repo with src/, while `web/src/api/` in a repo without web/ is taken as
an example. Exits 1 with `path[:line]: problem` per hit.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path, PurePath

# Pattern (matched from the right, like PurePath.match) -> max lines. First match wins.
BUDGETS = {
    "CLAUDE.md": 100,
    "README.md": 150,
    "docs/decisions/*.md": 15,
}
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".venv", "fixtures"}
TICK = re.compile(r"`([^`\s]+)`")
FENCE = re.compile(r"^\s*(```|~~~)")
NOT_A_PATH = re.compile(r"[<>{}*$|()\[\]=@,;]|^-|^\w+://|^~|^/")


def docs(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.md") if p.is_file() and not p.is_symlink()
                  and not SKIP_DIRS & set(p.relative_to(root).parts))


def budget(rel: PurePath) -> int | None:
    return next((limit for pat, limit in BUDGETS.items() if rel.match(pat)), None)


def looks_like_path(tok: str) -> bool:
    return "/" in tok and not NOT_A_PATH.search(tok)


def stale(tok: str, doc: Path, root: Path) -> bool:
    tok = re.sub(r":\d+(-\d+)?$", "", tok)
    first = PurePath(tok).parts[0]
    if first == ".git":  # a file, not a folder, in worktrees; never tracked content
        return False
    bases = [b for b in (doc.parent, root) if (b / first).exists() or first in (".", "..")]
    return bool(bases) and not any((b / tok).exists() for b in bases)


def check(root: Path) -> list[str]:
    hits = []
    for doc in docs(root):
        rel = doc.relative_to(root)
        lines = doc.read_text(encoding="utf-8").splitlines()
        limit = budget(rel)
        if limit is not None and len(lines) > limit:
            hits.append(f"{rel.as_posix()}: {len(lines)} lines, budget {limit}")
        fenced = False
        for n, line in enumerate(lines, 1):
            if FENCE.match(line):
                fenced = not fenced
                continue
            if fenced:
                continue
            hits += [f"{rel.as_posix()}:{n}: stale path `{t}`" for t in TICK.findall(line)
                     if looks_like_path(t) and stale(t, doc, root)]
    return hits


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    hits = check(Path(argv[0]).resolve())
    print("\n".join(hits) or "doc check: clean")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
