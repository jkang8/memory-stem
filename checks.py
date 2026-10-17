"""Checks run on every memory write. They return warnings to the agent and never block the write.
Each one catches a mistake that really happened: a rewrite that dropped wording the eval cases needed,
a supersede that retired a note on a different topic, and a new note saved beside one that already said it."""
from __future__ import annotations

import json
import re
from pathlib import Path

_STOP = frozenset("that this with from have about when what which where your into they them their there were been also than "
                  "only more most just like some such then very will would should could does john john's".split())
# Share of the old note's words a replacement drops. Measured 2026-10-15: good rewrites dropped 0.08-0.46,
# the supersede that wrongly retired "Memory system design" dropped 0.83. Cosine could not separate them (0.83 vs 0.81).
LOST_TOO_MUCH = 0.6
# Cosine at which a new note probably repeats an existing one. Measured 2026-10-15 on 27 past supersede pairs and 63 current
# notes: 0.90 caught 15/27 with 0 false alarms; 0.85 caught 20/27 but warned on 6 distinct notes (closest distinct pair 0.888).
DUPLICATE = 0.9


def _words(text: str) -> set[str]:
    return {w.strip(".,;:") for w in re.findall(r"[a-z0-9][a-z0-9@.'/-]{3,}", text.lower()) if w not in _STOP}


def dropped(old: str, new: str) -> list[str]:
    """Words the old note had that the replacement lost."""
    return sorted(_words(old) - _words(new))


def lost_share(old: str, new: str) -> float:
    o = _words(old)
    return len(o - _words(new)) / len(o) if o else 0.0


def eval_answers() -> list[str]:
    try:
        from .evaluate import _evals, logged, tuned  # lazy: evaluate pulls in the embedder stack
        out = [m for _, m in tuned()[0] + logged()]
    except Exception:
        out = []
    for f in ("heldout.json",):
        try:
            out += [m for _, m in json.loads(_evals(f).read_text())["cases"]]
        except Exception:  # no evals, or no VAULT_DIR (tests, other installs): warnings just skip this check
            pass
    return out


def broken_cases(old: str, new: str, others: list[str], answers: list[str] | None = None) -> list[str]:
    """Eval answers only the old note contained: the rewrite makes those questions unanswerable."""
    lo, ln, rest = old.lower(), new.lower(), [b.lower() for b in others]
    return [a for a in dict.fromkeys(answers if answers is not None else eval_answers())
            if a.lower() in lo and a.lower() not in ln and not any(a.lower() in b for b in rest)]


def review_supersede(old_body: str, new_body: str, others: list[str], answers: list[str] | None = None) -> list[str]:
    out = []
    share = lost_share(old_body, new_body)
    if share >= LOST_TOO_MUCH:
        out.append(f"the replacement drops {share:.0%} of the old note's words, so it may be a different topic; "
                   f"if so, restore the old note and save this one without supersedes. Dropped: {', '.join(dropped(old_body, new_body)[:12])}")
    if bad := broken_cases(old_body, new_body, others, answers):
        out.append(f"{len(bad)} eval answers were only in the old note and are now gone: {'; '.join(bad[:5])}")
    return out
