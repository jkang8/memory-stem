#!/bin/sh
# Monthly doc pruning: one deletion-only PR that makes the docs shorter. Never merges or pushes main.
#   scripts/prune-docs.sh      (from any checkout; the edit is made in a fresh worktree of origin/main)
# Runs scripts/prune-docs.md headless with --model opus and only file tools. This script commits, refuses unless the
# diff touches only existing .md files and is net-negative, runs the gate and the privacy guard, then opens the PR.
# Prints one summary line. PRUNE_BASE and PRUNE_DRY_RUN=1 (no push, no PR) are for testing this script.
set -u
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
GH_REPO="${PRUNE_GH_REPO:-jkang8/memory-stem}"
LIMIT="${PRUNE_TIME_LIMIT:-1500}"  # seconds: well inside Hermes's 1-hour cron script timeout
BASE="${PRUNE_BASE:-origin/main}"
RUNS="${PRUNE_RUNS:-$HOME/.hermes/memory-stem-dev/prune-runs}"
WTS="$HOME/.hermes/memory-stem-dev/worktrees"  # not under plugins/: Hermes would load them
PY="$(ls -d "$HOME"/.hermes/tools/python-*/bin/python3 | head -1)"
export MEMORY_STEM_DENYLIST="${MEMORY_STEM_DENYLIST:-$HOME/.hermes/memory-stem-dev/denylist.txt}"
say() { echo "doc pruner: $*"; }
json() { "$PY" -c 'import json,sys
try: v = json.load(open(sys.argv[1])).get(sys.argv[2], "")
except Exception: v = ""
print(v)' "$1" "$2"; }

mkdir -p "$RUNS" "$WTS"
mkdir "$RUNS/.lock" 2>/dev/null || { say "another run is active, skipped"; exit 0; }
STAMP="$(date +%Y%m%d-%H%M%S)"; RUN="$RUNS/$STAMP"; BR="prune/$STAMP"; WT="$WTS/prune-$STAMP"
cleanup() {
  [ -d "$WT" ] && git -C "$REPO" worktree remove --force "$WT" 2>/dev/null
  git -C "$REPO" branch -D "$BR" >/dev/null 2>&1
  rmdir "$RUNS/.lock"
}
trap cleanup EXIT
trap 'exit 1' INT TERM
mkdir -p "$RUN"
ls -dt "$RUNS"/2* 2>/dev/null | tail -n +13 | while read -r old; do rm -rf "$old"; done  # keep the last 12 runs

open="$(gh pr list --repo "$GH_REPO" --state open --json headRefName --jq '[.[] | select(.headRefName | startswith("prune/"))] | length')" \
  || { say "can't list PRs (gh), skipped"; exit 1; }
[ "$open" = 0 ] || { say "a pruning PR is already open, skipped"; exit 0; }

git -C "$REPO" fetch -q origin || { say "fetch failed"; exit 1; }
git -C "$REPO" worktree add -q -b "$BR" "$WT" $BASE || { say "worktree failed"; exit 1; }
[ -f "$WT/scripts/prune-docs.md" ] && [ -f "$WT/scripts/doc_check.py" ] || { say "$BASE has no prune-docs.md or doc check yet"; exit 1; }

# file tools only, confined to the worktree and the run folder: this job never needs to run anything
(cd "$WT" && PRUNE_RUN="$RUN" perl -e 'alarm shift; exec @ARGV' "$LIMIT" \
  claude -p --model opus --output-format json --no-session-persistence --restricted --tools "Read,Edit,Write,Glob,Grep" \
    --permission-mode acceptEdits --add-dir "$RUN" < "$WT/scripts/prune-docs.md" > "$RUN/claude.json" 2> "$RUN/claude.err") 2>/dev/null
# (prompt on stdin: --add-dir takes several values and would swallow a prompt argument)
rc=$?
status="$(json "$RUN/result.json" status)"
[ "$rc" = 142 ] && { say "no PR: timed out after ${LIMIT}s [logs: $RUN]"; exit 1; }
[ "$status" = nothing ] && { say "no PR: $(json "$RUN/result.json" reason | head -c 300)"; exit 0; }
[ "$status" = ready ] || { say "no PR: run ended without a result (exit $rc) [logs: $RUN]"; exit 1; }

# check the edit ourselves: existing .md files only, net-negative, additions at most a quarter of deletions
git -C "$WT" add -A
bad="$(git -C "$WT" diff --cached --name-status $BASE | grep -vE '^M[[:space:]].*\.md$'; git -C "$WT" diff --cached --name-only $BASE | grep -E '^(scripts|\.github)/')"  # prompts are .md too
[ -z "$bad" ] || { say "no PR: touched more than existing .md files: $(echo $bad | head -c 200) [logs: $RUN]"; exit 1; }
set -- $(git -C "$WT" diff --cached --numstat $BASE | awk '{a+=$1; d+=$2} END {print a+0, d+0}'); added=$1; removed=$2
[ "$removed" -gt "$added" ] && [ $((added * 4)) -le "$removed" ] \
  || { say "no PR: +$added -$removed lines is not deletion-only enough [logs: $RUN]"; exit 1; }
title="$(json "$RUN/result.json" title)"; [ -n "$title" ] || title="Prune docs"
git -C "$WT" commit -q -m "$title" -m "Deletion-only doc pruning by scripts/prune-docs.sh: +$added -$removed lines." \
  || { say "commit failed [logs: $RUN]"; exit 1; }
(cd "$WT" && scripts/gate.sh $BASE) > "$RUN/gate.txt" 2>&1 || { say "no PR: the gate fails [logs: $RUN]"; exit 1; }

used="$("$PY" -c 'import json,sys; print(", ".join(json.load(open(sys.argv[1])).get("modelUsage", {})))' "$RUN/claude.json" 2>/dev/null)"
{
  cat "$RUN/pr_body.md" 2>/dev/null
  printf '\n## Size\n+%s -%s lines (net %s).\n\n## Gate\n```\n%s\n```\n\n## Produced by\n' "$added" "$removed" "$((added - removed))" "$(cat "$RUN/gate.txt")"
  echo "- \`claude -p --model opus\` (effort: default), file tools only. Models used: ${used:-unknown}"
  printf '\n🤖 Generated with [Claude Code](https://claude.com/claude-code) via scripts/prune-docs.sh\n'
} > "$RUN/pr_body_final.md"
printf '%s\n' "$title" > "$RUN/pr_title.txt"
"$PY" "$WT/scripts/privacy_guard.py" "$WT" --text "$RUN/pr_title.txt" "$RUN/pr_body_final.md" > "$RUN/privacy.txt" \
  || { say "no PR: the PR text failed the privacy guard [logs: $RUN]"; exit 1; }

[ "${PRUNE_DRY_RUN:-}" = 1 ] && { say "dry run, would open: $title (+$added -$removed) [body: $RUN/pr_body_final.md]"; exit 0; }
git -C "$WT" push -q -u origin "$BR" 2>"$RUN/push.err" || { say "push failed [logs: $RUN]"; exit 1; }
url="$(gh pr create --repo "$GH_REPO" --base main --head "$BR" --title "$title" --body-file "$RUN/pr_body_final.md")" \
  || { say "gh pr create failed [logs: $RUN]"; exit 1; }
say "opened $url"
