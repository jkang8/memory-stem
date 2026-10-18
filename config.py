"""Paths and tunables. Everything derives from hermes_home so profiles stay isolated."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    notes_dir: Path
    index_path: Path
    model_cache: Path
    model_name: str = DEFAULT_MODEL
    top_k: int = 3
    max_chars: int = 1500
    rel_margin: float = 0.05  # hits more than this below the top cosine are dropped; 1.0 = off. Swept: 0.05 cut avg hits 2.33 to 1.50, recall unchanged
    vault_penalty: float = 0.08  # cosine subtracted from non-Memory vault notes
    strong_cosine: float = 0.62  # at or above this, meaning alone is enough
    min_cosine: float = 0.60  # swept with the whole vault indexed; recall 18/18, junk 0/8

    @property
    def vault_dir(self) -> Path:
        return self.notes_dir.parent

    @property
    def evals_dir(self) -> Path:
        """Personal eval sets and the miss log. In the vault, not the repo, because they quote the user's life."""
        return self.notes_dir / "_evals"


def load_settings(hermes_home: str | os.PathLike | None = None) -> Settings:
    home = Path(hermes_home or os.environ.get("HERMES_HOME") or Path.home() / ".hermes")
    vault, notes = os.environ.get("VAULT_DIR"), os.environ.get("VAULT_MEMORY_DIR")
    if notes:
        notes_dir = Path(notes).expanduser()
    elif vault:
        notes_dir = Path(vault).expanduser() / "Memory"
    else:  # no default: guessing a path could read or write the wrong folder
        raise ConfigError("set VAULT_DIR to your notes folder (memories go in $VAULT_DIR/Memory, or set VAULT_MEMORY_DIR)")
    return Settings(
        notes_dir=notes_dir,
        index_path=home / "vault_memory" / "index.sqlite",  # data dir keeps its old name
        model_cache=home / "cache" / "fastembed",
    )
