# VeriTrade clients

One UI, five platforms. `apps/web` is the interface; `apps/shell` is the Tauri
wrapper that ships it as a desktop or mobile app. They differ only in how the UI
reaches the API, which is decided in one file — `apps/web/src/platform.ts`.

```
apps/web            the UI, and the only place product behaviour lives
  src/generated/    the typed client, produced by `ledger product` from the
                    backend's own Pydantic models — do not hand-edit
apps/shell          the Tauri v2 shell: macOS, Windows, Linux, iOS, Android
```

## Running it

The API first, in the repo root:

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m uvicorn backend.main:app --port 8000
```

Then the UI:

```bash
cd apps/web
npm ci
npm run dev            # http://localhost:5173
```

`npm run build` typechecks and bundles to `dist/`. `VITE_API_BASE` overrides the
API address at build time; without it a dev build talks to `127.0.0.1:8000` and a
served build talks to its own origin.

## The desktop app

```bash
cd apps/shell
npm ci
npx tauri dev          # builds the UI and opens the shell
npx tauri build        # installers in src-tauri/target/<target>/release/bundle
```

**Linux needs system libraries** that are not installable from npm or cargo.
On Ubuntu 22.04:

```bash
sudo apt-get install -y libwebkit2gtk-4.1-dev libappindicator3-dev \
                        librsvg2-dev patchelf build-essential curl wget file
```

Ubuntu 24.04 ships the same WebKit package name. On 20.04 it is
`libwebkit2gtk-4.0-dev`, and Tauri v2 requires 4.1, so 22.04 or newer is the
practical floor.

Rust comes from [rustup](https://rustup.rs); Node 20 or newer.

### Architectures

Desktop is built per architecture, not universal:

| Platform | Targets |
|---|---|
| macOS | `aarch64-apple-darwin` (Apple silicon), `x86_64-apple-darwin` (Intel) |
| Linux | `x86_64-unknown-linux-gnu` |
| Windows | `x86_64-pc-windows-msvc`, `aarch64-pc-windows-msvc` |

A macOS universal binary is possible today and is deliberately not used: the
moment the Python engine ships as a bundled sidecar, that sidecar is
per-architecture and a universal bundle cannot contain both. Building separately
now avoids a rebuild of the release pipeline later.

Add a target before building for it:

```bash
rustup target add aarch64-apple-darwin
npx tauri build --target aarch64-apple-darwin
```

## Mobile

```bash
npx tauri ios init         # needs full Xcode, not Command Line Tools
npx tauri android init     # needs Android Studio + NDK
```

Both compile in CI but are **not signed there**: submission needs certificates
the workflow deliberately does not carry. What CI proves is that the Rust core
and the UI still build for the platform, which is the part that breaks silently.

Mobile talks to a hosted API and never to a sidecar. Python cannot ship inside an
App Store binary, so the bundled-engine design applies to desktop only.

## The generated client

`src/generated/` is written by `ledger product` from `project.yaml`, which names
the backend's real types. Regenerate after changing a Pydantic model:

```bash
cd apps/web && npm run codegen
```

It is committed so a checkout without the pipeline still typechecks. A field
renamed in Python then breaks the TypeScript build rather than a user's screen.
