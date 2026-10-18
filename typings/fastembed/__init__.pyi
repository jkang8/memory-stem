# The slice of fastembed embedder.py uses, so CI (numpy only) type-checks the same as a full install.
from collections.abc import Iterable, Iterator

import numpy as np

class TextEmbedding:
    def __init__(self, model_name: str, cache_dir: str | None = ...) -> None: ...
    def embed(self, documents: Iterable[str]) -> Iterator[np.ndarray]: ...
