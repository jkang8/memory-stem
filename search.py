"""Hybrid search. With vectors: semantic hits above a cutoff (middle-band hits also need a keyword match), ranked by fusing semantic and keyword ranks.
Without vectors: keyword hits. Keyword-only hits are dropped when vectors exist, because a stray common word
should not pull a note into the prompt."""
from __future__ import annotations

from dataclasses import dataclass

from . import aliases as _aliases
from .config import Settings
from .embedder import Embedder
from .index import Index


@dataclass(frozen=True)
class Hit:
    id: str
    score: float


class Searcher:
    def __init__(self, index: Index, embedder: Embedder, min_cosine: float, rrf_k: int = 60, strong_cosine: float = 0.65,
                 rel_margin: float = 1.0, vault_penalty: float = 0.0, aliases=None):
        self.index, self.embedder, self.rrf_k, self.rel_margin = index, embedder, rrf_k, rel_margin
        self.min_cosine, self.strong_cosine, self.vault_penalty = min_cosine, strong_cosine, vault_penalty
        self.aliases = aliases or {}

    @classmethod
    def from_settings(cls, s: Settings, index: Index, embedder: Embedder) -> Searcher:
        """The configured searcher. The provider and the evals both build it here, so the evals score what runs live."""
        return cls(index, embedder, s.min_cosine, strong_cosine=s.strong_cosine, rel_margin=s.rel_margin,
                   vault_penalty=s.vault_penalty, aliases=_aliases.load(s.notes_dir))

    def _penalty(self, note_id: str) -> float:
        return self.vault_penalty if ":" in note_id else 0.0  # vault ids are 'vault:<path>'; curated memories win ties

    def search(self, query: str, limit: int = 3) -> list[Hit]:
        query = _aliases.expand(query, self.aliases)
        kw = self.index.keyword(query)
        qv = self.embedder.embed_query(query)
        sem = []
        if qv is not None:
            sem = sorted(((i, c - self._penalty(i)) for i, c in self.index.semantic(qv[0], 60)), key=lambda x: -x[1])
            sem = [(i, c) for i, c in sem if c >= self.min_cosine]
        kw_ids = {i for i, _ in kw}
        if sem and self.rel_margin < 1.0:  # drop hits far below the best one: related is not relevant
            top = sem[0][1]
            sem = [(i, c) for i, c in sem if c >= top - self.rel_margin]
        # meaning alone is trusted only above strong_cosine; in the middle band a keyword match must agree
        keep = {i for i, c in sem if c >= self.strong_cosine or i in kw_ids} if qv is not None else kw_ids
        score: dict[str, float] = {}
        for ranked in (sem, kw):
            for rank, (i, _) in enumerate(ranked):
                if i in keep:
                    score[i] = score.get(i, 0.0) + 1.0 / (self.rrf_k + rank)
        return [Hit(i, s) for i, s in sorted(score.items(), key=lambda kv: -kv[1])[:limit]]
