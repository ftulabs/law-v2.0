"""Accounts, passwords and sessions.

Two ways in, one account record:
  • email + password — hashed with bcrypt (never stored or logged in the clear)
  • Google sign-in   — Streamlit's native OIDC; we only persist the verified email/name

Sessions are opaque random tokens. Only the SHA-256 of a token is stored, so a
database leak cannot be replayed as a login; the raw token lives in the browser
(and in Streamlit's session state) and is compared by hash on every request.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from dataclasses import dataclass
from datetime import timedelta

import bcrypt
from sqlalchemy import delete, insert, select, update

from ..config import settings
from ..storage.db import utcnow
from ..storage.engine import get_engine, init_schema, user_sessions, users

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 8


@dataclass(frozen=True)
class User:
    user_id: str
    email: str
    name: str
    organisation: str | None = None
    auth_provider: str = "password"

    @property
    def display_name(self) -> str:
        return self.name or self.email.split("@")[0]

    @property
    def initials(self) -> str:
        parts = [p for p in (self.display_name or "?").split() if p]
        return ("".join(p[0] for p in parts[:2]) or "?").upper()


class AuthError(Exception):
    """Message is safe to show the user verbatim."""


# ── helpers ──────────────────────────────────────────────────────────────
def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


def validate_email(email: str) -> str:
    e = _norm_email(email)
    if not _EMAIL_RE.match(e):
        raise AuthError("That doesn't look like an email address.")
    return e


def validate_password(pw: str) -> str:
    if len(pw or "") < MIN_PASSWORD:
        raise AuthError(f"Password must be at least {MIN_PASSWORD} characters.")
    return pw


def _hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(pw: str, hashed: str | None) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def _row_to_user(row) -> User:
    m = row._mapping
    return User(user_id=m["user_id"], email=m["email"], name=m["name"] or "",
                organisation=m["organisation"], auth_provider=m["auth_provider"] or "password")


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ── accounts ─────────────────────────────────────────────────────────────
def get_user_by_email(email: str) -> User | None:
    with get_engine().connect() as c:
        row = c.execute(select(users).where(users.c.email == _norm_email(email))).fetchone()
    return _row_to_user(row) if row else None


def get_user(user_id: str) -> User | None:
    with get_engine().connect() as c:
        row = c.execute(select(users).where(users.c.user_id == user_id)).fetchone()
    return _row_to_user(row) if row else None


def sign_up(email: str, password: str, name: str = "", organisation: str = "") -> User:
    init_schema()
    email = validate_email(email)
    validate_password(password)
    if get_user_by_email(email):
        raise AuthError("An account with that email already exists. Try signing in.")
    user = User(user_id=f"usr-{uuid.uuid4().hex[:12]}", email=email, name=(name or "").strip(),
                organisation=(organisation or "").strip() or None, auth_provider="password")
    with get_engine().begin() as c:
        c.execute(insert(users).values(
            user_id=user.user_id, email=user.email, name=user.name,
            organisation=user.organisation, password_hash=_hash_password(password),
            auth_provider="password", created_at=utcnow(), last_login_at=utcnow(), is_active=1))
    return user


def sign_in(email: str, password: str) -> User:
    init_schema()
    email = _norm_email(email)
    with get_engine().connect() as c:
        row = c.execute(select(users).where(users.c.email == email)).fetchone()
    # Same message whether the email is unknown or the password is wrong — otherwise the
    # form doubles as an "is this person registered?" oracle.
    if not row or not _verify_password(password, row._mapping["password_hash"]):
        raise AuthError("Email or password is incorrect.")
    if not row._mapping["is_active"]:
        raise AuthError("This account has been deactivated.")
    with get_engine().begin() as c:
        c.execute(update(users).where(users.c.user_id == row._mapping["user_id"])
                  .values(last_login_at=utcnow()))
    return _row_to_user(row)


def sign_in_with_google(email: str, name: str = "") -> User:
    """Called after Streamlit's OIDC flow has verified the identity. Creates the account
    on first sign-in, otherwise just records the login."""
    init_schema()
    email = validate_email(email)
    existing = get_user_by_email(email)
    if existing:
        with get_engine().begin() as c:
            c.execute(update(users).where(users.c.user_id == existing.user_id)
                      .values(last_login_at=utcnow(), name=existing.name or (name or "").strip()))
        return existing
    user = User(user_id=f"usr-{uuid.uuid4().hex[:12]}", email=email,
                name=(name or "").strip(), auth_provider="google")
    with get_engine().begin() as c:
        c.execute(insert(users).values(
            user_id=user.user_id, email=user.email, name=user.name, organisation=None,
            password_hash=None, auth_provider="google", created_at=utcnow(),
            last_login_at=utcnow(), is_active=1))
    return user


def change_password(user_id: str, current: str, new: str) -> None:
    validate_password(new)
    with get_engine().connect() as c:
        row = c.execute(select(users).where(users.c.user_id == user_id)).fetchone()
    if not row:
        raise AuthError("Account not found.")
    stored = row._mapping["password_hash"]
    # Google-only accounts have no password yet — let them set one without a current password
    if stored and not _verify_password(current, stored):
        raise AuthError("Your current password is incorrect.")
    with get_engine().begin() as c:
        c.execute(update(users).where(users.c.user_id == user_id)
                  .values(password_hash=_hash_password(new)))


# ── sessions ─────────────────────────────────────────────────────────────
def create_session(user_id: str, days: int | None = None) -> str:
    init_schema()
    token = secrets.token_urlsafe(32)
    days = days or settings.session_days
    with get_engine().begin() as c:
        c.execute(insert(user_sessions).values(
            token_hash=_token_hash(token), user_id=user_id,
            created_at=utcnow(), expires_at=utcnow() + timedelta(days=days)))
    return token


def resolve_session(token: str) -> User | None:
    """Return the signed-in user for a token, or None if it is unknown/expired."""
    if not token:
        return None
    try:
        with get_engine().connect() as c:
            row = c.execute(select(user_sessions).where(
                user_sessions.c.token_hash == _token_hash(token))).fetchone()
    except Exception:
        return None
    if not row:
        return None
    expires = row._mapping["expires_at"]
    if expires is not None:
        exp = expires if expires.tzinfo else expires.replace(tzinfo=utcnow().tzinfo)
        if exp < utcnow():
            destroy_session(token)
            return None
    return get_user(row._mapping["user_id"])


def destroy_session(token: str) -> None:
    if not token:
        return
    try:
        with get_engine().begin() as c:
            c.execute(delete(user_sessions).where(user_sessions.c.token_hash == _token_hash(token)))
    except Exception:
        pass


def purge_expired_sessions() -> int:
    with get_engine().begin() as c:
        res = c.execute(delete(user_sessions).where(user_sessions.c.expires_at < utcnow()))
    return res.rowcount or 0
