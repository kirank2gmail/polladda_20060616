"""
data/points.py — Points calculation engine.

Exact rules:

  FREE MISS (within allowed_misses):
    pts = 0. Nothing goes anywhere.

  PENALISED MISS (beyond allowed_misses):
    pts = -penalty_pts (configurable, default 1.0)
    RATIO mode → goes to winner pool
    FIXED mode → goes to bank

  LOSER (voted wrong):
    pts = -1 always (both modes)
    RATIO mode → -1 goes to winner pool
    FIXED mode → -1 goes to bank

  WINNER:
    RATIO mode → pool (all loser pts + all penalised miss pts) / n_winners
    FIXED mode → fixed_odds (flat). Everything else goes to bank.
"""

from data.gcs import read_table, write_table


def _get_tournament(tid):
    return next((t for t in read_table("tournaments")
                 if t["tournament_id"] == tid), None)

def _get_match(mid):
    return next((m for m in read_table("matches")
                 if m["match_id"] == mid), None)

def _get_registrations(tid):
    return [r for r in read_table("registrations")
            if r["tournament_id"] == tid]

def _get_votes(match_id=None, tournament_id=None):
    vs = read_table("votes")
    if match_id:      vs = [v for v in vs if v["match_id"] == match_id]
    if tournament_id: vs = [v for v in vs if v["tournament_id"] == tournament_id]
    return vs

def _get_matches(tournament_id=None, status=None):
    ms = read_table("matches")
    if tournament_id: ms = [m for m in ms if m["tournament_id"] == tournament_id]
    if status:        ms = [m for m in ms if m.get("status") == status]
    return ms

def _uid():
    import uuid; return str(uuid.uuid4())[:8]

def _now():
    from datetime import datetime; return datetime.utcnow().isoformat()


def _count_prior_misses(user_id: str, match_id: str,
                         tournament_id: str) -> int:
    all_matches = _get_matches(tournament_id=tournament_id, status="completed")
    all_votes   = _get_votes(tournament_id=tournament_id)
    this_match  = next((m for m in all_matches
                        if m["match_id"] == match_id), None)
    if not this_match:
        return 0
    this_dt   = f"{this_match['match_date']} {this_match['start_time']}"
    voted_ids = {v["match_id"] for v in all_votes if v["user_id"] == user_id}
    return sum(
        1 for m in all_matches
        if m["match_id"] != match_id
        and f"{m['match_date']} {m['start_time']}" < this_dt
        and m["match_id"] not in voted_ids
    )


def calculate_match_points(match_id: str, tournament_id: str,
                            winning_option: str) -> list[dict]:
    tournament = _get_tournament(tournament_id)
    if not tournament:
        raise ValueError(f"Tournament {tournament_id} not found")

    match          = _get_match(match_id) or {}
    scoring_mode   = match.get("scoring_mode", "ratio")
    fixed_odds     = float(match.get("fixed_odds", 1.0))
    allowed_misses = int(tournament.get("allowed_misses", 3))
    penalty_pts    = float(tournament.get("penalty_points", 1.0))

    registered   = [r["user_id"] for r in _get_registrations(tournament_id)]
    votes        = _get_votes(match_id=match_id)
    voted_users  = {v["user_id"] for v in votes}
    missed_users = [u for u in registered if u not in voted_users]

    winner_votes = [v for v in votes if v["vote"] == winning_option]
    loser_votes  = [v for v in votes if v["vote"] != winning_option]
    n_winners    = len(winner_votes)

    results    = []
    ratio_pool = 0.0   # accumulates only in ratio mode

    # ── Missed voters ─────────────────────────────────────────────────────────
    for user_id in missed_users:
        prior = _count_prior_misses(user_id, match_id, tournament_id)
        if prior >= allowed_misses:
            dest = "winner pool" if scoring_mode == "ratio" else "bank"
            if scoring_mode == "ratio":
                ratio_pool += penalty_pts
            results.append({
                "user_id": user_id, "match_id": match_id,
                "tournament_id": tournament_id,
                "base_points": 0, "penalty_points": -penalty_pts,
                "bonus_points": 0, "total_points": -penalty_pts,
                "note": f"penalty (-{penalty_pts} → {dest})",
            })
        else:
            results.append({
                "user_id": user_id, "match_id": match_id,
                "tournament_id": tournament_id,
                "base_points": 0, "penalty_points": 0,
                "bonus_points": 0, "total_points": 0,
                "note": f"free miss ({prior+1}/{allowed_misses})",
            })

    # ── Losers — always -1 ────────────────────────────────────────────────────
    for v in loser_votes:
        dest = "winner pool" if scoring_mode == "ratio" else "bank"
        if scoring_mode == "ratio":
            ratio_pool += 1.0
        results.append({
            "user_id": v["user_id"], "match_id": match_id,
            "tournament_id": tournament_id,
            "base_points": -1, "penalty_points": 0,
            "bonus_points": 0, "total_points": -1,
            "note": f"wrong (-1 → {dest})",
        })

    # ── Winners ───────────────────────────────────────────────────────────────
    if scoring_mode == "fixed":
        total_win = fixed_odds
        note_win  = f"correct fixed=+{fixed_odds}"
    else:
        per_winner = round(ratio_pool / n_winners, 4) if n_winners > 0 else 1.0
        total_win  = per_winner
        note_win   = (f"correct ratio "
                      f"(pool={round(ratio_pool,3)} ÷ {n_winners} winners = +{per_winner})")

    for v in winner_votes:
        results.append({
            "user_id": v["user_id"], "match_id": match_id,
            "tournament_id": tournament_id,
            "base_points": total_win, "penalty_points": 0,
            "bonus_points": 0, "total_points": total_win,
            "note": note_win,
        })

    return results


def delete_match_points(match_id: str):
    existing = read_table("points")
    write_table("points", [p for p in existing if p["match_id"] != match_id])


def save_points_batch(records: list[dict]):
    existing = read_table("points")
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
    write_table("points", existing)


def run_points_calculation(match_id: str, tournament_id: str,
                            winning_option: str) -> list[dict]:
    delete_match_points(match_id)
    records = calculate_match_points(match_id, tournament_id, winning_option)
    if records:
        save_points_batch(records)
    return records
