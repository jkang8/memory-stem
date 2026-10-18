"""Markdown note store: one file per memory, frontmatter + body. The vault is the source of truth;
everything else (index, embeddings) can be deleted and rebuilt from these files."""
from __future__ import annotations

import datetime as dt
import os
import re
import secrets
from dataclasses import dataclass, replace
from pathlib import Path

CURRENT, SUPERSEDED, FORGOTTEN = "current", "superseded", "forgotten"

# Last line of defense, not a scanner: refuses obvious secrets. Credentials belong in the vault (browser_vault), not here.
_SECRET = re.compile(
    r"-----BEGIN|\b(?:sk|ghp|gho|xox[bp])[-_][A-Za-z0-9_-]{16,}"
    r"|(?:password|passwd|pwd|secret|api[_-]?key|token)\s*[:=]\s*\S{6,}|\b(?:\d[ -]?){13,19}\b",
    re.I,
)
_BAD_NAME = re.compile(r'[\\/:*?"<>|#^\[\]]')
_FIELDS = ("id", "created", "verified", "source", "basis", "status", "expires", "supersedes", "superseded_by")
_LISTS = ("tags", "about", "questions")


@dataclass
class Note:
    id: str
    title: str
    body: str
    created: str
    verified: str = ""  # last day the fact was confirmed still true; blank = only as of `created`
    source: str = "agent"
    basis: str = ""  # where the fact came from: "user" (legacy "john"), "read: <what, date>", or "inferred"; blank = not recorded
    status: str = CURRENT
    tags: tuple[str, ...] = ("memory",)
    questions: tuple[str, ...] = ()  # questions this note answers; embedded and indexed with the text
    about: tuple[str, ...] = ()  # people, places and things the note is about ("Sam", "the lake house"); indexed
    expires: str = ""
    supersedes: str = ""
    superseded_by: str = ""
    path: Path | None = None
    mtime: float = 0.0

    def expired(self, today: str | None = None) -> bool:
        return bool(self.expires) and self.expires < (today or dt.date.today().isoformat())

    def active(self) -> bool:
        return self.status == CURRENT and not self.expired()

    def confirmed(self) -> str:
        """Last day the note was known true: verified if set, else created."""
        return max(self.verified, self.created)

    def search_text(self) -> str:
        # `about` is keyword-indexed only (index.py): embedding the names diluted meaning and cost 2/125 recall
        return f"{self.title}. {self.body}" + (" Questions: " + " ".join(self.questions) if self.questions else "")


def check_secret(text: str) -> None:
    if _SECRET.search(text):
        raise ValueError("looks like a secret (password, token, key or card number); store where to find it, not the value")


def render(n: Note) -> str:
    lines = ["---"]
    lines += [f"{f}: {getattr(n, f)}" for f in _FIELDS if getattr(n, f)]
    lines += ["tags:", *[f"  - {t}" for t in n.tags]]
    if n.about:
        lines += ["about:", *[f"  - {a}" for a in n.about]]
    if n.questions:
        lines += ["questions:", *[f'  - "{q.replace(chr(34), chr(39))}"' for q in n.questions]]
    lines += ["---", n.body.strip(), ""]
    return "\n".join(lines)


def parse(text: str, path: Path) -> Note | None:
    m = re.match(r"---\n(.*?)\n---\n?(.*)\Z", text, re.S)
    if not m:
        return None
    meta: dict[str, str] = {}
    lists: dict[str, list[str]] = {k: [] for k in _LISTS}
    key = ""
    for line in m.group(1).splitlines():
        if key in lists and line.lstrip().startswith("- "):
            lists[key].append(line.lstrip()[2:].strip().strip('"'))
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if key in lists and val.startswith("["):
            lists[key] += [t.strip() for t in val.strip("[]").split(",") if t.strip()]
        else:
            meta[key] = val
    if not meta.get("id"):
        return None
    return Note(
        id=meta["id"], title=path.stem, body=m.group(2).strip(), created=meta.get("created", ""), verified=meta.get("verified", ""),
        source=meta.get("source", "agent"), basis=meta.get("basis", ""), status=meta.get("status", CURRENT),
        tags=tuple(lists["tags"]) or ("memory",), questions=tuple(lists["questions"]), about=tuple(lists["about"]),
        expires=meta.get("expires", ""), supersedes=meta.get("supersedes", ""),
        superseded_by=meta.get("superseded_by", ""), path=path, mtime=path.stat().st_mtime,
    )


def _title_from(body: str) -> str:
    first = body.strip().splitlines()[0]
    cut = first[:60].rsplit(" ", 1)[0] if len(first) > 60 else first
    return _BAD_NAME.sub(" -", cut).strip(" .,-") or "memory"


class NoteStore:
    def __init__(self, root: str | os.PathLike):
        self.root = Path(root)

    def all(self) -> list[Note]:
        notes = []
        for p in sorted(self.root.glob("*.md")) if self.root.is_dir() else []:
            try:
                n = parse(p.read_text(encoding="utf-8"), p)
            except (OSError, UnicodeDecodeError):
                continue
            if n:
                notes.append(n)
        return notes

    def get(self, note_id: str) -> Note | None:
        return next((n for n in self.all() if n.id == note_id), None)

    def fingerprint(self) -> tuple[int, int]:
        """Cheap change detector: (file count, newest mtime)."""
        stats = [p.stat() for p in self.root.glob("*.md")] if self.root.is_dir() else []
        return len(stats), max((s.st_mtime_ns for s in stats), default=0)

    def add(self, body: str, *, title: str = "", tags: tuple[str, ...] = (), source: str = "agent",
            expires: str = "", supersedes: str = "", created: str = "", mark_old: bool = True,
            questions: tuple[str, ...] = (), basis: str = "", about: tuple[str, ...] = ()) -> Note:
        body = body.strip()
        if not body:
            raise ValueError("empty memory")
        check_secret(f"{title}\n{body}")
        old = None
        if supersedes and mark_old:
            old = self.get(supersedes)
            if old is None:
                raise KeyError(f"no memory with id {supersedes}")
        self.root.mkdir(parents=True, exist_ok=True)
        nid = dt.datetime.now().strftime("%Y%m%d-%H%M") + "-" + secrets.token_hex(2)
        name = _BAD_NAME.sub(" -", title).strip() if title else _title_from(body)
        path = self.root / f"{name}.md"
        if path.exists():
            path = self.root / f"{name} {nid[-4:]}.md"
        note = Note(id=nid, title=path.stem, body=body, created=created or dt.date.today().isoformat(), source=source,
                    tags=tuple(dict.fromkeys(("memory", *tags))), expires=expires, supersedes=supersedes, path=path,
                    questions=tuple(questions), basis=" ".join(basis.split())[:120],
                    about=tuple(dict.fromkeys(a.strip() for a in about if a.strip())))
        self._write(note)
        if old:
            self._write(replace(old, status=SUPERSEDED, superseded_by=nid))
        return note

    def forget(self, note_id: str) -> Note:
        n = self.get(note_id)
        if n is None:
            raise KeyError(f"no memory with id {note_id}")
        n = replace(n, status=FORGOTTEN)
        self._write(n)
        return n

    def restore(self, note_id: str) -> Note:
        """Make a superseded or forgotten note current again. Retire its replacement first (as autoapprove.revert
        does), or reconcile() supersedes it again on the next refresh."""
        n = self.get(note_id)
        if n is None:
            raise KeyError(f"no memory with id {note_id}")
        n = replace(n, status=CURRENT, superseded_by="")
        self._write(n)
        return n

    def verify(self, note_id: str, day: str = "") -> Note:
        """Stamp a current note as confirmed true today. Changes no content."""
        n = self.get(note_id)
        if n is None or n.status != CURRENT:
            raise KeyError(f"no current memory with id {note_id}")
        n = replace(n, verified=day or dt.date.today().isoformat())
        self._write(n)
        return n

    def reconcile(self) -> int:
        """Finish supersedes links made outside add() (a draft moved into Memory/, or a hand edit): retire the older note."""
        notes = {n.id: n for n in self.all()}
        fixed = 0
        for n in notes.values():
            old = notes.get(n.supersedes) if n.supersedes and n.active() else None
            if old and old.status == CURRENT:
                self._write(replace(old, status=SUPERSEDED, superseded_by=n.id))
                fixed += 1
        return fixed

    def move_to(self, note_id: str, dest: "NoteStore") -> Path:
        n = self.get(note_id)
        if n is None:
            raise KeyError(f"no memory with id {note_id}")
        dest.root.mkdir(parents=True, exist_ok=True)
        path = dest.root / n.path.name
        if path.exists():
            path = dest.root / f"{n.path.stem} {n.id[-4:]}.md"
        os.replace(n.path, path)
        return path

    def discard(self, note_id: str) -> Note:
        n = self.get(note_id)
        if n is None:
            raise KeyError(f"no memory with id {note_id}")
        n.path.unlink()
        return n

    @staticmethod
    def _write(n: Note) -> None:
        tmp = n.path.with_suffix(".tmp")
        tmp.write_text(render(n), encoding="utf-8")
        os.replace(tmp, n.path)
