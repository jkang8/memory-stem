"""Approve the dream job's drafts automatically, and undo one on request.

  python -m memory_stem.autoapprove            approve safe drafts, print a report
  python -m memory_stem.autoapprove --revert ID   forget note ID and bring back the note it replaced

A draft stays in Memory/_inbox for the user when its supersede looks off-topic or drops eval answers (checks.review_supersede).
If the eval gets worse after approving, the whole batch is reverted. Run from ~/.hermes/plugins with the Hermes venv."""
from __future__ import annotations

import json
import sys

from . import checks
from .config import load_settings
from .notes import NoteStore

LOG = "autoapprove_log.jsonl"  # one line per approval, for reverts and audit


def revert(store: NoteStore, note_id: str) -> str:
    n = store.get(note_id) or next((x for x in store.all() if x.id.endswith(note_id)), None)
    if n is None:
        raise KeyError(f"no memory with id {note_id}")
    store.forget(n.id)
    old = store.get(n.supersedes) if n.supersedes else None
    if old is not None and old.superseded_by == n.id:
        store.restore(old.id)
        return f"reverted {n.title}; restored {old.title}"
    return f"reverted {n.title}"


def run(evaluate=None) -> str:
    s = load_settings()
    store, inbox = NoteStore(s.notes_dir), NoteStore(s.notes_dir / "_inbox")
    log = s.index_path.parent / LOG
    approved, held = [], []
    before = evaluate() if evaluate is not None and inbox.all() else None
    for d in inbox.all():
        old = store.get(d.supersedes) if d.supersedes else None
        if d.supersedes and old is None:
            held.append(f"{d.title} (replaces a note that no longer exists)")
            continue
        if old is not None:
            others = [x.body for x in store.all() if x.active() and x.id != old.id]
            if why := checks.review_supersede(old.body, d.body, others):
                held.append(f"{d.title}: {why[0][:140]}")
                continue
        inbox.move_to(d.id, store)
        approved.append(d)
    store.reconcile()
    if approved and before is not None:
        after = evaluate()
        if after < before:
            for d in approved:
                revert(store, d.id)
            return f"eval dropped {before}->{after}, so I reverted all {len(approved)} approvals; drafts need a look"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        for d in approved:
            f.write(json.dumps({"id": d.id, "title": d.title, "supersedes": d.supersedes or None}) + "\n")
    lines = [f"- {d.title} ({d.id[-4:]})" + (" replaces an older note" if d.supersedes else "") for d in approved]
    lines += [f"- HELD for you: {h}" for h in held]
    return (f"Saved {len(approved)} memories" + (f", held {len(held)}" if held else "") + ":\n" + "\n".join(lines)) if lines else "No new memories."


def _recall() -> int:
    """Tuned-set recall count; run before and after approving so a bad batch can be undone."""
    from .evaluate import run as ev
    return int(ev(verbose=False)["recall"].split("/")[0])


if __name__ == "__main__":
    if sys.argv[1:2] == ["--revert"] and len(sys.argv) == 3:
        print(revert(NoteStore(load_settings().notes_dir), sys.argv[2]))
    else:
        print(run(evaluate=_recall))
