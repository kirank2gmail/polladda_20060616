"""
data/activity_log.py
Logs user login activity to GCS.
Records: user_id, timestamp, event type.
"""

from datetime import datetime, timezone
from data.gcs import read_table, write_table


def _now():
    return datetime.now(timezone.utc).isoformat()


def log_login(user_id: str):
    """Log a successful login event."""
    try:
        logs = read_table("activity_log")
        logs.append({
            "user_id"  : user_id,
            "event"    : "login",
            "logged_at": _now(),
        })
        # Keep last 1000 entries to avoid unbounded growth
        write_table("activity_log", logs[-1000:])
    except Exception:
        pass   # logging is non-fatal
