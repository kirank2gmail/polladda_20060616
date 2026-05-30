"""
utils/streaks.py — Win/loss streak calculations and leaderboard builder.
Uses get_display_name so nickname shows everywhere.
"""
from data.db import get_display_name


def calculate_streaks(user_points: list[dict]) -> dict:
    curr_win = curr_loss = max_win = max_loss = 0
    for r in user_points:
        note = str(r.get("note", ""))
        pts  = float(r.get("total_points", 0))
        if "miss" in note or "penalty" in note:
            curr_win = curr_loss = 0
            continue
        if pts > 0:
            curr_win  += 1; curr_loss  = 0
            max_win    = max(max_win, curr_win)
        else:
            curr_loss += 1; curr_win   = 0
            max_loss   = max(max_loss, curr_loss)
    return {"current_win_streak": curr_win, "current_loss_streak": curr_loss,
            "max_win_streak": max_win, "max_loss_streak": max_loss}


def build_leaderboard(points: list[dict], matches: list[dict],
                       users: list[dict]) -> list[dict]:
    if not points or not users: return []

    # Use nickname for display
    user_map  = {u["user_id"]: get_display_name(u["user_id"]) for u in users}
    match_ids = [m["match_id"] for m in matches]

    by_user: dict[str, list] = {}
    for p in points:
        by_user.setdefault(p["user_id"], []).append(p)

    rows = []
    for user_id, pts_list in by_user.items():
        nick = user_map.get(user_id, user_id)

        def _sort_key(p):
            m = next((x for x in matches if x["match_id"] == p["match_id"]), None)
            return (m["match_date"] + " " + m["start_time"]) if m else ""

        sorted_pts = sorted(pts_list, key=_sort_key)
        voted   = [p for p in pts_list
                   if "miss" not in p.get("note","") and "penalty" not in p.get("note","")]
        correct = [p for p in voted if float(p.get("total_points", 0)) > 0]
        missed  = [p for p in pts_list
                   if "miss" in p.get("note","") or "penalty" in p.get("note","")]

        total_pts = round(sum(float(p.get("total_points", 0)) for p in pts_list), 3)
        win_pct   = round(len(correct) / len(voted) * 100, 1) if voted else 0.0
        streaks   = calculate_streaks(sorted_pts)

        row = {
            "user_id": user_id, "name": nick,
            "total_points": total_pts, "win_pct": win_pct,
            "missed": len(missed),
            "curr_win_streak" : streaks["current_win_streak"],
            "curr_loss_streak": streaks["current_loss_streak"],
            "max_win_streak"  : streaks["max_win_streak"],
            "max_loss_streak" : streaks["max_loss_streak"],
        }

        pts_by_match = {p["match_id"]: p for p in pts_list}
        for mid in match_ids:
            p = pts_by_match.get(mid)
            if p is None:
                row[mid] = None
            else:
                note = str(p.get("note", ""))
                val  = float(p.get("total_points", 0))
                if "miss" in note:   row[mid] = "miss"
                elif "penalty" in note and val < 0: row[mid] = f"−{abs(val)}"
                elif val > 0:        row[mid] = val
                else:                row[mid] = 0.0
        rows.append(row)

    rows.sort(key=lambda r: r["total_points"], reverse=True)
    for i, r in enumerate(rows): r["rank"] = i + 1
    return rows


def leaderboard_heroes(rows: list[dict]) -> dict:
    if not rows: return {}
    return {
        "top_win_streak" : {"name": max(rows, key=lambda r: r["curr_win_streak"])["name"],
                             "value": max(rows, key=lambda r: r["curr_win_streak"])["curr_win_streak"]},
        "top_loss_streak": {"name": max(rows, key=lambda r: r["curr_loss_streak"])["name"],
                             "value": max(rows, key=lambda r: r["curr_loss_streak"])["curr_loss_streak"]},
        "top_missed"     : {"name": max(rows, key=lambda r: r["missed"])["name"],
                             "value": max(rows, key=lambda r: r["missed"])["missed"]},
    }
