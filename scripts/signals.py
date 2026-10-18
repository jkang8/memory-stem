"""Print Memory Stem's weak spots, for choosing the next foundational fix (see IMPROVE.md). Run it through scripts/signals.

Both private locations are arguments, never defaults: --vault (notes and eval sets) and --hermes-home (runtime data).
The tuned section quotes eval questions, so the output is for reading locally. Heldout shows counts only: it is frozen.
"""
from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from pathlib import Path


def replay_summary(path: Path) -> list[str]:
    """Counts and note ids only: the logged wording is the user's own and stays out of the output."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ["no replay log"]
    rows = []
    for line in lines:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    ids = Counter(str(r.get("id", "?")) for r in rows)
    prompt_like = sum(1 for r in rows if str(r.get("q", "")).lstrip().startswith("["))
    out = [f"{len(rows)} entries for {len(ids)} notes, {prompt_like} starting like a system prompt rather than user wording"]
    if ids:
        out.append("most logged notes: " + ", ".join(f"{i}: {n}" for i, n in ids.most_common(5)))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Print Memory Stem's weak spots.")
    ap.add_argument("--vault", required=True, type=Path, help="the notes folder (what VAULT_DIR points to)")
    ap.add_argument("--hermes-home", required=True, type=Path, help="Hermes's data folder; runtime data is under it")
    a = ap.parse_args(argv)
    os.environ["VAULT_DIR"], os.environ["HERMES_HOME"] = str(a.vault), str(a.hermes_home)
    os.environ.pop("VAULT_MEMORY_DIR", None)  # --vault decides where the notes are

    from memory_stem import evaluate, replay, stale, usage
    from memory_stem.config import load_settings
    from memory_stem.notes import NoteStore

    s = load_settings()
    notes = NoteStore(s.notes_dir).all()
    print("Memory Stem weak spots. Local only: the tuned section quotes personal data, so never paste it into code, commits or PRs.")

    t = evaluate.run(verbose=False)
    print(f"\n== tuned evals (OK to tune against)\nrecall {t['recall']}, junk returned {t['junk_returned']}, avg hits {t['avg_hits']}")
    for q in t["misses"]:
        print(f"  missed: {q}")

    print("\n== heldout evals (frozen: counts only, never tune against these)")
    try:
        h = evaluate.run_heldout()
        print(f"recall {h['recall']}, junk returned {h['junk_returned']}, retired cases {h['retired']}")
    except (OSError, ValueError, KeyError):
        print("no heldout set")

    print("\n== replay log (questions where search found a memory that recall missed)")
    print("\n".join(replay_summary(s.index_path.parent / replay.LOG)))

    idle = usage.report(notes, usage.load(s))
    print(f"\n== usage\n{len(idle)} current memories older than 30 days and unused for 30 days (`python -m memory_stem.usage` lists them)")

    print(f"\n== stale\n{len(stale.stale(notes))} current memories mention only past dates and have no expires "
          "(`python -m memory_stem.stale` lists them)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
