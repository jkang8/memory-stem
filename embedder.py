"""Embedding backends. NullEmbedder means "keyword search only"; the system works without vectors."""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class Embedder:
    """Null object: no vectors, search falls back to keywords."""
    name = "none"

    def embed(self, texts: list[str]):
        return None

    def embed_query(self, text: str):
        """Embed a search query. Same shape as embed([text]); models that need a query instruction override this."""
        return self.embed([text])


# bge models are trained to see this instruction on queries (not on documents); measured: fewer junk hits at the same recall
_BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


class FastEmbedder(Embedder):
    def __init__(self, model: str, cache_dir):
        from fastembed import TextEmbedding  # local ONNX, no network once the model is cached

        self.name = model
        self._model = TextEmbedding(model, cache_dir=str(cache_dir))

    def embed(self, texts: list[str]):
        import numpy as np

        v = np.array(list(self._model.embed(texts)), dtype="float32")
        return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-9)

    def embed_query(self, text: str):
        return self.embed([(_BGE_QUERY_PREFIX if "bge" in self.name.lower() else "") + text])


def make_embedder(model: str, cache_dir) -> Embedder:
    try:
        return FastEmbedder(model, cache_dir)
    except Exception as e:  # missing package or model: degrade, never fail the agent
        log.warning("memory_stem: semantic search off (%s); using keyword search only", e)
        return Embedder()
