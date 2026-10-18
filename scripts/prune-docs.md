# Memory Stem doc pruner

You are running headless from `scripts/prune-docs.sh`, in a fresh git worktree of Memory Stem (a public repo).
Your only job is to make the docs shorter without losing anything a reader needs. `prune-docs.sh` commits your
edits, checks them and opens the PR. A human reviews and merges it.

## What to cut

Go through every `.md` file in the repo. For each line, ask: would a capable agent or new engineer, reading only the
code, get this wrong or waste time without it? If not, cut it. In particular, cut:
- anything the code, tests or CI already say or enforce, such as restated signatures, defaults or file listings;
- history and process: what was tried first, timelines, who decided;
- stale status, TODOs, roadmap and "we plan to";
- generic advice any engineer knows;
- a fact said twice: keep the better home and delete the other, or link to it;
- in `docs/decisions/`, a superseded ADR. Collapse it to its first line, `Superseded by NNNN`.

## Rules

1. **Deletion first.** You may rewrite a line only to merge duplicates or to keep a sentence grammatical after a cut.
   Never add new content. The PR must remove more lines than it adds, and it may add at most a quarter as many lines
   as it removes. Otherwise it is discarded.
2. **Keep the hard rules and traps**, even when they look redundant: no personal data, the repo is public, heldout
   evals are frozen, never merge or force-push, this folder is the live plugin. Also keep working commands and how
   to tell they worked.
3. **Edit only existing `.md` files.** Don't create, rename or delete files, and don't touch code, tests or `scripts/`.
4. Don't quote personal data. You won't find any in the docs; if you do, leave the line alone and say so in `reason`.

## Result

When you're done, write `$PRUNE_RUN/result.json`:

```json
{"status": "ready | nothing", "title": "PR title (ready only)", "reason": "one or two sentences"}
```

If you set status `ready`, also write `$PRUNE_RUN/pr_body.md` with `## Removed`, giving one bullet per cut (file, what,
and which test it failed), and `## Kept on purpose`, covering anything that looked cuttable but stays. The line
counts and the gate output are added for you. If nothing fails the test, write status `nothing` and change no files.
That outcome is fine.
