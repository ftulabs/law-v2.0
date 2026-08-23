# Installing VeriTrade

Downloads: **[github.com/ftulabs/law-v2.0/releases/latest](https://github.com/ftulabs/law-v2.0/releases/latest)** ·
pick-it-for-me page: **[ftulabs.github.io/law-v2.0/download](https://ftulabs.github.io/law-v2.0/download.html)**

Every installer is built by CI from a tagged commit. Nothing is code-signed yet,
so each platform shows a warning the first time — what the warning says, and how
to get past it, is under each heading below.

---

## Which file do I want?

| You have | Download |
|---|---|
| Mac, Apple silicon (M1–M4) | `VeriTrade_<version>_aarch64.dmg` |
| Mac, Intel | `VeriTrade_<version>_x64.dmg` |
| Windows 10/11 | `VeriTrade_<version>_x64_en-US.msi` (or `_x64-setup.exe`) |
| Windows on ARM | `VeriTrade_<version>_arm64_en-US.msi` (or `_arm64-setup.exe`) |
| Ubuntu / Debian | `VeriTrade_<version>_amd64.deb` |
| Any other Linux | `VeriTrade_<version>_amd64.AppImage` |
| Fedora / RHEL | `VeriTrade-<version>-1.x86_64.rpm` |

On a Mac, ` > About This Mac` names the chip. Anything called "Apple M…" is
Apple silicon.

---

## macOS

```bash
open VeriTrade_0.1.0_aarch64.dmg      # then drag VeriTrade to Applications
```

The first launch is refused: **"VeriTrade is damaged and can't be opened."**
That message is misleading — the app is not damaged, it is unsigned, and macOS
quarantines anything downloaded without a Developer ID. Clear the quarantine
flag:

```bash
xattr -dr com.apple.quarantine /Applications/VeriTrade.app
```

Then open it normally. This stops being necessary once the app is signed and
notarised, which needs an Apple Developer account.

## Windows

Double-click the `.msi` — or the `-setup.exe`, which is the same app with an NSIS installer.  SmartScreen says **"Windows protected your PC"**;
choose *More info* → *Run anyway*. The installer is unsigned, so Windows cannot
name a publisher. An EV code-signing certificate removes this and takes a few
weeks of identity verification to obtain.

Windows on ARM will run the x64 build under emulation, but the `arm64` build is
faster — take it if you have it.

## Linux

**Debian and Ubuntu:**

```bash
sudo apt install ./VeriTrade_0.1.0_amd64.deb
```

`apt` resolves the WebKit dependency for you. On Ubuntu 22.04 and newer that
package is `libwebkit2gtk-4.1-0`; if you are on 20.04 the app will not install,
because Tauri v2 requires WebKitGTK 4.1 and 20.04 ships 4.0.

**Fedora, RHEL, openSUSE:**

```bash
sudo dnf install ./VeriTrade-0.1.0-1.x86_64.rpm
```

**Anything else — Arch, NixOS, or no package manager:**

```bash
chmod +x VeriTrade_0.1.0_amd64.AppImage
./VeriTrade_0.1.0_amd64.AppImage
```

The AppImage bundles its own libraries and needs no install. If it exits
immediately with a FUSE error, either install `fuse2` or extract it instead:

```bash
./VeriTrade_0.1.0_amd64.AppImage --appimage-extract && ./squashfs-root/AppRun
```

---

## The app needs an engine

The desktop app is a **client**. It reads and displays; the analysis itself runs
in the Python engine, and the app expects to find it at `http://127.0.0.1:8000`.

Bundling that engine into the installer is not done yet — see below — so for now
start it yourself, from a checkout of this repository. Python 3.10–3.12.

**Linux and macOS:**

```bash
git clone https://github.com/ftulabs/law-v2.0 && cd law-v2.0
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env                         # runs with no API key at all
.venv/bin/python -m uvicorn backend.main:app --port 8000
```

**Windows (PowerShell):**

```powershell
git clone https://github.com/ftulabs/law-v2.0; cd law-v2.0
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
Copy-Item .env.example .env
.venv\Scripts\python -m uvicorn backend.main:app --port 8000
```

A virtualenv puts its executables in `bin/` on Linux and macOS and in
`Scripts\` on Windows. Every command below follows that split; it is the only
difference between the platforms in this file.

Point the app somewhere else by setting `VERITRADE_API_BASE` before launching it.

With no key configured the engine uses a deterministic offline grader over the
bundled sample corpus, which is enough to see the whole flow. Real mapping needs
a key in `.env` — see the [README](README.md#quick-start).

## Mobile

There is no iOS or Android build to install. Both compile in CI, which is what
keeps them from breaking silently, but neither is signed: the App Store needs an
Apple Developer account and Play needs a Google Play console account, and
submission is a separate piece of work.

Mobile is designed to talk to a hosted API rather than a local engine — Python
cannot ship inside an App Store binary.

## Reproducing the benchmark, the paper and the site

Separate from the app, and much lighter: the RDTII-Bench results are produced by
[Ledger](https://github.com/ftulabs/ledger), which imports the entry points this
repo's `project.yaml` names. It needs neither an API key nor a network — every
input is a file checked into this repository — so the numbers in the paper can be
re-derived by anyone who clones it.

The environment is deliberately its own. Ledger has to run somewhere the tenant
is importable, so it is installed *beside* this repo's own dependencies rather
than into them. Three packages plus Ledger cover the benchmark; Pillow is needed
only by the case-study generator, which rasterises Chinese and Mongolian titles
that no stock TeX installation can typeset.

**Linux and macOS:**

```bash
python3 -m venv .venv-bench                  # Python 3.9+
.venv-bench/bin/pip install pydantic pydantic-settings PyYAML Pillow
.venv-bench/bin/pip install -e ../ledger    # Ledger has no public repo yet; see below

.venv-bench/bin/ledger run                   # 120 records, about 40 seconds
.venv-bench/bin/ledger metrics
.venv-bench/bin/ledger claims
.venv-bench/bin/ledger figures
.venv-bench/bin/ledger verify --explain      # every cited value, traced to records
```

**Windows (PowerShell):**

```powershell
py -3.12 -m venv .venv-bench
.venv-bench\Scripts\pip install pydantic pydantic-settings PyYAML Pillow
.venv-bench\Scripts\pip install -e ..\ledger   # Ledger has no public repo yet; see below

.venv-bench\Scripts\ledger run
.venv-bench\Scripts\ledger metrics
.venv-bench\Scripts\ledger claims
.venv-bench\Scripts\ledger figures
.venv-bench\Scripts\ledger verify --explain
```

Ledger is not published to PyPI and its repository is not public yet, so the
install above points at a sibling checkout — clone it next to this one. When the
repository lands, that line becomes an ordinary `pip install`.

`verify` is the point of the exercise. It walks `paper/paper.tex`, resolves every
`\lnum{}` and `\claim{}` back through `bench/out/metrics.json` to the records in
`bench/out/runs/`, and exits non-zero on anything it cannot ground.

### The PDF

`ledger paper` runs `verify` first and refuses to compile if any number in the
source is unbacked. It needs a TeX engine on `PATH` and the `pgfplots` package:

| Platform | Install |
|---|---|
| Ubuntu / Debian | `sudo apt install texlive-latex-recommended texlive-pictures texlive-fonts-recommended` |
| Fedora / RHEL | `sudo dnf install texlive-scheme-medium` |
| macOS | `brew install --cask basictex`, then `sudo tlmgr install pgfplots booktabs` |
| Windows | [MiKTeX](https://miktex.org/download) — it fetches missing packages on first compile |
| Any platform | [Tectonic](https://tectonic-typesetting.github.io/) — one binary, no TeX distribution, and the only option that makes the build byte-reproducible |

```bash
.venv-bench/bin/python -m bench.case_studies   # appendix case studies + glyph images
.venv-bench/bin/ledger paper                   # -> bench/out/paper.pdf
```

Tectonic is worth preferring where you have the choice. `pdflatex` and `xelatex`
write a random document identifier into the PDF trailer, so two builds from the
same records differ in those bytes; Tectonic's deterministic mode does not.

### The project site

```bash
.venv-bench/bin/ledger web                     # -> site/index.html
```

Generated from the same `metrics.json` the paper is compiled from, which is why
the two cannot disagree about a result.

The layout is the [Nerfies](https://github.com/nerfies/nerfies.github.io)
project-page template, vendored unmodified under `assets/nerfies/` and copied
into `site/theme/` at build time. **That template is CC BY-SA 4.0, and it is
share-alike**: the rendered site is a derivative and carries that licence, not
this repository's Apache-2.0. `ledger web` emits the required notice and the
link back in the page footer whenever a theme is configured, so the attribution
cannot be lost by forgetting it. See `assets/nerfies/LICENSE.md`.

Only the two stylesheets are vendored — not the analytics snippet, not the
icon-font JavaScript, not the carousel, and none of the Nerfies media. The one
network request the page makes is to Google Fonts, and it degrades to the system
stack without it.

Nothing is uploaded — open `site/index.html` directly, or serve the directory:

```bash
python3 -m http.server -d site 8080           # Windows: py -m http.server -d site 8080
```

## What is not done yet

Stated plainly, because each one is visible the first time you install:

- **No code signing** on any platform, so every install shows a warning.
- **No bundled engine.** The app is a client and needs `uvicorn` running.
- **No auto-update.** Tauri supports it; it needs a signing key first.
- **No mobile distribution.**

## Building it yourself

See [apps/README.md](apps/README.md) for the toolchain, per-platform system
dependencies, and the architecture matrix.
