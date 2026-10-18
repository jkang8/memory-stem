#!/bin/sh
# Quality gate for a Memory Stem change. Run from a checkout (worktree) of the repo; exits non-zero on any failure.
#   scripts/gate.sh [baseline_ref]      baseline defaults to origin/main
# 1. unit tests  2. privacy guard, doc check, ruff and pyright  3. real-vault recall evals vs the baseline (local only: evals quote the owner's life).
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
BASE="${1:-origin/main}"
PY="$(ls -d "$HOME"/.hermes/tools/python-*/bin/python3 | head -1)"
UV="$(command -v uv || ls "$HOME"/.hermes/tools/uv-*/uv 2>/dev/null | head -1)"
# the vault path is personal: it comes from the environment, never from this repo
[ -n "${VAULT_DIR:-}" ] || { echo "GATE FAIL: export VAULT_DIR=<your notes folder> first (the recall evals run against it)"; exit 1; }
export VAULT_DIR MEMORY_STEM_DENYLIST="${MEMORY_STEM_DENYLIST:-$HOME/.hermes/memory-stem-dev/denylist.txt}"
run() { # $1 = dir containing a memory_stem package; rest = command
  d="$1"; shift
  (cd "$d" && PYTHONPATH="$d" "$UV" run -q --offline --no-project --python "$PY" --with fastembed --with numpy "$@" 2>&1 | grep -v onnxruntime)
}
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/new" "$WORK/old"
ln -s "$REPO" "$WORK/new/memory_stem"
git -C "$REPO" archive "$BASE" | tar -x -C "$WORK/old" --one-top-level=memory_stem 2>/dev/null \
  || { mkdir "$WORK/old/memory_stem" && git -C "$REPO" archive "$BASE" | tar -x -C "$WORK/old/memory_stem"; }

echo "== unit tests"
run "$WORK/new" python -W ignore -m unittest discover -s memory_stem/tests -t . 2>&1 | tail -3 | tee "$WORK/t"
grep -q "^OK" "$WORK/t" || { echo "GATE FAIL: tests"; exit 1; }

echo "== privacy guard"
"$PY" "$REPO/scripts/privacy_guard.py" "$REPO" || { echo "GATE FAIL: privacy"; exit 1; }

echo "== doc check"
"$PY" "$REPO/scripts/doc_check.py" "$REPO" || { echo "GATE FAIL: docs"; exit 1; }

echo "== lint and types"
(cd "$WORK/new" && "$UV" run -q --offline --no-project --python "$PY" --with-requirements memory_stem/requirements-dev.txt \
  sh -c 'ruff check memory_stem && pyright -p memory_stem') || { echo "GATE FAIL: lint/types"; exit 1; }

score() { # $1 dir, $2 flag -> prints "right total junk"
  run "$1" python -W ignore -c "
import json,sys
from memory_stem import evaluate as E
r = E.run_heldout() if '$2' == 'heldout' else E.run(verbose=False)
a,b = r['recall'].split('/'); j = r['junk_returned'].split('/')[0]
print(a, b, j)" | tail -1
}
for set in tuned heldout; do
  o="$(score "$WORK/old" $set)"; n="$(score "$WORK/new" $set)"
  echo "== eval $set: baseline [$o] candidate [$n] (right total junk)"
  set -- $o; or=$1; oj=$3; set -- $n; nr=$1; nj=$3
  [ "$nr" -ge "$or" ] && [ "$nj" -le "$oj" ] || { echo "GATE FAIL: $set recall/junk regressed"; exit 1; }
done
echo "GATE PASS"
