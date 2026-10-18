"""Where recalled notes come from: the Memory notes plus a read-only view of the rest of the vault, so recall
covers notes outside Memory/.
Credentials are excluded by filename, by content, or by `private: true` frontmatter. Nothing here writes; Recall only reads its NoteStore."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from .notes import Note, NoteStore, check_secret

SKIP_DIRS = {"Memory", "Sources", "Templates", "Attachments", "Bases"}  # plus any dot-folder (editor config, trash, .git)
_NAME = re.compile(r"\b(auth\w*|passw\w*|credentials?|creds?|login|tokens?|secrets?|seed|bitwarden|keys?|2fa|recovery|api[ _-]?(?:key|token|secret)s?)\b", re.I)
_TOKENS = re.compile(r"\b(?=[A-Z0-9]*\d)[A-Z0-9]{20,}\b|\b[A-Za-z0-9_-]{32,}\b|\b\w{5}-\w{4,5}(?: \w{5}-\w{4,5}){2,}")
_URL = re.compile(r"https?://\S+|www\.\S+")  # URL slugs look like tokens; drop them before the token check
_ID = re.compile(r"\bids?\b[:=]?\s+[\w-]{20,}", re.I)  # "id 1Wzd..." is a Drive file id, not a secret
_FM = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.S)


def sensitive(name: str, text: str) -> bool:
    if _NAME.search(name) or _TOKENS.search(_ID.sub(" ", _URL.sub(" ", text))):
        return True
    m = _FM.match(text)
    if m and re.search(r"^private:\s*true", m.group(1), re.M | re.I):
        return True
    try:
        check_secret(text)
    except ValueError:
        return True
    return False


class FolderSource:
    """A read-only folder of markdown notes. Ids are '<name>:<relative path>'."""

    def __init__(self, name: str, root: Path, skip: set[str] = SKIP_DIRS):
        self.name, self.root, self.skip = name, Path(root), skip
        self.excluded: list[str] = []

    def _files(self):
        for p in self.root.rglob("*.md"):
            rel = p.relative_to(self.root)
            if not (set(rel.parts[:-1]) & self.skip) and not any(x.startswith(".") for x in rel.parts):
                yield p, rel

    def notes(self) -> list[Note]:
        out, self.excluded = [], []
        for p, rel in self._files():
            try:
                text = p.read_text(encoding="utf-8")
                mtime = p.stat().st_mtime
            except (OSError, UnicodeDecodeError):
                continue
            if sensitive(p.stem, text):
                self.excluded.append(str(rel))
                continue
            m = _FM.match(text)
            body = (text[m.end():] if m else text).strip()
            if len(body) < 30:
                continue
            out.append(Note(id=f"{self.name}:{rel}", title=p.stem, body=body, created=dt.date.fromtimestamp(mtime).isoformat(),
                            source=self.name, path=p, mtime=mtime))
        return out

    def fingerprint(self):
        stats = [p.stat() for p, _ in self._files()]
        return len(stats), max((s.st_mtime_ns for s in stats), default=0)


class Recall:
    """Memory notes plus the read-only vault, behind the same all()/get()/fingerprint() as NoteStore."""

    def __init__(self, store: NoteStore, vault: Path):
        self.store, self.vault = store, FolderSource("vault", vault)

    @property
    def excluded(self) -> list[str]:
        """Vault notes the secret filter dropped on the last read. The maintenance skill prints this."""
        return self.vault.excluded

    def all(self) -> list[Note]:
        return self.store.all() + self.vault.notes()

    def get(self, note_id: str) -> Note | None:
        if ":" not in note_id:
            return self.store.get(note_id)
        return next((n for n in self.vault.notes() if n.id == note_id), None)

    def fingerprint(self):
        return self.store.fingerprint(), self.vault.fingerprint()
