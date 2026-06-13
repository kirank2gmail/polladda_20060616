"""
utils/streaks.py
Win/loss streak calculations and leaderboard builder.

Streak rules:
  - Misses SKIPPED — neither reset nor continue streaks
  - Only voted matches count
  - max_win/loss_streak = highest ever consecutive run

Heroes:
  - Multiple players with same high value → all names alphabetical comma-separated

build_leaderboard() now takes match_ids_desc explicitly
so the caller controls column order (latest first).
"""

from data.gcs import read_table


def get_display_name(user_id: str) -> str:
    users = read_table("users")
    u     = next((x for x in users if x["user_id"] == user_id), None)
    if not u: return user_id
    nick  = (u.get("nickname") or "").strip()
    return nick if nick else u["user_id"]


def _is_miss(note: str) -> bool:
    n = note.lower()
    return "miss" in n or "penalty" in n


def calculate_streaks(user_points: list[dict]) -> dict:
    curr_win = curr_loss = max_win = max_loss = 0
    for r in user_points:
        note = str(r.get("note", ""))
        pts  = float(r.get("total_points", 0))
        if _is_miss(note):
            continue
        if pts > 0:
            curr_win  += 1; curr_loss  = 0
            max_win    = max(max_win, curr_win)
        else:
            curr_loss += 1; curr_win   = 0
            max_loss   = max(max_loss, curr_loss)
    return {
        "current_win_streak" : curr_win,
        "current_loss_streak": curr_loss,
        "max_win_streak"     : max_win,
        "max_loss_streak"    : max_loss,
    }


def build_leaderboard(points: list[dict],
                       matches_asc: list[dict],
                       match_ids_desc: list[str],
                       users: list[dict]) -> list[dict]:
    """
    matches_asc    — completed matches sorted oldest first (for streak calc)
    match_ids_desc — match IDs in display order: latest first (for columns)
    """
    if not points or not users:
        return []

    user_map = {u["user_id"]: get_display_name(u["user_id"]) for u in users}

    by_user: dict[str, list] = {}
    for p in points:
        by_user.setdefault(p["user_id"], []).append(p)

    rows = []
    for user_id, pts_list in by_user.items():
        nick = user_map.get(user_id, user_id)

        def _sort_key(p):
            m = next((x for x in matches_asc if x["match_id"] == p["match_id"]), None)
            return (m["match_date"] + " " + m["start_time"]) if m else ""

        sorted_pts = sorted(pts_list, key=_sort_key)

        voted   = [p for p in pts_list
                   if not _is_miss(str(p.get("note", "")))]
        correct = [p for p in voted if float(p.get("total_points", 0)) > 0]
        missed  = [p for p in pts_list if _is_miss(str(p.get("note", "")))]

        total_pts = round(sum(float(p.get("total_points", 0))
                              for p in pts_list), 3)
        win_pct   = round(len(correct) / len(voted) * 100, 1) if voted else 0.0
        streaks   = calculate_streaks(sorted_pts)

        row = {
            "user_id"          : user_id,
            "name"             : nick,
            "total_points"     : total_pts,
            "win_pct"          : win_pct,
            "missed"           : len(missed),
            "curr_win_streak"  : streaks["current_win_streak"],
            "curr_loss_streak" : streaks["current_loss_streak"],
            "max_win_streak"   : streaks["max_win_streak"],
            "max_loss_streak"  : streaks["max_loss_streak"],
        }

        # Per-match columns using desc order (latest first)
        pts_by_match = {p["match_id"]: p for p in pts_list}
        for mid in match_ids_desc:
            p = pts_by_match.get(mid)
            if p is None:
                row[mid] = None
            else:
                note = str(p.get("note", ""))
                val  = float(p.get("total_points", 0))
                if _is_miss(note) and val < 0:  row[mid] = f"−{abs(val)}"
                elif _is_miss(note):             row[mid] = "miss"
                elif val > 0:                    row[mid] = val
                elif val < 0:                    row[mid] = val
                else:                            row[mid] = 0.0

        rows.append(row)

    rows.sort(key=lambda r: r["total_points"], reverse=True)
    for i, r in enumerate(rows):
        r["rank"] = i + 1

    return rows


def leaderboard_heroes(rows: list[dict]) -> dict:
    """
    Returns hero stats. All tied players shown alphabetically comma-separated.
    """
    if not rows:
        return {}

    def _names_at_peak(key: str) -> tuple[int, str]:
        peak  = max(r[key] for r in rows)
        names = sorted(r["name"] for r in rows if r[key] == peak)
        return peak, ", ".join(names)

    win_val,  win_names  = _names_at_peak("max_win_streak")
    loss_val, loss_names = _names_at_peak("max_loss_streak")
    miss_val, miss_names = _names_at_peak("missed")

    return {
        "top_win_streak" : {"names": win_names,  "value": win_val},
        "top_loss_streak": {"names": loss_names, "value": loss_val},
        "top_missed"     : {"names": miss_names, "value": miss_val},
    }
