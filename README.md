# Memory Stem

Long-term memory for [Hermes Agent](https://hermes-agent.nousresearch.com), stored as plain markdown files.

Each memory is one note in a folder you choose. Before every turn, Memory Stem recalls up to four relevant notes. The agent saves and corrects memories through tools. Nothing is captured automatically.

## Install

```sh
hermes plugins install https://github.com/jkang8/memory-stem
hermes pm install
```

In `~/.hermes/config.yaml`:

```yaml
memory:
  provider: memory_stem
```

In `~/.hermes/.env`:

```sh
VAULT_DIR=/path/to/notes
```

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `VAULT_DIR` | yes | Folder of markdown notes (the vault). Other notes here are searchable, read-only |
| `VAULT_MEMORY_DIR` | no | Where memories are written. Default `$VAULT_DIR/Memory` |

There is no default path. If neither variable is set, the provider reports itself unavailable.

Optional files in the memory folder. Edits take effect on the next turn.

| File | Purpose |
|------|---------|
| `Profile.md` | Bullet points included in every session |
| `Aliases.md` | Nicknames expanded in searches, e.g. `- the shop = Acme Bike Repair` |

## Tools

| Tool | Description |
|------|-------------|
| `ms_remember` | Save a fact. `supersedes` corrects an existing note and keeps the old one as history |
| `ms_search` | Search memories and vault notes |
| `ms_draft` | Propose a memory. Drafts are not recalled until approved |
| `ms_review` | List, approve or reject drafts |
| `ms_forget` | Hide a memory from recall. The file is kept |
| `ms_verify` | Mark a memory as confirmed still true today. Recall shows it "as of" that date |

`ms_remember` and `ms_draft` accept `tags`, `expires` (YYYY-MM-DD), `questions` (phrasings that should find the note), `basis` (where the fact came from) and `about` (people, places or things the note concerns). A note tagged `event` with an `expires` date is recalled once a day in the two weeks before it expires, and otherwise only when search matches.

Generated files, never edited by hand: `Index.md` (every current memory) and `About/<subject>.md` (one page per `about` subject, so Obsidian's graph links related notes). Recall counts live in the runtime data dir as `usage.json`; `python -m memory_stem.usage` lists the most recalled memories and the ones unused for 30 days.

## Note format

```markdown
---
id: 20261016-1750-4ab8
verified: 2026-10-17
tags: [travel, event]
about: [Harbor Inn]
expires: 2026-10-25
questions: [Where am I staying?]
---
Hotel is Harbor Inn, Oct 18-24.
```

Notes are the source of truth. The search index (SQLite plus local [fastembed](https://github.com/qdrant/fastembed) embeddings) is a cache and rebuilds from the files. Files that look like credentials are never indexed.

## Development

```sh
cd ~/.hermes/plugins
uv run --no-project --with fastembed --with numpy \
  python -m unittest discover -s memory_stem/tests -t .
```

Recall evals read personal question sets from `$VAULT_MEMORY_DIR/_evals/` and run with `python -m memory_stem.evaluate [--heldout]`.

## License

[MIT](LICENSE)
