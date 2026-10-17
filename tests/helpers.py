"""Shared fakes. FakeEmbedder maps words to fixed axes so 'semantic' behaviour is deterministic."""
import numpy as np

from memory_stem.embedder import Embedder

AXES = {"hotel": 0, "stay": 0, "inn": 0, "bus": 1, "commute": 1, "work": 1, "tax": 2, "irs": 2, "state": 2}


class FakeEmbedder(Embedder):
    name = "fake"

    def embed(self, texts):
        out = np.zeros((len(texts), 4), dtype="float32")
        for r, t in enumerate(texts):
            for w in t.lower().replace(".", " ").split():
                if w in AXES:
                    out[r, AXES[w]] += 1
            out[r, 3] = 0.05  # keep vectors non-zero
        return out / np.linalg.norm(out, axis=1, keepdims=True)
