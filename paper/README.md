# RDTII-Bench — paper

This directory is a complete LaTeX project. It compiles as-is on Overleaf with
its own directory as the project root, and it compiles locally through
`ledger paper`, which additionally refuses to build if any number in the source
has stopped tracing back to a run record.

```
paper.tex              the prose — the only file written by hand
references.bib         the bibliography
latexmkrc              search paths, so Overleaf finds style/ and cases/
style/iclr2027/        the conference author kit, unmodified
generated/             values, claims, tables and charts — DO NOT EDIT
cases/                 appendix case studies + rasterised native titles — DO NOT EDIT
```

## What must not be edited here

Everything under `generated/` and `cases/` is produced by `ledger figures` and
`python -m bench.case_studies` from the run records in `bench/out/runs/`.
`ledger verify` re-derives each one on the next build and fails if it has been
changed by hand — which is the check the whole pipeline exists for.

`paper.tex` is the half worth editing. Every number in it is a `\lnum{}` or
`\claim{}` macro that resolves at compile time, so the prose can be rewritten
freely without any risk of a number drifting from the experiment behind it.

## Overleaf

**Setting it up once.** In Overleaf: *New Project → Import from GitHub*, and
pick the repository. Overleaf will use the repository root, so either point it
at a repository whose root is this directory, or set the main document to
`paper/paper.tex` in *Menu → Settings*. `latexmkrc` handles the rest.

**Keeping it in sync.** Two mechanisms exist and they are not the same thing:

| | Direction | Automatic? |
|---|---|---|
| Overleaf **GitHub Sync** | both | **No.** Overleaf has no webhook; you press *Pull*/*Push* in the Overleaf UI. |
| Overleaf **Git integration** | you push to Overleaf | **Yes**, from CI — this is what `.github/workflows/overleaf.yml` uses. |

So the answer to "can it auto-sync" is: pushing *to* Overleaf can be automatic;
pulling *into* Overleaf cannot. The workflow in this repository therefore runs
one way, repository → Overleaf, on every push that touches `paper/`.

That direction is the right one anyway. Overleaf cannot run the pipeline, so
anything it holds is a snapshot; making the repository the source of truth means
the snapshot is never the thing a number is read from.

### Pick one writer

A project imported from GitHub stays linked to it, and this repository's CI
pushes over Overleaf's *Git integration*. Those are two different mechanisms
writing to one project. Nothing breaks while only one of them is used, but
Overleaf resolves a genuine collision by pushing a dated branch into the GitHub
repository, which is a mess to unpick.

So choose, and configure only that half:

| | Configure | How an update reaches Overleaf |
|---|---|---|
| **GitHub Sync** | `PAPER_REPO` + `PAPER_REPO_TOKEN` | CI updates `rdtii-bench-paper`; you press *Pull* in Overleaf |
| **Git integration** | `OVERLEAF_PROJECT_ID` + `OVERLEAF_TOKEN` | automatic, no clicks |

If you take Git integration — the automatic one — then **do not press Pull or
Push in Overleaf's GitHub menu.** Unlinking GitHub Sync on the project removes
the temptation entirely; the paper repository stays useful as a mirror and a
backup either way.

**Configure it** with a repository variable and a secret — never a file:

```
gh variable set OVERLEAF_PROJECT_ID --body <the id in your Overleaf project URL>
                                    # e.g. overleaf.com/project/<THIS PART>
gh secret   set OVERLEAF_TOKEN      # paste an olp_... token from
                                    # Overleaf > Account Settings > Git integration
```

The push is not forced. If someone has edited the project in Overleaf, the push
fails rather than overwriting their paragraph; recover it with
`tools/overleaf.sh pull`, then re-run.

**By hand**, without CI:

```bash
export OVERLEAF_PROJECT_ID=... OVERLEAF_TOKEN=olp_...
tools/overleaf.sh push      # regenerates, then pushes
tools/overleaf.sh pull      # brings paper.tex back; leaves generated/ alone
```

Overleaf's git remote has no branches and does not support Git LFS or symlinks,
so keep the project to plain files on `master`. Credentials are username `git`
and the token as the password.

**There is no Overleaf API for creating a project.** `overleaf.com/devs`
documents only *Open in Overleaf* (`overleaf.com/docs?snip_uri=…`), which is a
browser handoff that produces a new unlinked project. Creating the project is a
one-time manual step for anyone, with any tooling; everything after it is
scriptable.

## Building locally

```bash
.venv-bench/bin/ledger figures                  # regenerate assets from metrics
.venv-bench/bin/python -m bench.case_studies    # regenerate the appendix cases
.venv-bench/bin/ledger paper                    # verify, then compile
```

See [../INSTALL.md](../INSTALL.md) for the environment and the TeX requirements.
