"""Hermes MemoryProvider adapter: the only module that imports Hermes code."""
from __future__ import annotations

import json
import logging
import threading
from typing import Any, Optional

from agent.memory_provider import MemoryProvider, RecallStatus, is_trivial_prompt

from . import catalog, replay, timewindow, usage
from .config import ConfigError, Settings, load_settings
from .embedder import make_embedder
from .index import Index
from .notes import NoteStore
from .search import Searcher
from .sources import Recall
from .tools import SCHEMAS, Tools
from .recall import MAX_ITEMS, status_label, contentless, habituate, profile, seen_path, upcoming, when

log = logging.getLogger(__name__)

PROMPT = (
    "Vault memory: durable facts live as markdown notes in the user's vault (Memory/) and relevant ones are "
    "recalled automatically each turn, possibly outdated. Use ms_remember only for durable facts, preferences and "
    "decisions the user stated or asked you to keep, never raw conversation or secrets; set expires for anything time-bound. "
    "To correct a stored fact call ms_remember with supersedes=<old id> instead of adding a duplicate. "
    "Add questions=[2-3 questions the note answers, in the user's words] so ms_search finds it. "
    "For a dated plan or deadline (trip, event, due date) add tag 'event' and set expires to the day after it ends; "
    "it then shows automatically in the two weeks before. "
    "Pass basis: 'user' if they said it, 'read: <what, date>' if you read it (email, booking, receipt), 'inferred' if you guessed. "
    "Pass about=[the people, places or things it concerns, e.g. 'Sam', 'the lake house'] so everything on one of them can be found. "
    "When the user or something you read confirms a recalled note is still true, call ms_verify with its id; "
    "the 'as of' date on recalled notes is the last time each was confirmed. "
    "Prediction error: when something you read (an email, booking, receipt, calendar entry) contradicts a recalled note, "
    "update that note right away with supersedes=<id> and basis='read: ...', and say so; don't wait for the user to notice. "
    "If a question about the user's own facts gets no matching note, say nothing is saved and look it up or ask; never fill the gap from a similar fact. "
    "For facts you inferred, or when unsure the user wants it kept, use ms_draft: drafts are not recalled until the user approves "
    "them (ms_review). ms_search finds anything not recalled; ms_forget hides a note."
)


class VaultMemoryProvider(MemoryProvider):
    def __init__(self, settings: Settings | None = None):
        self._settings = settings
        self._lock = threading.Lock()
        self._fp = None
        self._status: Optional[RecallStatus] = None
        self._tools: Tools | None = None
        self._primary = True

    # -- identity / availability ---------------------------------------------
    @property
    def name(self) -> str:
        return "memory_stem"

    def is_available(self) -> bool:
        try:
            s = self._settings or load_settings()
        except ConfigError:
            return False
        return s.vault_dir.is_dir()  # the vault exists; Memory/ is created on first write

    def unavailable_reason(self) -> str:
        try:
            return f"vault not found at {(self._settings or load_settings()).vault_dir}"
        except ConfigError as e:
            return str(e)

    # -- lifecycle -----------------------------------------------------------
    def initialize(self, session_id: str, **kwargs) -> None:
        s = self._settings = self._settings or load_settings(kwargs.get("hermes_home"))
        self.store = NoteStore(s.notes_dir)
        self.recall = Recall(self.store, s.vault_dir)
        embedder = make_embedder(s.model_name, s.model_cache)
        self.index = Index(s.index_path, embedder)
        self.searcher = Searcher.from_settings(s, self.index, embedder)
        primary = self._primary = kwargs.get("agent_context") in (None, "primary")  # subagents and cron only read
        self._tools = Tools(self.store, self.searcher, self._refresh, writable=primary, reader=self.recall)
        self._refresh()

    def _refresh(self) -> None:
        with self._lock:
            fp = self.recall.fingerprint()
            if fp != self._fp:
                self.store.reconcile()  # a draft moved into Memory/ by hand still retires the note it replaces
                self.index.sync(self.recall.all())
                catalog.write(self.store.root, self.store.all())
                catalog.write_hubs(self.store.root, self.store.all())
                self._fp = self.recall.fingerprint()

    def shutdown(self) -> None:
        pass

    # -- recall --------------------------------------------------------------
    def system_prompt_block(self) -> str:
        try:  # a map of what exists, so a missed search can still be followed by search
            t = catalog.titles(self.store.all()) if self._tools else ""
        except Exception:
            log.exception("memory_stem: titles failed")
            t = ""
        return PROMPT + profile(self._settings) + (f"\nSaved memory titles (ms_search finds the text):\n{t}" if t else "")

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        self._status = None
        self._last_query, self._last_recalled = query or "", set()
        if is_trivial_prompt(query) or self._tools is None:
            return ""
        try:
            self._refresh()
            s, lines, used, titles = self._settings, [], 0, []
            try:
                seen = json.loads(seen_path(s).read_text())
            except (OSError, ValueError):
                seen = {}
            soon = habituate(upcoming(self.store.all()), seen)
            try:
                seen_path(s).write_text(json.dumps(seen))
            except OSError:
                pass
            for n in soon:  # short: a reminder that it exists, search or search gives the rest
                lines.append(f"- [upcoming {when(n.expires)}; first reminder today] {n.title}: {n.body[:200]}")
                titles.append(n.title)
                used += len(lines[-1])
            shown = {n.id for n in soon}
            # working-memory cap: about 4 items per turn in total, upcoming events included, at least one search hit
            room = max(1, MAX_ITEMS - len(soon))
            hits = [] if contentless(query) else self.searcher.search(query, limit=min(s.top_k, room))
            for h in hits:
                n = self.recall.get(h.id)
                if not n or not n.active() or n.id in shown:
                    continue
                tag = n.id if n.source == "memory" or ":" not in n.id else f"{n.source} note, not a memory"
                how = f"; {n.basis}" if getattr(n, "basis", "") else ""
                line = f"- [{tag}{how}] {n.title} (as of {n.confirmed()}): {n.body[:400]}"
                if used + len(line) > s.max_chars:
                    break
                lines.append(line)
                titles.append(n.title if n.source == "memory" or ":" not in n.id else f"{n.title} (note)")
                used += len(line)
                self._last_recalled.add(n.id)
            # "this week" / "since September" pull in memories from that range; search has no topic to match
            if not contentless(query):
                for n in timewindow.extra(query, self.store.all(), shown | self._last_recalled, MAX_ITEMS - len(lines)):
                    how = f"; {n.basis}" if n.basis else ""
                    line = f"- [{n.id}{how}; in that time range] {n.title} (as of {n.confirmed()}): {n.body[:300]}"
                    if used + len(line) > s.max_chars:
                        break
                    lines.append(line)
                    titles.append(n.title)
                    used += len(line)
                    self._last_recalled.add(n.id)
        except Exception:  # recall must never break a turn
            log.exception("memory_stem: prefetch failed")
            return ""
        usage.bump(self._settings, [n.id for n in soon] + sorted(self._last_recalled))
        if not lines:
            return ""
        self._status = RecallStatus(status_label(titles), len(lines))
        return "Possibly relevant saved notes (verify dated facts before relying on them):\n" + "\n".join(lines)

    def recall_status(self) -> Optional[RecallStatus]:
        return self._status

    def sync_turn(self, user_content: str, assistant_content: str, **kwargs) -> None:
        pass  # deliberate: no auto-capture of conversation

    # -- tools ---------------------------------------------------------------
    def get_tool_schemas(self) -> list[dict[str, Any]]:
        return SCHEMAS

    def handle_tool_call(self, tool_name: str, args: dict[str, Any], **kwargs) -> str:
        if self._tools is None:
            return '{"ok": false, "error": "memory_stem not initialized"}'
        out = self._tools.handle(tool_name, args)
        if tool_name == "ms_search":
            self._note_miss(out)
            try:
                usage.bump(self._settings, [r["id"] for r in json.loads(out).get("results") or [] if ":" not in r["id"]], "searched")
            except (ValueError, TypeError):
                pass
        return out

    def _note_miss(self, out: str) -> None:
        """Recall missed if I had to ms_search and found a memory recall didn't inject. Log the user's wording
        against that memory so the nightly replay can teach it (shortcut: pairs with the last message only)."""
        q, recalled = getattr(self, "_last_query", ""), getattr(self, "_last_recalled", set())
        if not self._primary or not q or contentless(q):  # a cron prompt or subagent task is not the user's wording
            return
        try:
            res = json.loads(out).get("results") or []
        except ValueError:
            return
        top = next((r for r in res if ":" not in r["id"]), None)
        if top and top["id"] not in recalled and replay.related(q, top["text"]):
            replay.log(self._settings, q, top["id"])

    def backup_paths(self) -> list[str]:
        return [str((self._settings or load_settings()).notes_dir)]
