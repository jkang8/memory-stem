#!/bin/sh
# Weekly improver: one foundational change per run, as a PR a human reviews and merges. Never merges or pushes main.
#   scripts/improve.sh      (from any checkout; the change is made in a fresh worktree of origin/main)
# Runs scripts/improve.md headless with --model opus. If that attempt fails the gate twice on its change, retries
# once with --model fable; if it quit early or skipped tests, retries once with opus --effort high.
# Prints one summary line. Run logs stay outside the repo, in $IMPROVE_RUNS: they quote the owner's life.
set -u
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
GH_REPO="${IMPROVE_GH_REPO:-jkang8/memory-stem}"
LIMIT="${IMPROVE_TIME_LIMIT:-1500}"  # seconds per attempt: two attempts fit Hermes's 1-hour cron script timeout
BASE="${IMPROVE_BASE:-origin/main}"  # IMPROVE_BASE and IMPROVE_DRY_RUN=1 (no push, no PR) are for testing this script
RUNS="${IMPROVE_RUNS:-$HOME/.hermes/memory-stem-dev/improver-runs}"
WTS="${IMPROVE_WORKTREES:-$HOME/.hermes/memory-stem-dev/worktrees}"  # not under plugins/: Hermes would load them
PY="$(ls -d "$HOME"/.hermes/tools/python-*/bin/python3 | head -1)"
UV="$(command -v uv || ls "$HOME"/.hermes/tools/uv-*/uv 2>/dev/null | head -1)"
[ -n "${VAULT_DIR:-}" ] || VAULT_DIR="$(sed -n 's/^VAULT_DIR=//p' "$HOME/.hermes/.env" 2>/dev/null | tail -1 | tr -d "\"'")"
export VAULT_DIR MEMORY_STEM_DENYLIST="${MEMORY_STEM_DENYLIST:-$HOME/.hermes/memory-stem-dev/denylist.txt}"
say() { echo "improver: $*"; }
json() { "$PY" -c 'import json,sys
try: v = json.load(open(sys.argv[1])).get(sys.argv[2], "")
except Exception: v = ""
print(v)' "$1" "$2"; }

mkdir -p "$RUNS" "$WTS"
mkdir "$RUNS/.lock" 2>/dev/null || { say "another run is active, skipped"; exit 0; }
STAMP="$(date +%Y%m%d-%H%M%S)"; RUN="$RUNS/$STAMP"; BR="improve/$STAMP"; WT="$WTS/improve-$STAMP"
cleanup() {
  [ -d "$WT" ] && git -C "$REPO" worktree remove --force "$WT" 2>/dev/null
  git -C "$REPO" branch -D "$BR" >/dev/null 2>&1
  rmdir "$RUNS/.lock"
}
trap cleanup EXIT
trap 'exit 1' INT TERM
mkdir -p "$RUN/bin" "$RUN/pkg"

# one improver PR at a time
open="$(gh pr list --repo "$GH_REPO" --state open --json headRefName,labels \
  --jq '[.[] | select((.headRefName | startswith("improve/")) or any(.labels[]; .name == "improver"))] | length')" \
  || { say "can't list PRs (gh), skipped"; exit 1; }
[ "$open" = 0 ] || { say "an improver PR is already open, skipped"; exit 0; }
[ -n "$VAULT_DIR" ] || { say "VAULT_DIR not set, skipped"; exit 1; }

git -C "$REPO" fetch -q origin || { say "fetch failed"; exit 1; }
git -C "$REPO" worktree add -q -b "$BR" "$WT" $BASE || { say "worktree failed"; exit 1; }
[ -f "$WT/scripts/gate.sh" ] && [ -f "$WT/scripts/improve.md" ] || { say "$BASE has no gate or improve.md yet"; exit 1; }

# signals, copied in so the improver never needs gh or paths outside its folders
gh issue list --repo "$GH_REPO" --label improvement --state open --limit 20 --json number,title,body > "$RUN/issues.json" 2>/dev/null \
  || echo "[]" > "$RUN/issues.json"
gh pr list --repo "$GH_REPO" --state open --json number,title,body > "$RUN/open_prs.json" 2>/dev/null || echo "[]" > "$RUN/open_prs.json"
cp "$HOME/.hermes/vault_memory/replay_log.jsonl" "$RUN/" 2>/dev/null || : > "$RUN/replay_log.jsonl"
ls -dt "$RUNS"/2* 2>/dev/null | tail -n +13 | while read -r old; do rm -rf "$old"; done  # keep the last 12 runs

# $MS <module> [args] | $MS test [target]: this worktree's code against the real vault; heldout is refused
ln -s "$WT" "$RUN/pkg/memory_stem"
cat > "$RUN/bin/ms" <<EOF
#!/bin/sh
case " \$* " in *heldout*|*" --ids "*) echo "ms: heldout evals are off limits to the improver" >&2; exit 2;; esac
cd "$RUN/pkg" || exit 1
if [ "\${1:-}" = test ]; then shift; set -- unittest \${1:-discover -s memory_stem/tests -t .}; else m="\$1"; shift; set -- "memory_stem.\$m" "\$@"; fi
PYTHONPATH="$RUN/pkg" exec "$UV" run -q --offline --no-project --python "$PY" --with fastembed --with numpy python -W ignore -m "\$@"
EOF
chmod +x "$RUN/bin/ms"

# read-only signal gathering is a summarizing job: haiku
cat > "$RUN/agents.json" <<'EOF'
{"signals": {"model": "haiku", "tools": ["Bash", "Read", "Grep", "Glob"],
  "description": "Read-only. Runs the Memory Stem signal commands and summarizes them for choosing an improvement.",
  "prompt": "Gather and summarize Memory Stem signals. Change nothing. Run `$MS evaluate`, `$MS usage` and `$MS stale`; read $IMPROVE_RUN/replay_log.jsonl, $IMPROVE_RUN/issues.json and $IMPROVE_RUN/open_prs.json. Never run or read heldout evals. Report: (1) each tuned miss and junk hit with what came back instead, then the patterns across them; (2) replay log: entry count, which notes recur, recurring kinds of wording; (3) usage: never- or rarely-recalled notes and anything odd; (4) stale note count and kinds; (5) each open issue in one line; (6) each open PR in one line, saying what it already fixes. Your summary stays on this machine, but say which items are personal so the caller can describe them generically."}}
EOF

TOOLS="Bash,Read,Edit,Write,Glob,Grep,Agent"
DENY="Bash(git push*) Bash(gh *) Bash(*heldout*) Read(**/heldout*)"
attempt() { # $1 = attempt number, rest = model flags
  n=$1; shift
  A="$RUN/a$n"; mkdir -p "$A"; cp "$RUN/issues.json" "$RUN/open_prs.json" "$RUN/replay_log.jsonl" "$A/"
  [ -d "$RUN/previous" ] && cp -R "$RUN/previous" "$A/"
  prompt="$(cat "$WT/scripts/improve.md")"
  [ -f "$A/previous/retry.md" ] && prompt="$prompt

$(cat "$A/previous/retry.md")"
  echo "$*" > "$A/flags"
  (cd "$WT" && IMPROVE_RUN="$A" MS="$RUN/bin/ms" perl -e 'alarm shift; exec @ARGV' "$LIMIT" \
    claude -p --output-format json --no-session-persistence --restricted --tools "$TOOLS" \
      --permission-mode acceptEdits --allowedTools "$TOOLS" --disallowedTools "$DENY" \
      --add-dir "$A" --agents "$RUN/agents.json" "$@" "$prompt" > "$A/claude.json" 2> "$A/claude.err")
  echo $? > "$A/exit"
}

verdict() { # $1 = attempt number -> ready | nothing | gate_failed | quit_early: <why> | rejected: <why>
  A="$RUN/a$1"
  case "$(json "$A/result.json" status)" in
    nothing) echo nothing; return ;;
    gate_failed) [ -s "$A/gate_1.txt" ] && [ -s "$A/gate_2.txt" ] && { echo gate_failed; return; }
                 echo "quit_early: said the gate failed twice without two gate runs"; return ;;
    ready) ;;
    *) [ "$(cat "$A/exit")" = 142 ] && { echo "quit_early: timed out after ${LIMIT}s"; return; }
       echo "quit_early: $(json "$A/result.json" reason | head -c 300) (exit $(cat "$A/exit"))"; return ;;
  esac
  # don't take its word for it
  [ -z "$(git -C "$WT" status --porcelain)" ] || { echo "quit_early: uncommitted changes"; return; }
  changed="$(git -C "$WT" diff --name-only $BASE...HEAD)"
  [ -n "$changed" ] || { echo "quit_early: ready but no commit"; return; }
  echo "$changed" | grep -qE '^(scripts/|\.github/|CONTRIBUTING\.md)' && { echo "rejected: edited the gate or CI"; return; }
  echo "$changed" | grep -q '^tests/' || { echo "quit_early: no test added or changed"; return; }
  [ -s "$A/pr_body.md" ] && [ -n "$(json "$A/result.json" title)" ] || { echo "quit_early: no PR title or body"; return; }
  (cd "$WT" && scripts/gate.sh $BASE) > "$A/gate_check.txt" 2>&1 || { echo "quit_early: claimed ready but the gate fails"; return; }
  echo ready
}

reset_for_retry() { # keep what attempt $1 did as context for the next one, then start clean
  A="$RUN/a$1"; mkdir -p "$RUN/previous"
  git -C "$WT" add -A && git -C "$WT" diff --cached $BASE > "$RUN/previous/attempt.diff"
  cp "$A"/gate_*.txt "$A/result.json" "$RUN/previous/" 2>/dev/null
  git -C "$WT" reset -q --hard $BASE && git -C "$WT" clean -qfdx
  printf '%s\n' "## Previous attempt" "" "$2" "" \
    "Its diff is \`\$IMPROVE_RUN/previous/attempt.diff\`; its result and gate output are in \`\$IMPROVE_RUN/previous/\`." \
    "The worktree has been reset to $BASE. Build on what it learned; don't repeat its mistake." > "$RUN/previous/retry.md"
}

attempt 1 --model opus 2>/dev/null; v="$(verdict 1)"; n=1; why=""
case "$v" in
  gate_failed)
    why="opus failed the gate twice on the same change; retried with fable"
    reset_for_retry 1 "An attempt with opus failed the gate twice on the same change, with the gate output in hand. Diagnose why before changing anything; pick a different change only if this one can't pass."
    attempt 2 --model fable 2>/dev/null; v="$(verdict 2)"; n=2 ;;
  quit_early*)
    why="opus ${v#quit_early: }; retried with --effort high"
    reset_for_retry 1 "An attempt stopped short: ${v#quit_early: }. Do every step: a failing test first, the implementation, two gate runs at most, the result file."
    attempt 2 --model opus --effort high 2>/dev/null; v="$(verdict 2)"; n=2 ;;
esac
A="$RUN/a$n"
[ "$v" = ready ] || { say "no PR ($v) $(json "$A/result.json" reason | head -c 300) [logs: $RUN]"; exit 0; }

# the PR body, title and commit messages are public: guard them like the code
used="$("$PY" -c 'import json,sys; print(", ".join(json.load(open(sys.argv[1])).get("modelUsage", {})))' "$A/claude.json" 2>/dev/null)"
{
  cat "$A/pr_body.md"
  printf '\n## Gate\n```\n%s\n```\n\n## Produced by\n' "$(cat "$A/gate_check.txt")"
  echo "- \`claude -p $(cat "$A/flags")\` (effort: $(sed -n 's/.*--effort \([a-z]*\).*/\1/p' "$A/flags" | grep . || echo default)), attempt $n of 2${why:+: $why}"
  echo "- Models used: ${used:-unknown} (signal gathering by the haiku \`signals\` subagent)"
  printf '\n🤖 Generated with [Claude Code](https://claude.com/claude-code) via scripts/improve.sh\n'
} > "$RUN/pr_body_final.md"
json "$A/result.json" title > "$RUN/pr_title.txt"
git -C "$WT" log $BASE..HEAD --format=%B > "$RUN/commits.txt"
"$PY" "$WT/scripts/privacy_guard.py" "$WT" --text "$RUN/pr_title.txt" "$RUN/pr_body_final.md" "$RUN/commits.txt" > "$RUN/privacy.txt" \
  || { say "no PR: the PR text or commit messages failed the privacy guard [logs: $RUN]"; exit 1; }

[ "${IMPROVE_DRY_RUN:-}" = 1 ] && { say "dry run, would open: $(cat "$RUN/pr_title.txt") [body: $RUN/pr_body_final.md]"; exit 0; }
gh label create improver --repo "$GH_REPO" --color 5319e7 --description "Opened by scripts/improve.sh" >/dev/null 2>&1
git -C "$WT" push -q -u origin "$BR" 2>"$RUN/push.err" || { say "push failed [logs: $RUN]"; exit 1; }
url="$(gh pr create --repo "$GH_REPO" --base main --head "$BR" --label improver \
  --title "$(cat "$RUN/pr_title.txt")" --body-file "$RUN/pr_body_final.md")" || { say "gh pr create failed [logs: $RUN]"; exit 1; }
say "opened $url"
