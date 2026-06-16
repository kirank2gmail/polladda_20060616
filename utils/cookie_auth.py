"""
utils/cookie_auth.py
Persistent login using browser localStorage via a custom Streamlit component.

localStorage persists across:
  - Tab close/reopen ✅
  - Browser close/reopen ✅
  - Chrome, Edge, Firefox, Safari, iOS Safari ✅

Does NOT persist across:
  - Different browsers on same device ✗
  - Incognito/Private mode (cleared on close) ✗
  - "Clear browsing data" ✗

HOW IT WORKS:
  A tiny invisible iframe component reads/writes localStorage.
  Streamlit's declare_component caches the return value across reruns,
  so after the component mounts once (~200ms), the value is available
  on every subsequent rerun including page reload.

  On first page load:
    Run 1 → component renders (value=None) → blank screen briefly
    Component mounts → sends localStorage value → triggers Run 2
    Run 2 → value available → restore session or show login
    Total delay: typically 100-300ms, invisible to user

Secrets required:
    [cookie]
    encryption_key = "any-long-random-string-at-least-32-chars"
"""

import os
import json
import hashlib
import base64
import streamlit as st
import streamlit.components.v1 as stc
from datetime import datetime, timedelta, timezone

SESSION_DAYS = 7
_COMPONENT_KEY = "sportspoll_sess"


# ── Encryption ────────────────────────────────────────────────────────────────

def _fernet():
    from cryptography.fernet import Fernet
    raw = st.secrets.get("cookie", {}).get("encryption_key", "changeme-32chars-padded-for-fernet")
    key = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
    return Fernet(key)

def _encrypt(data: str) -> str:
    return _fernet().encrypt(data.encode()).decode()

def _decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


# ── Component ─────────────────────────────────────────────────────────────────

def _component(cmd: str = "read", value: str = ""):
    """
    Invisible iframe that reads/writes localStorage.
    Streamlit caches the return value — available on every rerun.
    """
    _dir = os.path.join(os.path.dirname(__file__), "session_component")
    _comp = stc.declare_component("sportspoll_session", path=_dir)
    return _comp(cmd=cmd, value=value, default=None, key="__sess_comp__")


# ── Public API ────────────────────────────────────────────────────────────────

def init_auth() -> str | None:
    """
    Call once at the very top of app.py (before any other st.* calls).
    Returns user_id if a valid session exists in localStorage, else None.

    On fresh page load this returns None on the first run.
    The component triggers a rerun (~200ms) and returns the stored value.
    After that it's cached and instant on every rerun.
    """
    raw = _component(cmd="read", value="")

    if not raw:
        return None

    try:
        payload = json.loads(_decrypt(raw))
        expires = datetime.fromisoformat(payload["expires"])
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expires:
            clear_auth()
            return None
        return payload.get("user_id")
    except Exception:
        return None


def save_auth(user_id: str):
    """
    Write encrypted session to localStorage.
    Call immediately after successful login.
    """
    expires = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat()
    payload = json.dumps({"user_id": user_id, "expires": expires})
    token   = _encrypt(payload)
    _component(cmd="set", value=token)


def clear_auth():
    """Clear localStorage session on sign-out."""
    _component(cmd="clear", value="")
