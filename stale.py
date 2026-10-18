"""Staleness check: python -m memory_stem.stale  (run from ~/.hermes/plugins).
Flags current notes that mention a date already past but have no `expires`, so they keep being recalled as if still true.
shortcut: month-name dates without a year are read as the note's created year (or next year if that is already past); fine for notes written near the date."""
from __future__ import annotations

import datetime as dt
import re

from .config import load_settings
from .notes import Note, NoteStore

_MONTHS = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}
_ISO = re.compile(r"\b(20\d\d)-(\d\d)-(\d\d)\b")
_NAMED = re.compile(r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.? (\d{1,2})(?:, (20\d\d))?\b")


def dates_in(text: str, created: str = "") -> list[dt.date]:
    out = []
    for y, m, d in _ISO.findall(text):
        out.append(_mk(int(y), int(m), int(d)))
    cy = int(created[:4]) if created[:4].isdigit() else dt.date.today().year
    for mon, d, y in _NAMED.findall(text):
        out.append(_mk(int(y) if y else cy, _MONTHS[mon.lower()[:3]], int(d)))
    return [x for x in out if x]


def _mk(y: int, m: int, d: int):
    try:
        return dt.date(y, m, d)
    except ValueError:
        return None


def stale(notes: list[Note], today: dt.date | None = None) -> list[tuple[Note, dt.date]]:
    today = today or dt.date.today()
    hits = []
    for n in notes:
        if not n.active() or n.expires:
            continue
        past = [d for d in dates_in(n.body, n.created) if d < today]
        if past and max(dates_in(n.body, n.created)) < today:  # every date mentioned is past
            hits.append((n, max(past)))
    return hits


_DEADLINE = re.compile(r"\b(by|due|ends?|deadline|enroll|leaves?|expires?|closes?|before|until|free (?:changes|cancel\w*)|unpaid)\b", re.I)
_HISTORY = re.compile(r"\b(since|first (?:invited|seen)|moved in|began|started|born|founded)\b", re.I)
_RELATIVE = re.compile(r"\b(tomorrow|tonight|yesterday|next (?:week|month|year|mon|tues|wednes|thurs|fri|satur|sun)\w*|this (?:week|weekend|month)|in \d+ (?:days|weeks))\b", re.I)


def intent(text: str) -> str:
    """Cue-word guess for ranking flags only: 'deadline' (should expire), 'history' (stays true) or 'unclear'."""
    d, h = bool(_DEADLINE.search(text)), bool(_HISTORY.search(text))
    return "deadline" if d and not h else "history" if h and not d else "unclear"


def warn(body: str, expires: str = "", today: dt.date | None = None) -> str:
    """Write-time check for remember / draft. Returns a warning string, or '' if the note looks fine."""
    if expires:
        return ""
    today = today or dt.date.today()
    msgs = []
    if _RELATIVE.search(body):
        msgs.append("uses a relative date (e.g. 'tomorrow', 'next Friday'); write the absolute date, it will be wrong tomorrow")
    future = [d for d in dates_in(body, today.isoformat()) if d >= today]
    if future:
        last = max(future)
        msgs.append(f"mentions {last.isoformat()} but has no expires; consider expires={(last + dt.timedelta(days=1)).isoformat()}"
                    f" if the note stops being true after that ({intent(body)} cues)")
    return "; ".join(msgs)


if __name__ == "__main__":
    rows = stale(NoteStore(load_settings().notes_dir).all())
    for n, d in sorted(rows, key=lambda r: r[1]):
        print(f"{n.id}  last date {d}  [{intent(n.body)}]  {n.title[:55]}")
    print(f"{len(rows)} current notes mention only past dates and have no expires")
