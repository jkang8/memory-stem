"""Nicknames the owner actually uses, expanded at query time: "the shop" also searches for "Acme Bike Repair".
Source of truth is Memory/Aliases.md, lines like `- the shop = Acme Bike Repair`. Edit that file; no restart needed on next sync."""
from __future__ import annotations

import re
from pathlib import Path

NAME = "Aliases.md"
_LINE = re.compile(r"^\s*[-*]\s*(.+?)\s*=\s*(.+?)\s*$")


def load(root: Path) -> dict[str, str]:
    try:
        text = (Path(root) / NAME).read_text(encoding="utf-8")
    except OSError:
        return {}
    return {m[1].lower(): m[2] for ln in text.splitlines() if (m := _LINE.match(ln))}


def expand(query: str, aliases: dict[str, str]) -> str:
    """Append the canonical name for each alias found as whole words; leave the query alone if it already has it."""
    extra = [full for a, full in aliases.items()
             if re.search(rf"(?<![\w]){re.escape(a)}(?![\w])", query, re.I) and full.lower() not in query.lower()]
    return query + (" " + " ".join(dict.fromkeys(extra)) if extra else "")
