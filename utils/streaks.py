"""
utils/streaks.py
Win/loss streak calculations and leaderboard builder.

Streak rules (corrected):
  - Misses are SKIPPED entirely — they do not reset or continue streaks
  - Only actual voted matches (correct or wrong) count toward streaks
  - max_loss_streak = highest number of consecutive losses across voted matches,
    with missed games simply skipped over
  - Leaderboard hero shows max_loss_streak (highest ever), not current
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
    """
    Processes point records sorted by match date ascending.
    Misses are ignored — streaks only count voted matches.
    """
    curr_win  = 0
    curr_loss = 0
    max_win   = 0
    max_loss  = 0

    for r in user_points:
        note = str(r.get("note", ""))
        pts  = float(r.get("total_points", 0))

        if _is_miss(note):
            continue          # skip — does not affect streaks at all

        if pts > 0:
            curr_win  += 1
            curr_loss  = 0
            max_win    = max(max_win, curr_win)
        else:
            curr_loss += 1
            curr_win   = 0
            max_loss   = max(max_loss, curr_loss)

    return {
        "current_win_streak" : curr_win,
        "current_loss_streak": curr_loss,
        "max_win_streak"     : max_win,
        "max_loss_streak"    : max_loss,
    }


def build_leaderboard(points: list[dict], matches: list[dict],
                       users: list[dict]) -> list[dict]:
    if not points or not users:
        return []

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
                   if not _is_miss(str(p.get("note", "")))]
        correct = [p for p in voted
                   if float(p.get("total_points", 0)) > 0]
        missed  = [p for p in pts_list
                   if _is_miss(str(p.get("note", "")))]

        total_pts = round(sum(float(p.get("total_points", 0))
                              for p in pts_list), 3)
        win_pct   = round(len(correct) / len(voted) * 100, 1) if voted else 0.0
        streaks   = calculate_streaks(sorted_pts)

        row = {
            "user_id"           : user_id,
            "name"              : nick,
            "total_points"      : total_pts,
            "win_pct"           : win_pct,
            "missed"            : len(missed),
            "curr_win_streak"   : streaks["current_win_streak"],
            "curr_loss_streak"  : streaks["current_loss_streak"],
            "max_win_streak"    : streaks["max_win_streak"],
            "max_loss_streak"   : streaks["max_loss_streak"],
        }

        pts_by_match = {p["match_id"]: p for p in pts_list}
        for mid in match_ids:
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
    if not rows:
        return {}

    top_win  = max(rows, key=lambda r: r["max_win_streak"])   # max ever consecutive wins
    top_loss = max(rows, key=lambda r: r["max_loss_streak"])  # max ever consecutive losses
    top_miss = max(rows, key=lambda r: r["missed"])

    return {
        "top_win_streak" : {
            "name" : top_win["name"],
            "value": top_win["max_win_streak"],
            "label": "Most consecutive wins (ever, misses ignored)",
        },
        "top_loss_streak": {
            "name" : top_loss["name"],
            "value": top_loss["max_loss_streak"],
            "label": "Most consecutive losses (ever, misses ignored)",
        },
        "top_missed"     : {
            "name" : top_miss["name"],
            "value": top_miss["missed"],
            "label": "Most missed votes",
        },
    }
