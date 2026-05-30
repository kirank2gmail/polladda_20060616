"""
data/db.py — Local file-based data store.
All data lives in data/store/*.json

User fields:
  user_id, name, nickname, role, password_hash,
  must_change_password, timezone, created_at, created_by
"""

import json
import hashlib
import uuid
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).parent / "store"
DATA_DIR.mkdir(parents=True, exist_ok=True)


# ── Core ──────────────────────────────────────────────────────────────────────

def _path(t):        return DATA_DIR / f"{t}.json"
def _now():          return datetime.utcnow().isoformat()
def _uid():          return str(uuid.uuid4())[:8]
def _hash(pw: str):  return hashlib.sha256(pw.encode()).hexdigest()

def _read(table: str) -> list[dict]:
    p = _path(table)
    if not p.exists(): return []
    try:
        with open(p) as f: return json.load(f)
    except: return []

def _write(table: str, records: list[dict]):
    with open(_path(table), "w") as f:
        json.dump(records, f, indent=2, default=str)

def _insert(table: str, rec: dict):
    rows = _read(table); rows.append(rec); _write(table, rows)

def _update_where(table: str, match_fn, update_fn):
    rows = _read(table)
    for r in rows:
        if match_fn(r): update_fn(r)
    _write(table, rows)

def _delete_where(table: str, match_fn):
    _write(table, [r for r in _read(table) if not match_fn(r)])


# ── Users ─────────────────────────────────────────────────────────────────────

def get_all_users() -> list[dict]:
    return _read("users")

def get_user_by_id(user_id: str) -> dict | None:
    return next((u for u in _read("users") if u["user_id"] == user_id), None)

def get_user_by_name(name: str) -> dict | None:
    return next((u for u in _read("users")
                 if u["name"].lower() == name.lower()), None)

def get_display_name(user_id: str) -> str:
    """Return nickname if set and non-empty, else user_id."""
    u = get_user_by_id(user_id)
    if not u: return user_id
    nick = (u.get("nickname") or "").strip()
    return nick if nick else u["user_id"]

def create_user(name: str, password: str, role: str = "user",
                created_by: str = "admin") -> dict:
    uid  = _uid()
    user = {
        "user_id"             : uid,
        "name"                : name,
        "nickname"            : uid,          # default = user_id
        "role"                : role,
        "password_hash"       : _hash(password),
        "must_change_password": True,
        "timezone"            : "Asia/Kolkata",
        "created_by"          : created_by,
        "created_at"          : _now(),
    }
    _insert("users", user)
    return user

def admin_exists() -> bool:
    return any(u.get("role") == "admin" for u in _read("users"))

def verify_password(user_id: str, password: str) -> bool:
    u = get_user_by_id(user_id)
    return bool(u and u.get("password_hash") == _hash(password))

def change_password(user_id: str, new_password: str):
    _update_where("users",
        lambda r: r["user_id"] == user_id,
        lambda r: r.update({"password_hash": _hash(new_password),
                             "must_change_password": False}))

def update_nickname(user_id: str, nickname: str):
    _update_where("users",
        lambda r: r["user_id"] == user_id,
        lambda r: r.update({"nickname": nickname.strip()}))

def update_user_timezone(user_id: str, tz: str):
    _update_where("users",
        lambda r: r["user_id"] == user_id,
        lambda r: r.update({"timezone": tz}))

def set_user_role(user_id: str, role: str):
    _update_where("users",
        lambda r: r["user_id"] == user_id,
        lambda r: r.update({"role": role}))

def delete_user(user_id: str):
    _delete_where("users", lambda r: r["user_id"] == user_id)


# ── Tournaments ───────────────────────────────────────────────────────────────

def get_tournaments(status: str = None) -> list[dict]:
    ts = _read("tournaments")
    return [t for t in ts if t.get("status") == status] if status else ts

def get_tournament(tid: str) -> dict | None:
    return next((t for t in _read("tournaments") if t["tournament_id"] == tid), None)

def create_tournament(data: dict):
    _insert("tournaments", {
        "tournament_id" : data["tournament_id"],
        "name"          : data["name"],
        "sport"         : data["sport"],
        "start_date"    : data["start_date"],
        "status"        : "upcoming",
        "allowed_misses": int(data["allowed_misses"]),
        "penalty_points": float(data["penalty_points"]),
        "created_by"    : data.get("created_by", "admin"),
        "created_at"    : _now(),
    })

def update_tournament_status(tid: str, status: str):
    _update_where("tournaments",
        lambda r: r["tournament_id"] == tid,
        lambda r: r.update({"status": status}))


# ── Registrations ─────────────────────────────────────────────────────────────

def get_registrations(tid: str) -> list[dict]:
    return [r for r in _read("registrations") if r["tournament_id"] == tid]

def is_registered(user_id: str, tid: str) -> bool:
    return any(r["user_id"] == user_id and r["tournament_id"] == tid
               for r in _read("registrations"))

def register_user(user_id: str, tid: str):
    if not is_registered(user_id, tid):
        _insert("registrations", {
            "reg_id": _uid(), "user_id": user_id,
            "tournament_id": tid, "registered_at": _now()})


# ── Matches ───────────────────────────────────────────────────────────────────

def get_matches(tournament_id: str = None, status: str = None) -> list[dict]:
    ms = _read("matches")
    if tournament_id: ms = [m for m in ms if m["tournament_id"] == tournament_id]
    if status:        ms = [m for m in ms if m.get("status") == status]
    return ms

def get_match(match_id: str) -> dict | None:
    return next((m for m in _read("matches") if m["match_id"] == match_id), None)

def create_match(data: dict):
    _insert("matches", {
        "match_id"     : data["match_id"],
        "tournament_id": data["tournament_id"],
        "title"        : data["title"],
        "location"     : data["location"],
        "match_date"   : data["match_date"],
        "start_time"   : data["start_time"],
        "timezone"     : data["timezone"],
        "options"      : data["options"],
        "status"       : "upcoming",
        "result"       : "",
        "created_by"   : data.get("created_by", "admin"),
        "created_at"   : _now(),
    })

def bulk_create_matches(tid: str, rows: list[dict], created_by: str):
    for row in rows:
        row["tournament_id"] = tid
        row["created_by"]    = created_by
        create_match(row)

def update_match_result(match_id: str, result: str):
    _update_where("matches",
        lambda r: r["match_id"] == match_id,
        lambda r: r.update({"result": result, "status": "completed"}))

def delete_match(match_id: str):
    for table in ("matches", "votes", "points"):
        _delete_where(table, lambda r: r["match_id"] == match_id)


# ── Votes ─────────────────────────────────────────────────────────────────────

def get_votes(match_id: str = None, tournament_id: str = None) -> list[dict]:
    vs = _read("votes")
    if match_id:       vs = [v for v in vs if v["match_id"] == match_id]
    if tournament_id:  vs = [v for v in vs if v["tournament_id"] == tournament_id]
    return vs

def get_user_vote(user_id: str, match_id: str) -> dict | None:
    return next((v for v in _read("votes")
                 if v["user_id"] == user_id and v["match_id"] == match_id), None)

def cast_vote(user_id: str, match_id: str, tid: str, vote: str):
    _insert("votes", {
        "vote_id": _uid(), "user_id": user_id,
        "match_id": match_id, "tournament_id": tid,
        "vote": vote, "voted_at": _now(),
        "updated_at": "", "update_count": 0})

def update_vote(user_id: str, match_id: str, new_vote: str):
    _update_where("votes",
        lambda r: r["user_id"] == user_id and r["match_id"] == match_id,
        lambda r: r.update({
            "vote": new_vote, "updated_at": _now(),
            "update_count": int(r.get("update_count", 0)) + 1}))

def delete_vote(user_id: str, match_id: str):
    """Admin-only: delete a specific user's vote."""
    _delete_where("votes",
        lambda r: r["user_id"] == user_id and r["match_id"] == match_id)


# ── Points ────────────────────────────────────────────────────────────────────

def get_points(tournament_id: str = None, user_id: str = None) -> list[dict]:
    ps = _read("points")
    if tournament_id: ps = [p for p in ps if p["tournament_id"] == tournament_id]
    if user_id:       ps = [p for p in ps if p["user_id"] == user_id]
    return ps

def save_points_batch(records: list[dict]):
    existing = _read("points")
    now = _now()
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
