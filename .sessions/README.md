# Parallel Claude Code sessions — coordination protocol

Three sessions edit this repo at once. This directory makes that visible; **git branches** make
it safe. One file per session, so two sessions never write the same file and the directory
merges without conflicts.

## The rule that actually prevents damage

**One branch per session.** Uncommitted work in a shared working tree is the real hazard: a
`git checkout` or `git stash` in session B silently takes session A's uncommitted files with it.
That has already happened once here — 42 uncommitted files from the corpus/retrieval session
were left sitting on `main` while another session committed UI work to `main`.

    git checkout -b <area>/<what>     # before you start
    git add -A && git commit          # early and often, even WIP commits

## Before editing shared code

    python tools/session_claim.py list                       # who is doing what
    python tools/session_claim.py check --paths backend/pipeline/retrieval.py
    python tools/session_claim.py claim --id ui --branch feat/ui-globe \
        --paths frontend backend/auth --what "globe/map picker + account card"
    python tools/session_claim.py release --id ui            # when done

`claim` exits 2 and prints the conflict if another active claim overlaps. Claims are advisory:
they surface collisions, they do not lock. Overlap is sometimes fine — talk about it, do not
silently both edit.

## Files that are hot right now (touched by more than one area)

| file | why it is contested |
|---|---|
| `backend/config.py` | every area adds settings — keep edits to your own block, never reformat |
| `backend/schemas.py` | economies, output columns |
| `backend/pipeline/mapping.py` | retrieval reads it, scoring writes it |
| `CLAUDE.md` | everyone documents into it — append to your own section |

For those, prefer many small commits over one big one, and re-read the file immediately before
editing rather than relying on an earlier read.
