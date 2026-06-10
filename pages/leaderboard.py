"""
pages/leaderboard.py
Sortable leaderboard — per-match columns, streaks, missed count.
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

    t_names  = [t["name"] for t in tournaments]
    t_ids    = [t["tournament_id"] for t in tournaments]
    pre_tid  = st.session_state.get("tournament_id", t_ids[0])
    pre_idx  = t_ids.index(pre_tid) if pre_tid in t_ids else 0

    sel_name = st.selectbox("🏆 Tournament", t_names, index=pre_idx)
    sel_tid  = t_ids[t_names.index(sel_name)]

    points   = get_points(tournament_id=sel_tid)
    matches  = get_matches(tournament_id=sel_tid, status="completed")
    users    = get_all_users()

    if not points:
        st.info("No results recorded yet for this tournament.")
        return

    # Sort matches by date for column order
    matches_sorted = sorted(matches, key=lambda m: m["match_date"] + m["start_time"])

    lb = build_leaderboard(points, matches_sorted, users)
    if not lb:
        st.info("Leaderboard not available yet.")
        return

    # ── Hero stats ───────────────────────────────────────────────────────────
    heroes = leaderboard_heroes(lb)
    if heroes:
        st.markdown("### 🎖️ Highlights")
        h1, h2, h3 = st.columns(3)
        with h1:
            with st.container(border=True):
                st.markdown("🔥 **Longest Win Streak**")
                hw = heroes["top_win_streak"]
                st.markdown(f"**{hw['name']}**  —  {hw['value']} wins")
        with h2:
            with st.container(border=True):
                st.markdown("💀 **Longest Loss Streak**")
                hl = heroes["top_loss_streak"]
                st.markdown(f"**{hl['name']}**  —  {hl['value']} losses")
        with h3:
            with st.container(border=True):
                st.markdown("⚠️ **Most Missed Votes**")
                hm = heroes["top_missed"]
                st.markdown(f"**{hm['name']}**  —  {hm['value']} misses")

    st.markdown("---")
    st.markdown("### 📊 Leaderboard")

    match_ids   = [m["match_id"] for m in matches_sorted]
    fixed_cols  = ["rank","name","total_points","win_pct","missed"]
    all_cols    = fixed_cols + match_ids

    # Build display DataFrame
    df = pd.DataFrame(lb)
    df = df[[c for c in all_cols if c in df.columns]]
    df = df.rename(columns={
        "rank":"Rank","name":"Player",
        "total_points":"Points","win_pct":"Win %","missed":"Missed"
    })

    # Format match columns
    for mid in match_ids:
        if mid in df.columns:
            df[mid] = df[mid].apply(_fmt_cell)

    # ── Sort controls ────────────────────────────────────────────────────────
    sort_opts = ["Points","Win %","Missed","Rank"] + match_ids
    sort_opts = [c for c in sort_opts if c in df.columns]

    c1, c2 = st.columns([3, 1])
    sort_by = c1.selectbox("Sort by", sort_opts, label_visibility="collapsed")
    asc     = c2.checkbox("Ascending", value=False)

    sort_col = sort_by if sort_by in df.columns else "Points"
    df = df.sort_values(sort_col, ascending=asc, na_position="last")

    # ── Render ───────────────────────────────────────────────────────────────
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config=_col_config(match_ids, matches_sorted),
    )

    # ── Match quick links ────────────────────────────────────────────────────
    if match_ids:
        st.markdown("#### Match Details")
        cols = st.columns(min(len(match_ids), 6))
        for i, mid in enumerate(match_ids):
            m_row = next((m for m in matches_sorted if m["match_id"] == mid), None)
            label = m_row["title"] if m_row else mid
            with cols[i % 6]:
                if st.button(label, key=f"lb_{mid}"):
                    st.session_state["page"]     = "match"
                    st.session_state["match_id"] = mid
                    st.rerun()


def _fmt_cell(val) -> str:
    if val is None or val == "":
        return "—"
    if val == "miss":
        return "⚠️"
    if isinstance(val, str) and val.startswith("−"):
        return f"❌ {val}"
    try:
        f = float(val)
        if f > 0:   return f"✅ +{f}"
        if f < 0:   return f"❌ {f}"
        return "❌ 0"
    except Exception:
        return str(val)


def _col_config(match_ids, matches) -> dict:
    cfg = {
        "Rank"   : st.column_config.NumberColumn("Rank",   width="small"),
        "Player" : st.column_config.TextColumn("Player",   width="medium"),
        "Points" : st.column_config.NumberColumn("Points", format="%.3f", width="small"),
        "Win %"  : st.column_config.NumberColumn("Win %",  format="%.1f%%", width="small"),
        "Missed" : st.column_config.NumberColumn("Missed", width="small"),
    }
    for mid in match_ids:
        m = next((x for x in matches if x["match_id"] == mid), None)
        cfg[mid] = st.column_config.TextColumn(
            mid, help=m["title"] if m else mid, width="small"
        )
    return cfg
