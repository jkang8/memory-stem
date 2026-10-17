"""Miss log for the nightly replay. When recall injected nothing useful but search then found a memory,
The user's wording and that memory's id are appended here; the dream job can add the wording as a question on the note.
Logging only: nothing here edits notes."""
from __future__ import annotations

import datetime as dt
import json
import re

from .config import load_settings

LOG = "replay_log.jsonl"
_WORD = re.compile(r"[a-z0-9]{4,}")


def related(query: str, text: str) -> bool:
    """Cheap guard: the found note shares at least one real word with the question (not a search on a new topic)."""
    return bool(set(_WORD.findall(query.lower())) & set(_WORD.findall(text.lower())))


def log(settings, query: str, note_id: str) -> None:
    try:
        p = (settings or load_settings()).index_path.parent / LOG
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"day": dt.date.today().isoformat(), "q": query[:300], "id": note_id}) + "\n")
    except OSError:
        pass
