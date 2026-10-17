"""The model-facing tools. Pure functions of (store, searcher): no Hermes imports."""
from __future__ import annotations

import json

from . import checks
from .notes import NoteStore
from .search import Searcher
from .stale import warn

SCHEMAS = [
    {"name": "ms_remember",
     "description": "Save one durable fact, preference or decision as a note in the user's vault. Never raw chat, one-off task progress or secrets. "
                    "To correct an existing memory, pass supersedes=<old id> instead of adding a duplicate.",
     "parameters": {"type": "object", "properties": {
         "content": {"type": "string", "description": "The memory, one idea, plain declarative sentences."},
         "title": {"type": "string", "description": "Short note title (becomes the file name). Optional."},
         "tags": {"type": "array", "items": {"type": "string"}},
         "questions": {"type": "array", "items": {"type": "string"}, "description": "2-3 questions this note answers, in the user's words."},
         "expires": {"type": "string", "description": "YYYY-MM-DD after which it stops being recalled. Set it for anything time-bound: trips, deadlines, 'as of' status."},
         "supersedes": {"type": "string", "description": "Id of the memory this replaces. Optional."},
         "basis": {"type": "string", "description": "Where the fact came from: 'user' (they said it), 'read: <what, date>' (an email, booking, document), or 'inferred' (your guess). Inferred facts lose to the others."},
         "about": {"type": "array", "items": {"type": "string"}, "description": "People, places or things the note is about, e.g. ['Sam', 'the lake house']. Optional."},
         },
         "required": ["content"]}},
    {"name": "ms_verify",
     "description": "Mark a current memory as confirmed still true today (the user said so, or you read something that matches it). "
                    "Changes nothing else. If the fact changed, use ms_remember with supersedes instead.",
     "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
    {"name": "ms_search",
     "description": "Search saved memories by meaning and keywords. Returns ids, titles and text.",
     "parameters": {"type": "object", "properties": {
         "query": {"type": "string"}, "limit": {"type": "integer", "default": 5}}, "required": ["query"]}},
    {"name": "ms_forget",
     "description": "Hide a memory by id (the note stays in the vault marked forgotten; the user can delete it).",
     "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}},
    {"name": "ms_draft",
     "description": "Propose a memory for the user to approve. Use it for facts you inferred, for end-of-session or cron summaries, and whenever "
                    "you are unsure he wants it kept. Drafts are not recalled until approved with ms_review. Same fields as ms_remember.",
     "parameters": {"type": "object", "properties": {
         "content": {"type": "string"}, "title": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}},
         "questions": {"type": "array", "items": {"type": "string"}, "description": "2-3 questions this note answers, in the user's words."},
         "expires": {"type": "string", "description": "YYYY-MM-DD. Set it for anything time-bound."},
         "supersedes": {"type": "string", "description": "Id of the saved memory this would replace. Optional."},
         "basis": {"type": "string", "description": "Where the fact came from: 'user' (they said it), 'read: <what, date>' (an email, booking, document), or 'inferred' (your guess). Inferred facts lose to the others."},
         "about": {"type": "array", "items": {"type": "string"}, "description": "People, places or things the note is about, e.g. ['Sam', 'the lake house']. Optional."},
         },
         "required": ["content"]}},
    {"name": "ms_review",
     "description": "List, approve or reject drafts. action=list shows them; action=approve or reject takes id (full id, its last 4 characters, "
                    "or 'all'). Approving moves the draft into the vault memory and retires any memory it supersedes.",
     "parameters": {"type": "object", "properties": {
         "action": {"type": "string", "enum": ["list", "approve", "reject"]}, "id": {"type": "string"}},
         "required": ["action"]}},
]


class Tools:
    def __init__(self, store: NoteStore, searcher: Searcher, refresh, writable: bool = True, reader=None):
        self.reader = reader or store
        self.store, self.searcher, self.refresh, self.writable = store, searcher, refresh, writable
        self.inbox = NoteStore(store.root / "_inbox")  # drafts live here; NoteStore only reads the top level, so they are never recalled

    def handle(self, name: str, args: dict) -> str:
        try:
            return json.dumps(getattr(self, "_" + name.removeprefix("ms_"))(**args))
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            return json.dumps({"ok": False, "error": str(e).strip("\"'")})

    def _remember(self, content, title="", tags=(), expires="", supersedes="", questions=(), basis="", about=()):
        if not self.writable:
            raise ValueError("memory writes are disabled in this context")
        old = self.store.get(supersedes) if supersedes else None
        similar = [] if supersedes else self._similar(content)
        if old is not None and not about:
            about = old.about  # a correction keeps what the note was about
        n = self.store.add(content, title=title, tags=tuple(tags), expires=expires, supersedes=supersedes,
                           questions=tuple(questions), basis=basis, about=tuple(about))
        self.refresh()
        out = {"ok": True, "id": n.id, "note": n.title, "superseded": supersedes or None}
        notes = [w] if (w := warn(content, expires)) else []
        if old is not None:
            others = [x.body for x in self.store.all() if x.active() and x.id not in (n.id, old.id)]
            notes += checks.review_supersede(old.body, n.body, others)
        if similar:
            notes.append("existing notes may already say this; if so, pass supersedes=<id> instead: " + "; ".join(similar))
        return {**out, "warning": " | ".join(notes)} if notes else out

    def _similar(self, content: str) -> list[str]:
        """Current memories nearly identical in meaning: likely duplicates. Search ranking alone flagged 62 of 63 notes,
        so this uses raw cosine against checks.DUPLICATE instead."""
        try:
            qv = self.searcher.embedder.embed([content])
            if qv is None:
                return []
            hits = self.searcher.index.semantic(qv[0], 5)
        except Exception:
            return []
        out = []
        for i, c in hits:
            m = self.store.get(i) if c >= checks.DUPLICATE and ":" not in i else None
            if m and m.active():
                out.append(f"{m.id} ({m.title}, {c:.2f})")
        return out

    def _search(self, query, limit=5):
        self.refresh()
        out = []
        for h in self.searcher.search(query, limit=int(limit)):
            n = self.reader.get(h.id)
            if n and n.active():
                r = {"id": n.id, "note": n.title, "created": n.created, "text": n.body}
                r.update({k: v for k, v in (("verified", n.verified), ("basis", n.basis), ("about", list(n.about))) if v})
                out.append(r)
        return {"ok": True, "results": out}

    def _verify(self, id):
        if not self.writable:
            raise ValueError("memory writes are disabled in this context")
        n = self.store.verify(id)
        self.refresh()
        return {"ok": True, "id": n.id, "note": n.title, "verified": n.verified}

    def _forget(self, id):
        if not self.writable:
            raise ValueError("memory writes are disabled in this context")
        n = self.store.forget(id)
        self.refresh()
        return {"ok": True, "id": n.id, "note": n.title}

    def _draft(self, content, title="", tags=(), expires="", supersedes="", questions=(), basis="inferred", about=()):
        # allowed in read-only contexts (cron, subagents): a draft is inert until the user approves it
        old = self.store.get(supersedes) if supersedes else None
        if supersedes and old is None:
            raise KeyError(f"no memory with id {supersedes}")
        about = about or (old.about if old else ())
        n = self.inbox.add(content, title=title, tags=tuple(tags), expires=expires, supersedes=supersedes,
                           source="ms_draft", mark_old=False, questions=tuple(questions), basis=basis, about=tuple(about))
        out = {"ok": True, "id": n.id, "note": n.title, "status": "draft; not recalled until the user approves it"}
        return {**out, "warning": w} if (w := warn(content, expires)) else out

    def _pick(self, id):
        drafts = self.inbox.all()
        if id == "all":
            return drafts
        hit = [n for n in drafts if n.id == id] or [n for n in drafts if n.id.endswith(id)]
        if len(hit) != 1:
            raise KeyError(f"{'no' if not hit else 'several'} drafts match {id!r}")
        return hit

    def _review(self, action="list", id=""):
        if action == "list":
            return {"ok": True, "drafts": [{"id": n.id, "note": n.title, "text": n.body, "supersedes": n.supersedes or None,
                                            "expires": n.expires or None} for n in self.inbox.all()]}
        if action not in ("approve", "reject"):
            raise ValueError("action must be list, approve or reject")
        if not self.writable:
            raise ValueError("memory writes are disabled in this context")
        if not id:
            raise ValueError("id is required (full id, last 4 characters, or 'all')")
        done = []
        for n in self._pick(id):
            if action == "approve":
                self.inbox.move_to(n.id, self.store)
            else:
                self.inbox.discard(n.id)
            done.append(n.title)
        self.store.reconcile()
        self.refresh()
        return {"ok": True, {"approve": "approved", "reject": "rejected"}[action]: done}
