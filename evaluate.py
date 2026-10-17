"""Recall regression check against the REAL vault: vm.sh evaluate [--heldout | --ids <file> | --miss <q> <text>].

Eval sets live in Memory/_evals/ (they quote the user's life, so they stay out of the repo):
tuned.json (cases + junk, OK to tune against), heldout.json and heldout_domain.json (frozen, never tune),
misses.json (real misses the user reported). Exit code 1 if recall or junk rejection regress.
"""
from __future__ import annotations

import json
import sys
import tempfile
import warnings
from pathlib import Path

from .config import load_settings
from .embedder import make_embedder
from .index import Index
from .notes import NoteStore
from . import aliases
from .search import Searcher
from .recall import Recall

def _evals(name: str):
    return load_settings().evals_dir / name


def tuned() -> tuple[list[tuple[str, str]], list[str]]:
    """The tuned set: (question, text the right note must contain) plus junk prompts that must recall nothing."""
    try:
        d = json.loads(_evals("tuned.json").read_text())
        return [tuple(c) for c in d["cases"]], d["junk"]
    except (OSError, ValueError, KeyError):
        return [], []


def logged() -> list[tuple[str, str]]:
    try:
        return [tuple(x) for x in json.loads(_evals("misses.json").read_text())]
    except (OSError, ValueError):
        return []


def log_miss(question: str, must: str) -> None:
    rows = logged()
    if (question, must) not in rows:
        _evals("misses.json").parent.mkdir(parents=True, exist_ok=True)
        _evals("misses.json").write_text(json.dumps(rows + [(question, must)], indent=1))


def _scratch_index(s, emb) -> Index:
    """A throwaway copy of the live index: sync then only re-embeds changed notes (seconds, not minutes).
    The live index is never written. Falls back to an empty index if there is no live one."""
    import sqlite3
    p = Path(tempfile.mkdtemp()) / "i.sqlite"
    if s.index_path.exists():
        try:
            with sqlite3.connect(s.index_path) as src, sqlite3.connect(p) as dst:
                src.backup(dst)  # consistent copy even if the gateway is writing
        except sqlite3.Error:
            p.unlink(missing_ok=True)
    return Index(p, emb)


def run(verbose: bool = True) -> dict:
    warnings.filterwarnings("ignore")
    cases, junk_qs = tuned()
    cases = cases + logged()
    s = load_settings()
    store = NoteStore(s.notes_dir)
    emb = make_embedder(s.model_name, s.model_cache)
    idx = _scratch_index(s, emb)
    rec = Recall(store, s.vault_dir)
    idx.sync(rec.all())
    sr = Searcher(idx, emb, s.min_cosine, strong_cosine=s.strong_cosine, rel_margin=s.rel_margin, vault_penalty=s.vault_penalty, aliases=aliases.load(s.notes_dir))
    right, sizes, misses = 0, [], []
    for q, must in cases:
        bodies = [rec.get(h.id).body for h in sr.search(q, s.top_k)]
        sizes.append(len(bodies))
        if any(must.lower() in b.lower() for b in bodies):
            right += 1
        else:
            misses.append(q)
    junk = sum(1 for q in junk_qs if sr.search(q, s.top_k))
    out = {"notes": len(rec.all()), "recall": f"{right}/{len(cases)}", "avg_hits": round(sum(sizes) / len(sizes), 2),
           "junk_returned": f"{junk}/{len(junk_qs)}", "misses": misses, "ok": right >= len(cases) - 1 and junk == 0}
    if verbose:
        for k, v in out.items():
            print(f"{k}: {v}")
    return out


def run_heldout(name: str = "heldout.json") -> dict:
    """Frozen paraphrase questions written before any scoring (heldout.json). Never tune thresholds or wording against these."""
    warnings.filterwarnings("ignore")
    data = json.loads(_evals(name).read_text())
    s = load_settings()
    store = NoteStore(s.notes_dir)
    emb = make_embedder(s.model_name, s.model_cache)
    idx = _scratch_index(s, emb)
    rec = Recall(store, s.vault_dir)
    idx.sync(rec.all())
    sr = Searcher(idx, emb, s.min_cosine, strong_cosine=s.strong_cosine, rel_margin=s.rel_margin, vault_penalty=s.vault_penalty, aliases=aliases.load(s.notes_dir))
    live = [n.body.lower() for n in store.all() if n.active()]
    bad = [m for _, m in data["cases"] if not any(m.lower() in b for b in live)]  # my case is wrong, not recall
    right, miss = 0, []
    live_cases = [(q, m) for q, m in data["cases"] if m not in bad]  # retired: the fact changed, so the case no longer has an answer
    for q, must in live_cases:
        if any(must.lower() in rec.get(h.id).body.lower() for h in sr.search(q, s.top_k)):
            right += 1
        else:
            miss.append(q)
    junk = [q for q in data["junk"] if sr.search(q, s.top_k)]
    return {"recall": f"{right}/{len(live_cases)}", "retired": len(data["cases"]) - len(live_cases),
            "junk_returned": f"{len(junk)}/{len(data['junk'])}", "misses": miss, "junk": junk, "bad_cases": bad}


def run_ids(name: str) -> dict:
    """Score a frozen file of [{id, question}] cases by whether the right note id is in the top results, per source.
    Works for any source: ids are '<source>:<path>' (or a bare memory id). Never tune against these files."""
    warnings.filterwarnings("ignore")
    p = Path(name)
    data = json.loads((p if p.exists() else _evals(p.name)).read_text())  # bare name = file in Memory/_evals
    s = load_settings()
    emb = make_embedder(s.model_name, s.model_cache)
    idx = _scratch_index(s, emb)
    rec = Recall(NoteStore(s.notes_dir), s.vault_dir)
    idx.sync(rec.all())
    sr = Searcher(idx, emb, s.min_cosine, strong_cosine=s.strong_cosine, rel_margin=s.rel_margin, vault_penalty=s.vault_penalty, aliases=aliases.load(s.notes_dir))
    known = {n.id for n in rec.all()}
    per: dict[str, list[int]] = {}
    miss = []
    for c in data:
        src = c["id"].split(":", 1)[0] if ":" in c["id"] else "memory"
        got = [h.id for h in sr.search(c["question"], s.top_k)]
        ok = c["id"] in got
        per.setdefault(src, [0, 0])
        per[src][0] += ok
        per[src][1] += 1
        if not ok:
            miss.append((c["question"], "not indexed" if c["id"] not in known else (got[0] if got else "nothing returned")))
    return {"recall": {k: f"{a}/{b}" for k, (a, b) in per.items()}, "misses": miss}


if __name__ == "__main__":
    if sys.argv[1:3] and sys.argv[1] == "--ids":  # python -m memory_stem.evaluate --ids path/to/cases.json
        for k, v in run_ids(sys.argv[2]).items():
            print(f"{k}: {v}")
    elif sys.argv[1:2] == ["--heldout"]:  # optionally: --heldout <file with cases/junk>; domain set uses --ids
        for k, v in run_heldout(*sys.argv[2:3]).items():
            print(f"{k}: {v}")
    elif len(sys.argv) == 4 and sys.argv[1] == "--miss":  # python -m memory_stem.evaluate --miss "question" "text the right note has"
        log_miss(sys.argv[2], sys.argv[3])
        print("logged; total logged misses:", len(logged()))
    else:
        sys.exit(0 if run()["ok"] else 1)
