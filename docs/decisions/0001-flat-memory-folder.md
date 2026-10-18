# 0001: Memories are one flat folder

**Status:** accepted · **Date:** 2026-10-18

**Decision:** Every memory is a top-level `Memory/*.md` file with an `id`. Subfolders of `Memory/` are never read as memories.

**Why:**
- Reading only the top level is what keeps drafts (`_inbox/`), eval sets (`_evals/`) and generated pages (`About/`) out of recall, with no filter rules to maintain.
- The per-turn change check is one cheap glob (file count and newest mtime).

**Rejected:** topic subfolders, because tags and `about` group notes instead (`Index.md` by tag, `About/` by subject). A recursive read would recall drafts and eval files.

**Consequences:** Non-memory files in `Memory/` go in a subfolder or carry no `id`. Organizing memories means tags or `about`, not folders.
