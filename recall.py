"""What gets recalled each turn, independent of Hermes: the always-on profile, upcoming events, the
contentless-reply skip, and Recall (Memory notes plus the read-only rest of the vault behind one interface)."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from .config import Settings, load_settings
from .notes import Note, NoteStore
from .sources import FolderSource

PROFILE = "Profile.md"  # no `id` in its frontmatter, so NoteStore never treats it as a memory
_FILLER = frozenset("""a an the and or but so to it its this that these those do does did is are be been i im i'm you we us me my
let let's lets go going gogo vo yes yeah yep yup ok okay k kk sure alright fine good great nice cool perfect awesome
please pls thanks thank ty approve approved approves accept accepted sounds sound looks look like that's thats
right correct exactly agreed agree same again more one too also now then just go ahead proceed continue next keep
both all them no nope nah wait hmm hm oh ah lol haha in on of at for with up out if as by from into about
it's its we're were there here what one's ones""".split())


def contentless(text: str) -> bool:
    """A reply that only says 'go on' ("Let's go", "Approve", "?"): searching it recalls noise, so skip search.
    Upcoming events still show. Anything with one real word (a name, a noun, a number) still searches."""
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    return not [w for w in words if w not in _FILLER and len(w) > 1]


MAX_ITEMS = 4  # recalled notes per turn, upcoming events included
UPCOMING_DAYS = 14  # an `event` note starts surfacing this many days before its expires date


def upcoming(notes, today: dt.date | None = None, days: int = UPCOMING_DAYS, cap: int = 4) -> list:
    """Prospective memory: dated plans (tag `event`, expires = day after) surface by date, not by search match."""
    today = today or dt.date.today()
    out = []
    for n in notes:
        if not n.active() or "event" not in n.tags or not n.expires:
            continue
        try:
            left = (dt.date.fromisoformat(n.expires) - today).days
        except ValueError:
            continue
        if 0 < left <= days:
            out.append((left, n))
    return [n for _, n in sorted(out, key=lambda x: x[0])[:cap]]


def habituate(soon, seen: dict, today: dt.date | None = None) -> list:
    """Remind of each upcoming event once a day, like a person would; after that it shows only when search
    matches the message. `seen` (id -> ISO day) is updated in place."""
    day = (today or dt.date.today()).isoformat()
    out = [n for n in soon if seen.get(n.id) != day]
    seen.update((n.id, day) for n in out)
    return out


def when(expires: str, today: dt.date | None = None) -> str:
    """'today', 'tomorrow', 'in 5 days': an event note's expires is the day after it ends, so the event is the day before."""
    try:
        d = (dt.date.fromisoformat(expires) - dt.timedelta(days=1) - (today or dt.date.today())).days
    except ValueError:
        return f"ends {expires}"
    return {0: "today", 1: "tomorrow"}.get(d, f"in {d} days" if d > 1 else "ended")


def seen_path(s: Settings | None):
    return (s or load_settings()).index_path.parent / "upcoming_seen.json"


def profile(s: Settings | None, cap: int = 2500) -> str:
    """The user's always-on profile: facts search kept missing (an office, accounts). Loaded every session, capped."""
    try:
        text = ((s or load_settings()).notes_dir / PROFILE).read_text(encoding="utf-8")
    except OSError:
        return ""
    body = re.sub(r"\A---\r?\n.*?\r?\n---\r?\n?", "", text, flags=re.S)
    body = "\n".join(ln for ln in body.splitlines() if ln.lstrip().startswith("-")).strip()
    return f"\nUser profile (always true unless they say otherwise):\n{body[:cap]}" if body else ""


class Recall:
    """Memory notes plus the read-only vault, behind the same all()/get()/fingerprint() as NoteStore."""

    def __init__(self, store: NoteStore, vault: Path):
        self.store = store
        self.sources = [FolderSource("vault", vault)]

    def vault_notes(self) -> list[Note]:
        return [n for s in self.sources for n in s.notes()]

    def all(self) -> list[Note]:
        return self.store.all() + self.vault_notes()

    def get(self, note_id: str) -> Note | None:
        if ":" not in note_id:
            return self.store.get(note_id)
        return next((n for n in self.vault_notes() if n.id == note_id), None)

    def fingerprint(self):
        return (self.store.fingerprint(), *(s.fingerprint() for s in self.sources))


def status_label(titles: list[str], show: int = 2, width: int = 30) -> str:
    """Label for the chat's recall line, e.g. 'Vault memory: Gala · Hotel +1 more', so a wrong recall is visible."""
    cut = [t if len(t) <= width else t[: width - 1].rstrip() + "…" for t in titles[:show]]
    more = f" +{len(titles) - show} more" if len(titles) > show else ""
    return f"Vault memory: {' · '.join(cut)}{more}" if cut else "Vault memory"
