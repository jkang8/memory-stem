# Memory Stem

Long-term memory for [Hermes Agent](https://hermes-agent.nousresearch.com), stored as plain markdown files.

Each memory is one note in a folder you choose. Before every turn, Memory Stem recalls up to four relevant notes. The agent saves and corrects memories through tools; nothing is captured from the chat automatically.

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

A note tagged `event` with an `expires` date shows up once a day in the two weeks before it expires, even when nothing in the chat matches it.

Memory Stem regenerates `Index.md` (every current memory) and `About/<subject>.md` (one page per `about` subject, so Obsidian's graph links related notes). Don't edit them by hand.

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

Notes are the source of truth. The search index (SQLite plus local [fastembed](https://github.com/qdrant/fastembed) embeddings) is a cache and rebuilds from the files. Files that look like credentials are never indexed, and neither are vault pages with no prose (link indexes, Dataview dashboards, lists of IDs). Pasting only a code, token or URL recalls nothing.

## Development

Commands, layout and the rules for changes are in [AGENTS.md](AGENTS.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
