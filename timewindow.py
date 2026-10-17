"""Time-window recall: "what did we decide this week", "anything since September" has no topic words for search,
so pull Memory notes created in that range instead. Newest first."""
from __future__ import annotations

import datetime as dt
import re

_MONTHS = {m: i for i, m in enumerate(
    "january february march april may june july august september october november december".split(), 1)}


def window(query: str, today: dt.date | None = None) -> tuple[dt.date, dt.date] | None:
    """Date range a query asks about, or None. Inclusive on both ends."""
    today = today or dt.date.today()
    q = (query or "").lower()
    # only questions about our history ("what did we decide today"), not "weather today"
    if not re.search(r"\b(sav|remember|decid|new|chang|happen|discuss|talk|learn|note|told|said|did (we|i)|have (we|i)|since|anything)", q):
        return None
    if re.search(r"\btoday\b", q):
        return today, today
    if re.search(r"\byesterday\b", q):
        return today - dt.timedelta(1), today - dt.timedelta(1)
    if re.search(r"\b(this|past|last) week\b|\brecently\b|\blately\b", q):
        return today - dt.timedelta(7), today
    if re.search(r"\b(this|past|last) month\b", q):
        return today - dt.timedelta(31), today
    m = re.search(r"\b(since|after|in|during)\s+(" + "|".join(_MONTHS) + r")\b", q)
    if m:
        mon = _MONTHS[m[2]]
        year = today.year if mon <= today.month else today.year - 1
        start = dt.date(year, mon, 1)
        if m[1] in ("since", "after"):
            return start, today
        return start, dt.date(year + mon // 12, mon % 12 + 1, 1) - dt.timedelta(1)
    return None


def in_window(notes, win) -> list:
    lo, hi = win
    out = []
    for n in notes:
        try:
            d = dt.date.fromisoformat(n.created[:10])
        except ValueError:
            continue
        if n.active() and lo <= d <= hi:
            out.append(n)
    return sorted(out, key=lambda n: n.created, reverse=True)


def extra(query: str, notes, have: set, room: int, today: dt.date | None = None) -> list:
    """Memories from the query's time range not already shown, at most `room`."""
    win = window(query, today) if room > 0 else None
    return [n for n in in_window(notes, win) if n.id not in have][:room] if win else []
