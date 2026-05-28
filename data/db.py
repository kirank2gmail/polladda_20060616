"""
data/store.py
Local file-based data store.
All data lives in /data/*.json files — one file per entity type.
No database, no auth, no external services required.

Files:
  data/users.json
  data/tournaments.json
  data/registrations.json
  data/matches.json
  data/votes.json
  data/points.json
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path

# ── Storage path ─────────────────────────────────────────────────────────────
DATA_DIR = Path(__file__).parent / "store"
DATA_DIR.mkdir(parents=True, exist_ok=True)

TABLES = ["users", "tournaments", "registrations", "matches", "votes", "points"]


# ── Core read/write ──────────────────────────────────────────────────────────

def _path(table: str) -> Path:
    return DATA_DIR / f"{table}.json"


def _read(table: str) -> list[dict]:
    p = _path(table)
    if not p.exists():
        return []
    try:
        with open(p, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _write(table: str, records: list[dict]):
    with open(_path(table), "w") as f:
        json.dump(records, f, indent=2, default=str)


def _insert(table: str, record: dict):
    records = _read(table)
    records.append(record)
    _write(table, records)


def _update_where(table: str, match_fn, update_fn):
    """Update all records where match_fn(record) is True."""
    records = _read(table)
    for r in records:
        if match_fn(r):
            update_fn(r)
    _write(table, records)


def _delete_where(table: str, match_fn):
    records = _read(table)
    records = [r for r in records if not match_fn(r)]
    _write(table, records)


def _now() -> str:
    return datetime.utcnow().isoformat()


def _uid() -> str:
    return str(uuid.uuid4())[:8]


# ── Users ────────────────────────────────────────────────────────────────────

def get_all_users() -> list[dict]:
    return _read("users")


def get_user_by_name(name: str) -> dict | None:
    for u in _read("users"):
        if u["name"].lower() == name.lower():
            return u
    return None


def get_user_by_id(user_id: str) -> dict | None:
    for u in _read("users"):
        if u["user_id"] == user_id:
            return u
    return None


def create_user(name: str, role: str = "user") -> dict:
    user = {
        "user_id"   : _uid(),
        "name"      : name,
        "role"      : role,
        "timezone"  : "Asia/Kolkata",
        "created_at": _now(),
    }
    _insert("users", user)
    return user


def get_or_create_user(name: str, role: str = "user") -> dict:
    u = get_user_by_name(name)
    if u:
        return u
    return create_user(name, role)


def update_user_timezone(user_id: str, tz: str):
    _update_where(
        "users",
        lambda r: r["user_id"] == user_id,
        lambda r: r.update({"timezone": tz})
    )


def set_user_role(user_id: str, role: str):
    _update_where(
        "users",
        lambda r: r["user_id"] == user_id,
        lambda r: r.update({"role": role})
    )


# ── Tournaments ──────────────────────────────────────────────────────────────

def get_tournaments(status: str = None) -> list[dict]:
    ts = _read("tournaments")
    if status:
        ts = [t for t in ts if t.get("status") == status]
    return ts


def get_tournament(tournament_id: str) -> dict | None:
    for t in _read("tournaments"):
        if t["tournament_id"] == tournament_id:
            return t
    return None


def create_tournament(data: dict):
    rec = {
        "tournament_id" : data["tournament_id"],
        "name"          : data["name"],
        "sport"         : data["sport"],
        "start_date"    : data["start_date"],
        "status"        : "upcoming",
        "allowed_misses": int(data["allowed_misses"]),
        "penalty_points": float(data["penalty_points"]),
        "created_by"    : data.get("created_by", "admin"),
        "created_at"    : _now(),
    }
    _insert("tournaments", rec)


def update_tournament_status(tournament_id: str, status: str):
    _update_where(
        "tournaments",
        lambda r: r["tournament_id"] == tournament_id,
        lambda r: r.update({"status": status})
    )


# ── Registrations ────────────────────────────────────────────────────────────

def get_registrations(tournament_id: str) -> list[dict]:
    return [r for r in _read("registrations")
            if r["tournament_id"] == tournament_id]


def is_registered(user_id: str, tournament_id: str) -> bool:
    return any(
        r["user_id"] == user_id and r["tournament_id"] == tournament_id
        for r in _read("registrations")
    )


def register_user(user_id: str, tournament_id: str):
    if not is_registered(user_id, tournament_id):
        _insert("registrations", {
            "reg_id"       : _uid(),
            "user_id"      : user_id,
            "tournament_id": tournament_id,
            "registered_at": _now(),
        })


# ── Matches ──────────────────────────────────────────────────────────────────

def get_matches(tournament_id: str = None, status: str = None) -> list[dict]:
    ms = _read("matches")
    if tournament_id:
        ms = [m for m in ms if m["tournament_id"] == tournament_id]
    if status:
        ms = [m for m in ms if m.get("status") == status]
    return ms


def get_match(match_id: str) -> dict | None:
    for m in _read("matches"):
        if m["match_id"] == match_id:
            return m
    return None


def create_match(data: dict):
    rec = {
        "match_id"      : data["match_id"],
        "tournament_id" : data["tournament_id"],
        "title"         : data["title"],
        "location"      : data["location"],
        "match_date"    : data["match_date"],
        "start_time"    : data["start_time"],
        "timezone"      : data["timezone"],
        "options"       : data["options"],   # pipe-separated string
        "status"        : "upcoming",
        "result"        : "",
        "created_by"    : data.get("created_by", "admin"),
        "created_at"    : _now(),
    }
    _insert("matches", rec)


def bulk_create_matches(tournament_id: str, rows: list[dict], created_by: str):
    for row in rows:
        row["tournament_id"] = tournament_id
        row["created_by"]    = created_by
        create_match(row)


def update_match_result(match_id: str, result: str):
    _update_where(
        "matches",
        lambda r: r["match_id"] == match_id,
        lambda r: r.update({"result": result, "status": "completed"})
    )


# ── Votes ────────────────────────────────────────────────────────────────────

def get_votes(match_id: str = None, tournament_id: str = None) -> list[dict]:
    vs = _read("votes")
    if match_id:
        vs = [v for v in vs if v["match_id"] == match_id]
    if tournament_id:
        vs = [v for v in vs if v["tournament_id"] == tournament_id]
    return vs


def get_user_vote(user_id: str, match_id: str) -> dict | None:
    for v in _read("votes"):
        if v["user_id"] == user_id and v["match_id"] == match_id:
            return v
    return None


def cast_vote(user_id: str, match_id: str, tournament_id: str, vote: str):
    _insert("votes", {
        "vote_id"      : _uid(),
        "user_id"      : user_id,
        "match_id"     : match_id,
        "tournament_id": tournament_id,
        "vote"         : vote,
        "voted_at"     : _now(),
        "updated_at"   : "",
        "update_count" : 0,
    })


def update_vote(user_id: str, match_id: str, new_vote: str):
    _update_where(
        "votes",
        lambda r: r["user_id"] == user_id and r["match_id"] == match_id,
        lambda r: r.update({
            "vote"        : new_vote,
            "updated_at"  : _now(),
            "update_count": int(r.get("update_count", 0)) + 1,
        })
    )


# ── Points ───────────────────────────────────────────────────────────────────

def get_points(tournament_id: str = None, user_id: str = None) -> list[dict]:
    ps = _read("points")
    if tournament_id:
        ps = [p for p in ps if p["tournament_id"] == tournament_id]
    if user_id:
        ps = [p for p in ps if p["user_id"] == user_id]
    return ps


def save_points_batch(records: list[dict]):
    existing = _read("points")
    now      = _now()
    for r in records:
        existing.append({
            "point_id"      : _uid(),
            "user_id"       : r["user_id"],
            "match_id"      : r["match_id"],
            "tournament_id" : r["tournament_id"],
            "base_points"   : r.get("base_points",    0),
            "penalty_points": r.get("penalty_points", 0),
            "bonus_points"  : r.get("bonus_points",   0),
            "total_points"  : r.get("total_points",   0),
            "note"          : r.get("note",           ""),
            "calculated_at" : now,
        })
    _write("points", existing)


def delete_match_points(match_id: str):
    _delete_where("points", lambda r: r["match_id"] == match_id)
