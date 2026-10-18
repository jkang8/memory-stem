# 0002: Heldout evals are frozen

**Status:** accepted · **Date:** 2026-10-18

**Decision:** `heldout*.json` are never tuned against: no thresholds, wording, aliases or questions. `tuned.json` is the set to tune on.

**Why:**
- They were written before any scoring, so they are the only honest measure of recall on phrasing the system has not seen.
- Tuning on them turns the score into a training number, and regressions would go unseen.

**Rejected:** a single set for both tuning and reporting, because it overfits by construction.

**Consequences:** The gate uses heldout only as a no-regression count. Improvement work reads tuned misses. A case whose fact changed is retired automatically, not rewritten.
