"""lom.agc.gov.my response decryption.

As of 2026-08 the Malaysian AGC portal wraps its DataTables JSON in AES-256-GCM instead of
serving it plainly: the endpoint answers `{"encrypted": true, "data": "<base64>"}`. This is a
transport wrapper, not an access control — the portal publishes the key in its own page
(`const SEARCH_RESPONSE_KEY = '<64 hex>'`) precisely so the browser can read it, and the
payload is the same public catalogue of Malaysian legislation either way. We do exactly what
the page's own `responseCrypto.js` does.

Payload layout (written by PHP's openssl_encrypt, read by responseCrypto.js):

    base64( [12-byte IV] [16-byte GCM tag] [ciphertext] )

Handles the plain form too, so a portal that flips back keeps working.
"""
from __future__ import annotations

import base64
import json
import re
from typing import Callable

_KEY_RE = re.compile(r"SEARCH_RESPONSE_KEY\s*=\s*['\"]([0-9a-fA-F]{64})['\"]")
_key_cache: dict[str, str] = {}          # referer URL → hex key


def response_key(client, referer_url: str, log: Callable[[str], None] = print) -> str | None:
    """Read the AES key the portal page hands its own JavaScript. Cached per page."""
    if referer_url in _key_cache:
        return _key_cache[referer_url]
    try:
        html = client.get(referer_url).text
    except Exception as e:  # noqa: BLE001
        log(f"[my-portal] key page fetch failed ({type(e).__name__})")
        return None
    m = _KEY_RE.search(html)
    if not m:
        log("[my-portal] no SEARCH_RESPONSE_KEY on the page — portal markup changed")
        return None
    _key_cache[referer_url] = m.group(1).lower()
    return _key_cache[referer_url]


def decrypt_payload(data_b64: str, key_hex: str) -> dict:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    blob = base64.b64decode(data_b64)
    if len(blob) < 28:
        raise ValueError("encrypted payload too short")
    iv, tag, ct = blob[:12], blob[12:28], blob[28:]
    plain = AESGCM(bytes.fromhex(key_hex)).decrypt(iv, ct + tag, None)
    return json.loads(plain)


def fetch_catalogue(client, catalogue_url: str, referer: str, length: int = 5000,
                    log: Callable[[str], None] = print) -> list[dict]:
    """POST the DataTables endpoint and return its `records`, decrypting when needed."""
    r = client.post(catalogue_url, data={"draw": "1", "start": "0", "length": str(length)},
                    headers={"X-Requested-With": "XMLHttpRequest", "Referer": referer})
    r.raise_for_status()
    payload = r.json()
    if payload.get("encrypted") and isinstance(payload.get("data"), str):
        key = response_key(client, referer, log)
        if not key:
            return []
        payload = decrypt_payload(payload["data"], key)
    return payload.get("records", [])
