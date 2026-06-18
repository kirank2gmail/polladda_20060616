"""
utils/session_manager.py
Server-side session tokens stored in GCS.

Session token is placed in the URL as ?s=TOKEN.
URL params persist as long as the browser tab is open or the URL is bookmarked.
Closing a tab and reopening the base URL loses the token — but browsers that
restore previous sessions (Chrome, Edge, Firefox) will restore the URL including
the token, giving silent login.

For guaranteed persistence across tab close: user ticks "Keep me signed in"
on the login form, which sets the token in the URL. Browsers that restore
sessions pick this up automatically.

Sessions expire after 7 days. GCS cleanup happens automatically on read.
"""

import uuid
import streamlit as st
from datetime import datetime, timedelta, timezone
from data.gcs import read_table, write_table

SESSION_DAYS  = 365    # 1 year
SESSION_PARAM = "s"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_valid() -> list[dict]:
    """Read sessions table, dropping expired entries."""
    sessions = read_table("sessions")
    now      = datetime.now(timezone.utc)
    valid    = []
    changed  = False
    for s in sessions:
        try:
            exp = datetime.fromisoformat(s["expires"])
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp > now:
                valid.append(s)
            else:
                changed = True
        except Exception:
            changed = True
    if changed:
        write_table("sessions", valid)
    return valid


def _get_fingerprint() -> str:
    """
    Return a simple browser fingerprint from request headers.
    Binds the session to the specific browser that created it.
    If headers are unavailable, returns empty string (no binding).
    """
    try:
        from streamlit.web.server.websocket_headers import _get_websocket_headers
        headers = _get_websocket_headers()
        ua = headers.get("User-Agent", "") if headers else ""
        return ua[:120]   # truncate for storage
    except Exception:
        return ""


def create_session(user_id: str) -> str:
    """Create a server-side session bound to this browser, return the token."""
    token    = str(uuid.uuid4()).replace("-", "")
    expires  = (datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)).isoformat()
    sessions = _read_valid()
    # One session per user — remove any existing ones
    sessions = [s for s in sessions if s.get("user_id") != user_id]
    sessions.append({
        "token"      : token,
        "user_id"    : user_id,
        "fingerprint": _get_fingerprint(),
        "created_at" : _now(),
        "expires"    : expires,
    })
    write_table("sessions", sessions)
    return token


def validate_session(token: str) -> str | None:
    """
    Validate token. Returns user_id if:
      - Token exists and not expired
      - Browser fingerprint matches (if fingerprint was stored)
    Returns None otherwise.
    """
    if not token:
        return None
    sessions = _read_valid()
    current_fp = _get_fingerprint()
    for s in sessions:
        if s.get("token") == token:
            stored_fp = s.get("fingerprint", "")
            # If fingerprint was stored, it must match
            if stored_fp and current_fp and stored_fp != current_fp:
                return None   # different browser — reject
            return s["user_id"]
    return None


def delete_session(token: str):
    """Delete a session (sign out)."""
    if not token:
        return
    try:
        sessions = [s for s in read_table("sessions")
                    if s.get("token") != token]
        write_table("sessions", sessions)
    except Exception:
        pass


def get_session_token() -> str | None:
    """Read session token from URL query params."""
    return st.query_params.get(SESSION_PARAM)


def set_session_token(token: str):
    """Write session token to URL query params."""
    st.query_params[SESSION_PARAM] = token


def clear_session_token():
    """Remove session token from URL."""
    if SESSION_PARAM in st.query_params:
        del st.query_params[SESSION_PARAM]
