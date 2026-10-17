"""memory_stem: a Hermes memory provider backed by markdown notes in a folder (the vault).

Layers (each file does one job, only provider.py touches Hermes):
  config -> notes (source of truth) -> sources -> embedder -> index (disposable SQLite) -> search -> recall -> tools -> provider
See README.md.
"""


def register(ctx):
    from .provider import VaultMemoryProvider  # lazy: keeps the core modules importable without Hermes

    ctx.register_memory_provider(VaultMemoryProvider())
