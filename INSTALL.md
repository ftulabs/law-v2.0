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
start it yourself, from a checkout of this repository:

```bash
git clone https://github.com/ftulabs/law-v2.0 && cd law-v2.0
python3 -m venv .venv                       # Python 3.10-3.12
.venv/bin/pip install -r requirements.txt
cp .env.example .env                         # runs with no API key at all
.venv/bin/python -m uvicorn backend.main:app --port 8000
```

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

## What is not done yet

Stated plainly, because each one is visible the first time you install:

- **No code signing** on any platform, so every install shows a warning.
- **No bundled engine.** The app is a client and needs `uvicorn` running.
- **No auto-update.** Tauri supports it; it needs a signing key first.
- **No mobile distribution.**

## Building it yourself

See [apps/README.md](apps/README.md) for the toolchain, per-platform system
dependencies, and the architecture matrix.
