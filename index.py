"""Disposable SQLite index over the notes: FTS5 for keywords, float32 blobs for vectors.
Delete the file and it rebuilds from the markdown on the next sync."""
from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path

from .embedder import Embedder
from .notes import Note

_STOP = frozenset(
    "a an and are as at be but by do for from how i in is it me my of on or so that the this to was what when where "
    "which who why with you your am can did does will would should could about".split()
)


def fts_query(text: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 1 and w not in _STOP]
    return " OR ".join(f'"{w}"' for w in list(dict.fromkeys(words))[:40])  # cap terms, never slice a quoted string


class Index:
    def __init__(self, path: str | Path, embedder: Embedder):
        self.embedder = embedder
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.RLock()
        self._cache = None
        with self._lock, self._db:
            self._db.execute("CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT)")
            self._db.execute("CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY, mtime REAL, vec BLOB)")
            self._db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(title, body, tokenize='porter unicode61')")
            old = self._db.execute("SELECT v FROM meta WHERE k='model'").fetchone()
            if not old or old[0] != embedder.name:  # a different model makes old vectors meaningless
                self._db.execute("DELETE FROM notes")
                self._db.execute("DELETE FROM fts")
                self._db.execute("INSERT OR REPLACE INTO meta VALUES('model', ?)", (embedder.name,))

    def sync(self, notes: list[Note]) -> tuple[int, int]:
        """Make the index match the active notes. Returns (indexed, removed)."""
        with self._lock:
            active = {n.id: n for n in notes if n.active()}
            known = dict(self._db.execute("SELECT id, mtime FROM notes"))
            gone = [i for i in known if i not in active]
            stale = [n for n in active.values() if known.get(n.id) != n.mtime]
            vecs = self.embedder.embed([n.search_text() for n in stale]) if stale else None
            with self._db:
                for i in gone + [n.id for n in stale]:
                    self._drop(i)
                for k, n in enumerate(stale):
                    cur = self._db.execute(
                        "INSERT INTO notes(id, mtime, vec) VALUES(?,?,?)",
                        (n.id, n.mtime, vecs[k].tobytes() if vecs is not None else None))
                    self._db.execute("INSERT INTO fts(rowid, title, body) VALUES(?,?,?)", (cur.lastrowid, n.title, " ".join((n.body, *n.about, *n.questions))))
            self._cache = None
            return len(stale), len(gone)

    def _drop(self, note_id: str) -> None:
        row = self._db.execute("SELECT rowid FROM notes WHERE id=?", (note_id,)).fetchone()
        if row:
            self._db.execute("DELETE FROM fts WHERE rowid=?", (row[0],))
            self._db.execute("DELETE FROM notes WHERE id=?", (note_id,))

    def keyword(self, query: str, k: int = 20) -> list[tuple[str, float]]:
        q = fts_query(query)
        if not q:
            return []
        with self._lock:
            return [(i, -s) for i, s in self._db.execute(
                "SELECT n.id, bm25(fts) FROM fts JOIN notes n ON n.rowid = fts.rowid "
                "WHERE fts MATCH ? ORDER BY bm25(fts) LIMIT ?", (q, k))]

    def semantic(self, qvec, k: int = 20) -> list[tuple[str, float]]:
        import numpy as np

        with self._lock:
            if self._cache is None:
                rows = self._db.execute("SELECT id, vec FROM notes WHERE vec IS NOT NULL").fetchall()
                ids = [r[0] for r in rows]
                mat = np.vstack([np.frombuffer(r[1], dtype="float32") for r in rows]) if rows else np.zeros((0, len(qvec)), "float32")
                self._cache = (ids, mat)
            ids, mat = self._cache
        if not ids:
            return []
        sims = mat @ qvec
        return [(ids[i], float(sims[i])) for i in np.argsort(-sims)[:k]]
