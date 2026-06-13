"""
pages/leaderboard.py
Leaderboard — sorted by Points by default.
Match columns in reverse chronological order (latest first, next to Missed).
"""

import streamlit as st
import pandas as pd
from data.db import get_matches, get_points, get_tournaments, get_all_users
from utils.streaks import build_leaderboard, leaderboard_heroes


def show_leaderboard(user: dict):
    tournaments = get_tournaments()
    if not tournaments:
        st.info("No tournaments yet.")
        return

    t_names = [t["name"] for t in tournaments]
    t_ids   = [t["tournament_id"] for t in tournaments]
    pre_tid = st.session_state.get("tournament_id", t_ids[0])
    pre_idx = t_ids.index(pre_tid) if pre_tid in t_ids else 0

    sel_name = st.selectbox("🏆 Tournament", t_names, index=pre_idx)
    sel_tid  = t_ids[t_names.index(sel_name)]

    points  = get_points(tournament_id=sel_tid)
    matches = get_matches(tournament_id=sel_tid, status="completed")
    users   = get_all_users()

    if not points:
        st.info("No results recorded yet for this tournament.")
        return

    # Sort matches ascending by date for streak calculation
    matches_asc = sorted(matches,
                         key=lambda m: m["match_date"] + " " + m["start_time"])

    # Match IDs in DESCENDING order — latest first for columns
    match_ids_desc = [m["match_id"] for m in reversed(matches_asc)]

    lb = build_leaderboard(points, matches_asc, match_ids_desc, users)
    if not lb:
        st.info("Leaderboard not available yet.")
        return

    # ── Hero stats ────────────────────────────────────────────────────────────
    heroes = leaderboard_heroes(lb)
    if heroes:
        st.markdown("### 🎖️ Highlights")
        h1, h2, h3 = st.columns(3)
        with h1:
            with st.container(border=True):
                st.markdown("🔥 **Longest Win Streak**")
                hw = heroes["top_win_streak"]
                st.markdown(f"**{hw['names']}**")
                st.caption(f"{hw['value']} consecutive wins (misses ignored)")
        with h2:
            with st.container(border=True):
                st.markdown("💀 **Longest Loss Streak**")
                hl = heroes["top_loss_streak"]
                st.markdown(f"**{hl['names']}**")
                st.caption(f"{hl['value']} consecutive losses (misses ignored)")
        with h3:
            with st.container(border=True):
                st.markdown("⚠️ **Most Missed Votes**")
                hm = heroes["top_missed"]
                st.markdown(f"**{hm['names']}**")
                st.caption(f"{hm['value']} missed")

    st.markdown("---")
    st.markdown("### 📊 Leaderboard")
    st.caption("Sorted by total points. Match columns show latest match first.")

    # Fixed columns + match columns in desc order
    fixed_cols = ["rank", "name", "total_points", "win_pct", "missed"]
    all_cols   = fixed_cols + match_ids_desc

    # Build DataFrame
    df = pd.DataFrame(lb)
    # Keep only columns that exist
    df = df[[c for c in all_cols if c in df.columns]]
    df = df.sort_values("total_points", ascending=False, na_position="last")

    # Rename fixed columns
    df = df.rename(columns={
        "rank"        : "Rank",
        "name"        : "Player",
        "total_points": "Points",
        "win_pct"     : "Win %",
        "missed"      : "Missed",
    })

    # Rename match columns to short titles (latest first)
    rename_map = {}
    for mid in match_ids_desc:
        m     = next((x for x in matches_asc if x["match_id"] == mid), None)
        short = m["title"][:14] if m else mid
        rename_map[mid] = short
    df = df.rename(columns=rename_map)

    short_titles = list(rename_map.values())

    # Format match point cells
    for col in short_titles:
        if col in df.columns:
            df[col] = df[col].apply(_fmt_cell)

    # Rebuild rank after sort
    df["Rank"] = range(1, len(df) + 1)
    cols_order = ["Rank", "Player", "Points", "Win %", "Missed"] + short_titles
    df = df[[c for c in cols_order if c in df.columns]]

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config=_col_config(short_titles),
    )

    # ── Match quick links ─────────────────────────────────────────────────────
    if match_ids_desc:
        st.markdown("#### Match Details")
        cols = st.columns(min(len(match_ids_desc), 6))
        for i, mid in enumerate(match_ids_desc):
            m = next((x for x in matches_asc if x["match_id"] == mid), None)
            label = m["title"] if m else mid
            with cols[i % 6]:
                if st.button(label, key=f"lb_{mid}"):
                    st.session_state["page"]               = "match"
                    st.session_state["match_id"]           = mid
                    st.session_state["match_list"]         = \
                        [x["match_id"] for x in matches_asc]
                    st.session_state["match_tournament_id"] = sel_tid
                    st.session_state["_last_nav"]          = "home"
                    st.rerun()


def _fmt_cell(val) -> str:
    if val is None or val == "": return "—"
    if val == "miss":            return "⚠️"
    if isinstance(val, str) and val.startswith("−"):
        return f"❌ {val}"
    try:
        f = float(val)
        if f > 0:  return f"✅ +{f:.2f}"
        if f < 0:  return f"❌ {f:.2f}"
        return "❌ 0"
    except Exception:
        return str(val)


def _col_config(short_titles: list) -> dict:
    cfg = {
        "Rank"  : st.column_config.NumberColumn("Rank",   width="small"),
        "Player": st.column_config.TextColumn("Player",   width="medium"),
        "Points": st.column_config.NumberColumn("Points", format="%.3f", width="small"),
        "Win %" : st.column_config.NumberColumn("Win %",  format="%.1f%%", width="small"),
        "Missed": st.column_config.NumberColumn("Missed", width="small"),
    }
    for col in short_titles:
        cfg[col] = st.column_config.TextColumn(col, width="small")
    return cfg
