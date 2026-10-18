# Memory Stem

A memory provider plugin for Hermes Agent. Each memory is one markdown note in the user's vault (`$VAULT_DIR/Memory/`),
and before every turn the provider recalls a few relevant ones through hybrid keyword and local-embedding search. The
notes are the source of truth; everything else is a cache that rebuilds from them. This repo is public.

## Map

The repo root is the `memory_stem` package. Layers, lowest first (each module's docstring says what it owns):

- `config.py`: the one `Settings` object; paths and tunables come from here, never from ad hoc env reads
- `notes.py`: `NoteStore`, the markdown files. `sources.py`: the read-only rest of the vault
- `embedder.py`, `index.py` (disposable SQLite), `search.py` (hybrid ranking)
- `recall.py`, `timewindow.py`, `catalog.py`: what gets injected each turn, and the generated `Index.md` and `About/` pages
- `tools.py`: the `ms_*` tools. `provider.py`: the Hermes adapter, the only module that imports Hermes
- Maintenance CLIs, each runnable as `python -m memory_stem.<name>`: `evaluate`, `autoapprove`, `stale`, `usage`
- `scripts/gate.sh` and `scripts/privacy_guard.py`: the quality gate. `tests/`: unit tests with a fake embedder

## Commands

Run from the folder that contains the package (`memory_stem` must be importable by that name):

```sh
uv run --no-project --with fastembed --with numpy \
  python -m unittest discover -s memory_stem/tests -t .    # unit tests: "OK" at the end
memory_stem/scripts/gate.sh                               # tests, privacy guard, recall evals vs origin/main
```

Recall evals run against the real vault, so they need `VAULT_DIR`. Use the same `uv run` prefix:
`python -m memory_stem.evaluate` prints `recall: 19/19`-style counts for the tuned set.

`scripts/gate.sh` ends with `GATE PASS` or names what failed. Paste its full output in every PR.

## Hard rules

- **No personal data in the repo, commits or PR text.** The evals, the miss log and the notes quote the owner's
  life. `scripts/privacy_guard.py` checks for emails, secrets and the terms in a local denylist (`$MEMORY_STEM_DENYLIST`).
  The denylist never enters the repo. Tests use made-up data.
- **Heldout evals are frozen.** `heldout*.json` were written before any scoring. Never tune thresholds, wording,
  aliases or questions against them. `tuned.json` is the set you may tune against.
- **Never merge PRs and never force-push.** One change per PR, tests first. The maintainer merges.
- **Every tool is listed in `plugin.yaml` `provides_tools`,** or Hermes won't expose it.

## Where things live outside the repo

- Eval sets and the reported-miss log: `$VAULT_DIR/Memory/_evals/`. Never copy them into the repo.
- Runtime data (index, usage counts, replay and autoapprove logs, upcoming-event state): the Hermes data dir,
  `$HERMES_HOME/vault_memory/`. Deleting the index is safe; it rebuilds on the next sync.
- Drafts awaiting approval: `$VAULT_DIR/Memory/_inbox/`. `NoteStore` reads only the top level, so they're never recalled.

## Traps

- The installed plugin folder is the live checkout Hermes loads. Make changes in a git worktree **outside** the
  Hermes plugins folder, or Hermes discovers the worktree as another plugin.
- Plugin code loads only when the gateway restarts, so a broken import fails silently until then.
- Hermes scripts, scheduled jobs and the maintenance skill call the module CLIs and `memory_stem.sources.FolderSource` by name.
  Grep for callers before renaming or moving one.
- `Profile.md`, `Aliases.md` and `Index.md` sit in `Memory/` without an `id`, so `NoteStore` doesn't treat them as memories.

## More

- `README.md`: install, configuration, tools and the note format
- `CONTRIBUTING.md`: the PR rules
- `docs/decisions/`: decisions that look changeable but aren't
