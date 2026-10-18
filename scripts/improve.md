# Memory Stem improver

You are running headless from `scripts/improve.sh`, in a fresh git worktree of Memory Stem (a public repo) on a new
branch cut from `origin/main`. Make **one** foundational improvement, prove it with a test and the gate, and commit
it. `improve.sh` checks your work, then opens the PR. A human reviews and merges it.

These come from the environment:
- `$IMPROVE_RUN` is a run folder outside the repo. Write your result there and nothing else outside the worktree.
- `$MS` runs a module against this worktree with the real vault: `$MS evaluate`, `$MS usage`, `$MS stale`,
  and `$MS test` runs the unit tests.
- `$IMPROVE_RUN/issues.json` holds the open GitHub issues labeled `improvement`, and `$IMPROVE_RUN/open_prs.json`
  the open PRs. Their changes are not in your worktree yet.
- `$IMPROVE_RUN/replay_log.jsonl` is a copy of the miss log: user wording that recall missed, paired with the note search found.

## Hard rules

1. **Never look at heldout data.** Don't read `heldout*.json` and don't run `evaluate --heldout` or `--ids` (`$MS`
   refuses them). The gate reports heldout as pass/fail counts, and that is all you may see. Never tune a threshold,
   wording or alias to move heldout. `tuned.json` misses may guide you.
2. **No personal data leaves this machine.** The evals, replay log, usage and notes quote the owner's life. Never put
   their text in code, tests, commit messages or the PR body. Describe them in counts and generic patterns, for
   example "4 of 19 tuned misses ask about a date range". Tests use made-up data and `tests/helpers.FakeEmbedder`.
3. **Don't touch the grader.** Leave `scripts/`, `.github/`, `CONTRIBUTING.md` and the eval files alone. A change
   that edits them is discarded.
4. No pushing, no PRs, no `gh`. Don't edit the live plugin (`~/.hermes/plugins/memory_stem`) or anything else
   outside this worktree except `$IMPROVE_RUN/result.json` and `$IMPROVE_RUN/pr_body.md`.

## Steps

1. **Gather signals.** Delegate to the `signals` subagent. It runs the commands and summarizes them, so you don't
   read raw logs yourself. Ask it for the tuned misses, replay-log patterns, usage, stale notes, issues and open PRs.
2. **Pick one change.** Choose the single highest-leverage foundational change: recall quality, correctness,
   robustness, test coverage or simplicity. Prefer a root-cause fix that will keep paying off over a patch for one
   case. An open `improvement` issue that fits beats one you invent. Never redo or overlap an open PR. If nothing clears the bar of "a reviewer would be
   glad to merge this", stop with status `nothing` and say why. That outcome is fine.
3. **Test first.** Write a test that fails without the change. Run it and confirm it fails for the right reason:
   `$MS test memory_stem.tests.<module>` (`$MS test` alone runs every unit test).
4. **Implement** the smallest change that makes it pass, matching the surrounding code's style and comment density.
5. **Run the gate:** `scripts/gate.sh` from the worktree root, saving its output to `$IMPROVE_RUN/gate_1.txt`. If it
   fails, read why, fix the same change, and run it once more (`gate_2.txt`). If it fails twice, stop with status
   `gate_failed`. Don't switch to a different change.
6. **Commit** with a message that says what changed and why. No personal data.
7. **Write `$IMPROVE_RUN/pr_body.md`** with sections `## Problem`, `## Change` and `## Risks`. `improve.sh` adds the
   gate output and the model used.

## Result

Always finish by writing `$IMPROVE_RUN/result.json`:

```json
{"status": "ready | nothing | gate_failed | gave_up",
 "title": "PR title (ready only)",
 "reason": "one or two sentences: what you did, or why there is no PR",
 "tests_run": true,
 "gate_runs": 1}
```

- `ready`: committed, the gate passed, and `pr_body.md` is written.
- `nothing`: nothing worth doing. No commit.
- `gate_failed`: the gate failed twice on the same change. Leave your commits in place so a retry can see them.
- `gave_up`: anything else that stopped you. Say what in `reason`.
