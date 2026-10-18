"""Where recalled notes come from: the Memory notes plus a read-only view of the rest of the vault, so recall
covers notes outside Memory/.
Credentials are excluded by filename, by content, or by `private: true` frontmatter; index pages, dashboards and
ID dumps are skipped as scaffolding. Nothing here writes; Recall only reads its NoteStore."""
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


_LINK = re.compile(r"!?\[\[[^\]]+\]\]|\[[^\]]*\]\([^)]+\)|https?://\S+")
_QUERY_BLOCK = re.compile(r"```(?:dataview|dataviewjs|tasks|query)\b.*?```", re.S | re.I)
_INLINE_QUERY = re.compile(r"`\$?=[^`]*`")  # Dataview inline expressions: `= this.file.name`
_SENTENCE = re.compile(r"[A-Za-z]{3,}\W+[A-Za-z]{3,}\W+[A-Za-z]{3,}\W+[A-Za-z]{3,}")
_ID_LIKE = re.compile(r"(?=[\w-]*\d)(?=[\w-]*[A-Za-z])[\w-]{8,}")


def scaffolding(body: str) -> bool:
    """Index pages, query dashboards and ID dumps. They have no prose for a question to match, so any search that
    reaches them is noise. Measured 2026-10-18: drops 25 of 443 vault notes."""
    lines = [ln for ln in body.splitlines() if ln.strip()]
    link_only = sum(1 for ln in lines if _LINK.search(ln) and len(_LINK.sub("", ln).strip(" -*>|#.:0123456789")) < 25)
    if len(lines) >= 3 and link_only / len(lines) >= 0.7:
        return True
    if _QUERY_BLOCK.search(body) and not _has_prose(_INLINE_QUERY.sub("", _QUERY_BLOCK.sub("", body))):  # a dashboard: queries, links and callouts
        return True
    tokens = body.split()
    return bool(tokens) and sum(1 for t in tokens if _ID_LIKE.fullmatch(t)) / len(tokens) >= 0.5


def _has_prose(text: str) -> bool:
    """At least one line that reads as a sentence once links and list, quote and heading marks are removed."""
    return any(len(t) >= 40 and _SENTENCE.search(t)
               for t in (_LINK.sub("", ln).strip(" -*>#|") for ln in text.splitlines()))


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
            if len(body) < 30 or scaffolding(body):  # not in `excluded`: that list audits the secret filter
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
