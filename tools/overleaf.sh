#!/usr/bin/env bash
# Move paper/ between this repository and an Overleaf project, by hand.
#
#   tools/overleaf.sh push    paper/ -> Overleaf   (regenerates first)
#   tools/overleaf.sh pull    Overleaf -> paper/   (prose only; see below)
#
# Configure once, in your shell -- never in a file in this repository:
#
#   export OVERLEAF_PROJECT_ID=<the id in the project URL>
#   export OVERLEAF_TOKEN=olp_...        # Overleaf > Account > Git integration
#
# A token pasted into a tracked file is a token that has to be revoked.
set -euo pipefail

: "${OVERLEAF_PROJECT_ID:?set OVERLEAF_PROJECT_ID}"
: "${OVERLEAF_TOKEN:?set OVERLEAF_TOKEN}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REMOTE="https://git:${OVERLEAF_TOKEN}@git.overleaf.com/${OVERLEAF_PROJECT_ID}"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

case "${1:-}" in
push)
  # Regenerate before pushing. Overleaf cannot run the pipeline, so what it
  # receives is a snapshot -- and a stale snapshot is exactly the drift the
  # pipeline exists to prevent.
  "$ROOT/.venv-bench/bin/ledger" -m "$ROOT/project.yaml" figures
  "$ROOT/.venv-bench/bin/python" -m bench.case_studies
  if ! git -C "$ROOT" diff --quiet -- paper/generated paper/cases; then
    echo "paper/generated or paper/cases changed -- commit them before pushing," >&2
    echo "so the Overleaf project and this repository name the same state." >&2
    exit 1
  fi
  git clone --quiet --depth 1 "$REMOTE" "$WORK/overleaf"
  rsync -a --delete --exclude '.git' "$ROOT/paper/" "$WORK/overleaf/"
  cd "$WORK/overleaf"
  git add -A
  if git diff --cached --quiet; then
    echo "Overleaf is already up to date."
    exit 0
  fi
  git -c user.name=ledger -c user.email=ledger@localhost \
      commit -q -m "ledger: paper from $(git -C "$ROOT" rev-parse --short HEAD)"
  git push --quiet origin master
  echo "pushed paper/ to Overleaf project ${OVERLEAF_PROJECT_ID}"
  ;;
pull)
  # Prose only. Generated assets come back from `ledger figures`, never from an
  # editor -- if Overleaf has changed one, verify would fail here anyway, and
  # the honest fix is to re-run the stage rather than to accept the edit.
  git clone --quiet --depth 1 "$REMOTE" "$WORK/overleaf"
  rsync -a "$WORK/overleaf/paper.tex" "$ROOT/paper/paper.tex"
  echo "pulled paper.tex; generated/ and cases/ were left alone."
  echo "run: .venv-bench/bin/ledger paper   # verify re-checks every number"
  ;;
*)
  sed -n '2,12p' "$0" >&2
  exit 2
  ;;
esac
