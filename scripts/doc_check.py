"""Fail if docs are over budget or name things that no longer exist. Run in CI and by scripts/gate.sh.

- Line budgets (BUDGETS): over budget means cut, not raise the cap.
- Stale references: repo paths in code spans or fenced blocks, and `python -m memory_stem.<module>` anywhere,
  must exist. A path counts as a repo path when its first folder is in the repo, or it is a bare .py/.sh name
  (found at the root or next to the doc);
  vault files, ~ and $ paths and globs are outside the repo and are skipped.
usage: python scripts/doc_check.py [repo_dir]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BUDGETS = {"CLAUDE.md": 100, "AGENTS.md": 100, "README.md": 150, "CONTRIBUTING.md": 80, "docs/decisions/*.md": 15}

SPAN = re.compile(r"`([^`\n]+)`")
MODULE = re.compile(r"python3? -m memory_stem\.([\w.]+)")
PATHLIKE = re.compile(r"^[\w.\-/]+$")
CODE_EXT = (".py", ".sh")  # bare names with other extensions (Profile.md, tuned.json) are vault files


def docs(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.md") if not any(part.startswith((".", "__")) for part in p.relative_to(root).parts))


def over_budget(root: Path) -> list[str]:
    out = []
    for pattern, cap in BUDGETS.items():
        for p in sorted(root.glob(pattern)):
            n = len(p.read_text(encoding="utf-8").splitlines())
            if n > cap:
                out.append(f"{p.relative_to(root)}: {n} lines, budget {cap} (cut it; don't raise the cap)")
    return out


def _exists(root: Path, ref: str, here: Path) -> bool:
    """A bare name may sit next to the doc that names it; a path is from the repo root."""
    for base in (root, here) if "/" not in ref else (root,):
        if (base / ref).exists():
            return True
        stem, _, _symbol = ref.rpartition(".")  # tests/helpers.FakeEmbedder -> tests/helpers.py
        if stem and (base / (stem + ".py")).exists():
            return True
    return False


def _repo_path(root: Path, token: str) -> str | None:
    """The token as a repo-relative path to check, or None when it isn't one (prose, flags, outside the repo)."""
    t = token.strip(".,;:()[]'\"").removeprefix("./").removeprefix("memory_stem/")  # the repo is the memory_stem package
    t = t.rstrip("/")
    if not t or not PATHLIKE.match(t) or t.startswith(("-", ".")):
        return None
    if "/" in t:
        return t if (root / t.split("/")[0]).exists() else None
    return t if t.endswith(CODE_EXT) else None


def stale(root: Path) -> list[str]:
    out = []
    for doc in docs(root):
        name, fenced = doc.relative_to(root), False
        for n, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("```"):
                fenced = not fenced
                continue
            for mod in MODULE.findall(line):
                if not ((root / (mod.replace(".", "/") + ".py")).exists() or (root / mod.replace(".", "/") / "__init__.py").exists()):
                    out.append(f"{name}:{n}: `python -m memory_stem.{mod}` names no module")
            code = line.split() if fenced else [w for span in SPAN.findall(line) for w in span.split()]
            for token in dict.fromkeys(code):
                ref = _repo_path(root, token)
                if ref and not _exists(root, ref, doc.parent):
                    out.append(f"{name}:{n}: `{ref}` does not exist")
    return out


def check(root: Path) -> list[str]:
    return over_budget(root) + stale(root)


if __name__ == "__main__":
    root = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent.parent).resolve()
    hits = check(root)
    print("\n".join(hits) or "doc check: clean")
    sys.exit(1 if hits else 0)
