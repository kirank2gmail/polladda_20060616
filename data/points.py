"""
data/points.py
Points calculation engine — uses local store.
"""

from data.db import (
    get_tournament, get_registrations, get_votes, get_matches,
    save_points_batch, delete_match_points
)


def _count_prior_misses(user_id: str, match_id: str,
                         tournament_id: str) -> int:
    """Count matches this user missed BEFORE this match in this tournament."""
    all_matches = get_matches(tournament_id=tournament_id, status="completed")
    all_votes   = get_votes(tournament_id=tournament_id)

    this_match  = next((m for m in all_matches if m["match_id"] == match_id), None)
    if not this_match:
        return 0

    this_dt = f"{this_match['match_date']} {this_match['start_time']}"
    voted_ids = {v["match_id"] for v in all_votes if v["user_id"] == user_id}

    missed = 0
    for m in all_matches:
        if m["match_id"] == match_id:
            continue
        m_dt = f"{m['match_date']} {m['start_time']}"
        if m_dt < this_dt and m["match_id"] not in voted_ids:
            missed += 1
    return missed


def calculate_match_points(match_id: str, tournament_id: str,
                            winning_option: str) -> list[dict]:
    tournament = get_tournament(tournament_id)
    if not tournament:
        raise ValueError(f"Tournament {tournament_id} not found")

    allowed_misses = int(tournament.get("allowed_misses", 3))
    penalty_pts    = float(tournament.get("penalty_points", 0.5))

    reg_list     = get_registrations(tournament_id)
    registered   = [r["user_id"] for r in reg_list]

    votes        = get_votes(match_id=match_id)
    voted_users  = {v["user_id"] for v in votes}
    missed_users = [u for u in registered if u not in voted_users]

    winner_votes = [v for v in votes if v["vote"] == winning_option]
    loser_votes  = [v for v in votes if v["vote"] != winning_option]
    n_winners    = len(winner_votes)
    n_losers     = len(loser_votes)

    # ── Penalty pool ──
    penalty_pool = 0.0
    results      = []

    for user_id in missed_users:
        prior = _count_prior_misses(user_id, match_id, tournament_id)
        if prior >= allowed_misses:
            penalty_pool += penalty_pts
            results.append({
                "user_id"       : user_id,
                "match_id"      : match_id,
                "tournament_id" : tournament_id,
                "base_points"   : 0,
                "penalty_points": -penalty_pts,
                "bonus_points"  : 0,
                "total_points"  : -penalty_pts,
                "note"          : f"penalty (-{penalty_pts})",
            })
        else:
            results.append({
                "user_id"       : user_id,
                "match_id"      : match_id,
                "tournament_id" : tournament_id,
                "base_points"   : 0,
                "penalty_points": 0,
                "bonus_points"  : 0,
                "total_points"  : 0,
                "note"          : f"free miss ({prior+1}/{allowed_misses})",
            })

    # ── Winner / loser points ──
    base_ratio    = round(n_losers / n_winners, 4) if n_winners > 0 else 1.0
    bonus_per_win = round(penalty_pool / n_winners, 4) if n_winners > 0 else 0.0
    total_pts     = round(base_ratio + bonus_per_win, 3)

    for v in winner_votes:
        results.append({
            "user_id"       : v["user_id"],
            "match_id"      : match_id,
            "tournament_id" : tournament_id,
            "base_points"   : base_ratio,
            "penalty_points": 0,
            "bonus_points"  : bonus_per_win,
            "total_points"  : total_pts,
            "note"          : f"correct (base={base_ratio} bonus={bonus_per_win})",
        })

    for v in loser_votes:
        results.append({
            "user_id"       : v["user_id"],
            "match_id"      : match_id,
            "tournament_id" : tournament_id,
            "base_points"   : 0,
            "penalty_points": 0,
            "bonus_points"  : 0,
            "total_points"  : 0,
            "note"          : "wrong",
        })

    return results


def run_points_calculation(match_id: str, tournament_id: str,
                            winning_option: str) -> list[dict]:
    """Full pipeline: delete old → recalculate → save."""
    delete_match_points(match_id)
    records = calculate_match_points(match_id, tournament_id, winning_option)
    if records:
        save_points_batch(records)
    return records
