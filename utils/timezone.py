"""
utils/timezone.py
All timezone conversion and display helpers.
"""

import pytz
from datetime import datetime


COMMON_TIMEZONES = [
    "Asia/Kolkata",
    "Europe/London",
    "Europe/Paris",
    "Europe/Berlin",
    "America/New_York",
    "America/Chicago",
    "America/Los_Angeles",
    "Australia/Sydney",
    "Australia/Brisbane",
    "Asia/Dubai",
    "Asia/Singapore",
    "Asia/Tokyo",
    "Pacific/Auckland",
    "UTC",
]


def get_match_cutoff_utc(match: dict) -> datetime:
    """
    Convert match local start time to UTC-aware datetime.
    This is the single source of truth for vote deadline.
    """
    local_tz  = pytz.timezone(match["timezone"])
    local_dt  = datetime.strptime(
        f"{match['match_date']} {match['start_time']}", "%Y-%m-%d %H:%M"
    )
    aware     = local_tz.localize(local_dt)
    return aware.astimezone(pytz.utc)


def is_voting_open(match: dict) -> bool:
    cutoff_utc = get_match_cutoff_utc(match)
    now_utc    = datetime.now(pytz.utc)
    return now_utc < cutoff_utc


def time_until_cutoff(match: dict) -> tuple[int, int, int]:
    """
    Returns (hours, minutes, seconds) until vote deadline.
    Returns (0, 0, 0) if already past.
    """
    cutoff  = get_match_cutoff_utc(match)
    now     = datetime.now(pytz.utc)
    delta   = cutoff - now
    if delta.total_seconds() <= 0:
        return 0, 0, 0
    total   = int(delta.total_seconds())
    h       = total // 3600
    m       = (total % 3600) // 60
    s       = total % 60
    return h, m, s


def format_match_times(match: dict, user_timezone: str = None) -> dict:
    """
    Returns dict of formatted time strings for display.
    """
    local_tz  = pytz.timezone(match["timezone"])
    local_dt  = datetime.strptime(
        f"{match['match_date']} {match['start_time']}", "%Y-%m-%d %H:%M"
    )
    aware     = local_tz.localize(local_dt)
    utc_dt    = aware.astimezone(pytz.utc)

    result = {
        "local": aware.strftime("%d %b %Y  %H:%M  %Z"),
        "utc"  : utc_dt.strftime("%d %b %Y  %H:%M  UTC"),
        "user" : None,
        "tz"   : match["timezone"],
    }

    if user_timezone and user_timezone != match["timezone"]:
        try:
            user_tz   = pytz.timezone(user_timezone)
            user_dt   = aware.astimezone(user_tz)
            result["user"] = user_dt.strftime("%d %b %Y  %H:%M  %Z")
        except Exception:
            pass

    return result


def format_countdown(match: dict) -> tuple[str, str]:
    """
    Returns (message, severity) for countdown display.
    severity: 'success' | 'warning' | 'error'
    """
    h, m, s = time_until_cutoff(match)
    if h == 0 and m == 0 and s == 0:
        return "🔴 Voting Closed", "error"
    if h < 1:
        return f"⚠️ Closes in {m}m {s}s — hurry!", "warning"
    if h < 3:
        return f"🟡 Voting open — closes in {h}h {m}m", "warning"
    return f"🟢 Voting open — closes in {h}h {m}m", "success"


def parse_utc_iso(iso_str: str) -> datetime | None:
    """
    Parse an ISO datetime string to UTC-aware datetime.
    """
    if not iso_str:
        return None
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        return dt.astimezone(pytz.utc)
    except Exception:
        return None


def format_ts(iso_str: str, user_timezone: str = "UTC") -> str:
    """
    Format a stored UTC ISO timestamp for display in user's timezone.
    """
    dt = parse_utc_iso(iso_str)
    if not dt:
        return "—"
    try:
        tz = pytz.timezone(user_timezone)
        return dt.astimezone(tz).strftime("%d %b %Y  %H:%M  %Z")
    except Exception:
        return dt.strftime("%d %b %Y  %H:%M  UTC")
