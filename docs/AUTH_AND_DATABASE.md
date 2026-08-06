# Accounts & database

How sign-in and persistence work, and what changes when this moves to the cloud.

---

## 1. What a visitor sees

| State | Screen |
|---|---|
| Not signed in | **Landing page** — what VeriTrade does, the 3-step flow, links to the white paper and the GitHub repo, and the sign-in / create-account card. |
| Signed in | The tool itself, plus **Your past analyses** in the sidebar and an account menu (top-right) with sign-out. |

The landing page *is* the app's unauthenticated state (`frontend/auth_ui.require_user()`),
so no web-server routing changed — `veritrade.ftu.fyi` still points at the same Streamlit
process. `docs/landing.html` remains the standalone marketing page served at
`/app/static/landing.html`.

---

## 2. Sign-in methods

**Email + password** — always available. Passwords are hashed with **bcrypt**; the
plaintext is never stored or logged. Sign-in returns the same message for an unknown
email and a wrong password, so the form can't be used to discover who has an account.

**Google** — optional, and the button only appears when an OIDC provider is actually
configured, so it can never fail in front of a user. To enable it, add to
`.streamlit/secrets.toml`:

```toml
[auth]
redirect_uri = "https://veritrade.ftu.fyi/oauth2callback"
cookie_secret = "<a long random string>"

[auth.google]
client_id = "<google oauth client id>"
client_secret = "<google oauth client secret>"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

A Google sign-in for an email that already has a password account **links to that same
account** rather than creating a duplicate.

### Sessions
Sign-in issues an opaque random token. Only its **SHA-256** is stored in
`user_sessions`, so a database leak cannot be replayed as a login. The raw token lives
in a `vt_session` cookie (`SameSite=Lax`, `Secure` on HTTPS), which is what keeps you
signed in across a browser refresh. Lifetime: `SESSION_DAYS` (default 14).

---

## 3. Database

Everything goes through **SQLAlchemy** (`backend/storage/engine.py`), so the same code
runs on the local file today and on hosted Postgres later.

```bash
# now — local file (default, nothing to configure)
# DATABASE_URL unset  →  sqlite:///outputs/veritrade.db

# later — cloud Postgres (Neon / Supabase / RDS): one env var, no code change
DATABASE_URL=postgresql+psycopg://user:password@host/dbname
pip install "psycopg[binary]"
```

### Tables

| Table | Holds |
|---|---|
| `users` | account: email, name, organisation, bcrypt hash, provider, timestamps |
| `user_sessions` | SHA-256 of live session tokens + expiry |
| `runs` | one row per analysis — now carries **`user_id`** (NULL for pre-accounts runs) |
| `documents`, `provisions`, `mappings`, `review_log` | the existing audit trail, unchanged |

The five original tables keep their exact historical column layout, so an existing
`outputs/veritrade.db` keeps working — the upgrade only **adds** `users`,
`user_sessions` and a nullable `runs.user_id` (added automatically on first boot).

### Traceability
Every run is attributed to the account that launched it (`db.claim_run`), and history
reads are scoped by `user_id` — one researcher never sees another's runs. The CLI and
API call `db.list_runs()` with no user and still see everything, which is what an
operator/audit view needs.

---

## 4. Settings

| Env var | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | *(empty)* | Postgres URL; empty = local SQLite file |
| `AUTH_ENABLED` | `true` | `false` bypasses the gate (offline demos / screenshots) |
| `SESSION_DAYS` | `14` | How long a session cookie stays valid |
| `GOOGLE_AUTH_ENABLED` | `true` | Hides the Google button when `false` |

---

## 5. Design system note

`.streamlit/config.toml` is the source of truth for **native** Streamlit widgets and
`frontend/theme.py` for our own markup — both use the same hex values. Both
`[theme.light]` and `[theme.dark]` are defined, which is what stopped light mode from
inheriting dark chrome, and Inter/IBM Plex Mono are registered as theme fonts so widget
labels match our headings.

Light/dark has a visible toggle in the top-right (and on the landing page). It drives
**Streamlit's own** theme preference rather than a private flag: it writes
`localStorage["stActiveTheme-<pathname>-v2"]` (`"Light"` / `"Dark"` / `"System"`) and
reloads — the same thing Streamlit's ⋮ → Settings dialog does — so the native widgets
and our CSS switch together. The old toggle only repainted our own markup, which is why
light mode used to keep dark chrome.
