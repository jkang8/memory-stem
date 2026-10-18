# Contributing

- **One change per PR.** A fix, a feature or a refactor, not several. Small PRs get reviewed; big ones get skimmed.
- **Tests first.** Add a test that fails without the change, then make it pass. Unit tests use `tests/helpers.FakeEmbedder`, never the real vault.
- **Run the gate** from your checkout and paste its full output in the PR:

  ```sh
  scripts/gate.sh            # baseline: origin/main
  ```

  It runs the unit tests, the privacy guard, and the local recall evals against the baseline. It fails if recall drops or junk rises.
- **No personal data.** This repo is public. Eval sets stay in the vault (`Memory/_evals/`), and terms to keep out live in a local denylist (`$MEMORY_STEM_DENYLIST`). Don't quote eval questions, replay logs or notes in code, commits or PRs.
- **Never tune against `heldout*.json`.** Those sets are frozen; `tuned.json` is the one to tune against.
- No direct pushes to `main`, no force-pushes. CI must be green and the maintainer merges.
