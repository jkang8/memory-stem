"""Recall counts per memory, so dead notes can be pruned and noisy ones spotted.
Kept beside the index (runtime data), not in note frontmatter: a count bump would rewrite and re-embed the note."""
from __future__ import annotations

import datetime as dt
import json

from .config import load_settings
from .notes import NoteStore

FILE = "usage.json"


def _path(settings):
    return (settings or load_settings()).index_path.parent / FILE


def load(settings=None) -> dict:
    try:
        return json.loads(_path(settings).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def bump(settings, ids, kind: str = "recalled") -> None:
    """kind: 'recalled' (injected before a turn) or 'searched' (returned by ms_search)."""
    if not ids:
        return
    data, day = load(settings), dt.date.today().isoformat()
    for i in ids:
        u = data.setdefault(i, {})
        u[kind] = u.get(kind, 0) + 1
        u["last"] = day
    try:
        _path(settings).write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def report(notes, data: dict, today: dt.date | None = None, idle_days: int = 30) -> list[str]:
    """Current memories never recalled or searched, or idle for idle_days, oldest first."""
    today = today or dt.date.today()
    rows = []
    for n in notes:
        if not n.active() or n.created > (today - dt.timedelta(days=idle_days)).isoformat():
            continue
        last = data.get(n.id, {}).get("last", "")
        if not last or last < (today - dt.timedelta(days=idle_days)).isoformat():
            rows.append((last or "never", n))
    return [f"{n.id}  last used {last}  {n.title[:60]}" for last, n in sorted(rows, key=lambda r: (r[0] != "never", r[0]))]


if __name__ == "__main__":
    s = load_settings()
    notes, data = NoteStore(s.notes_dir).all(), load(s)
    top = sorted(data.items(), key=lambda kv: -kv[1].get("recalled", 0))[:10]
    by_id = {n.id: n for n in notes}
    print("Most recalled:")
    for i, u in top:
        print(f"  {u.get('recalled', 0):>4}x  {by_id[i].title[:60] if i in by_id else i}")
    idle = report(notes, data)
    print(f"{len(idle)} memories older than 30 days not used in 30 days:")
    print("\n".join(idle))
