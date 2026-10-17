"""Generated one-line-per-memory index (Memory/Index.md). Never edited by hand.
NoteStore ignores it (no `id` in its frontmatter) and Recall skips Memory/, so it can never be recalled as a memory."""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from .notes import Note

NAME = "Index.md"
_HEAD = "---\ntags:\n  - index\n---\nGenerated from the notes in this folder. Edit the notes, not this file.\n"


def _gist(body: str, width: int = 110) -> str:
    first = re.split(r"(?<=[.!?])\s", body.strip().splitlines()[0], maxsplit=1)[0]
    return first if len(first) <= width else first[:width].rsplit(" ", 1)[0] + "…"


def render(notes: list[Note]) -> str:
    groups: dict[str, list[Note]] = defaultdict(list)
    for n in notes:
        if n.active():
            groups[next((t for t in n.tags if t != "memory"), "other")].append(n)
    out = [_HEAD, f"{sum(map(len, groups.values()))} current memories.\n"]
    for tag in sorted(groups):
        out.append(f"\n## {tag}\n")
        for n in sorted(groups[tag], key=lambda n: n.title.lower()):
            exp = f" (expires {n.expires})" if n.expires else ""
            out.append(f"- [[{n.title}]]{exp}: {_gist(n.body)}")
    return "\n".join(out) + "\n"


def write(root: Path, notes: list[Note]) -> bool:
    """Write the index only if its text changed, so the file's mtime does not churn. True if written."""
    path, text = Path(root) / NAME, render(notes)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    Path(root).mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


HUBS = "About"  # Memory/About/<subject>.md, one generated page per `about` subject, so Obsidian's graph links them


def write_hubs(root: Path, notes: list[Note]) -> int:
    """One page per subject listing its current memories. Regenerated, never edited; stale pages are removed."""
    groups: dict[str, list[Note]] = defaultdict(list)
    for n in notes:
        if n.active():
            for a in n.about:
                groups[a].append(n)
    hub = Path(root) / HUBS
    hub.mkdir(parents=True, exist_ok=True)
    want = {}
    for subject, ns in groups.items():
        name = re.sub(r'[\\/:*?"<>|#^\[\]]', " -", subject).strip() + ".md"
        lines = [f"- [[{n.title}]]: {_gist(n.body)}" for n in sorted(ns, key=lambda n: n.title.lower())]
        want[name] = _HEAD + f"\nMemories about {subject}.\n\n" + "\n".join(lines) + "\n"
    for p in hub.glob("*.md"):
        if p.name not in want:
            p.unlink()
    for name, text in want.items():
        p = hub / name
        if not p.exists() or p.read_text(encoding="utf-8") != text:
            p.write_text(text, encoding="utf-8")
    return len(want)


def titles(notes: list[Note], width: int = 48) -> str:
    """Compact map of what is remembered: current note titles only, one per line, for the system prompt."""
    cut = lambda t: t if len(t) <= width else t[:width].rsplit(" ", 1)[0] + "…"
    return "\n".join(f"- {cut(n.title)}" for n in sorted(notes, key=lambda n: n.title.lower()) if n.active())
