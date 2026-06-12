"""
pages/leaderboard.py
Leaderboard with:
  - Sort by Points (default) or Name
  - Match columns in reverse order (latest first)
  - Hero tiles showing all tied players comma-separated
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

    points   = get_points(tournament_id=sel_tid)
    # matches sorted asc by date (db.get_matches sorts this way)
    matches  = get_matches(tournament_id=sel_tid, status="completed")
    users    = get_all_users()

    if not points:
        st.info("No results recorded yet for this tournament.")
        return

    matches_sorted_asc = sorted(matches,
        key=lambda m: m["match_date"] + " " + m["start_time"])

    lb = build_leaderboard(points, matches_sorted_asc, users)
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

    # Match IDs in desc order (latest first) — from first lb row
    match_ids_desc = lb[0].get("_match_ids_desc", []) if lb else []

    # ── Sort controls ─────────────────────────────────────────────────────────
    fixed_cols = ["rank", "name", "total_points", "win_pct", "missed"]
    all_cols   = fixed_cols + match_ids_desc

    c1, c2, c3 = st.columns([3, 2, 1])
    sort_by = c1.selectbox(
        "Sort by",
        ["Points", "Name"] + [_short_title(mid, matches_sorted_asc)
                               for mid in match_ids_desc],
        index=0, label_visibility="collapsed"
    )
    asc = c2.checkbox("Ascending", value=False)

    # Build display DataFrame
    df = pd.DataFrame(lb)
    df = df[[c for c in all_cols if c in df.columns]]
    df = df.rename(columns={
        "rank": "Rank", "name": "Player",
        "total_points": "Points", "win_pct": "Win %", "missed": "Missed"
    })
    # Rename match columns to short titles
    rename_map = {}
    for mid in match_ids_desc:
        m = next((x for x in matches_sorted_asc if x["match_id"] == mid), None)
        short = m["title"][:12] if m else mid
        rename_map[mid] = short
    df = df.rename(columns=rename_map)

    # Apply sort
    if sort_by == "Points":
        df = df.sort_values("Points", ascending=asc, na_position="last")
    elif sort_by == "Name":
        df = df.sort_values("Player", ascending=not asc, na_position="last")
    else:
        # Sort by match column title
        if sort_by in df.columns:
            # Need numeric sort — format cells after
            df = df.sort_values(sort_by, ascending=asc, na_position="last")

    # Format match columns
    short_titles = list(rename_map.values())
    for col in short_titles:
        if col in df.columns:
            df[col] = df[col].apply(_fmt_cell)

    # Re-rank after sort
    df.insert(0, "Rank", range(1, len(df) + 1))
    if "Rank" in df.columns and df.columns.tolist().count("Rank") > 1:
        df = df.loc[:, ~df.columns.duplicated()]

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config=_col_config(short_titles, matches_sorted_asc),
    )

    # ── Match quick links ─────────────────────────────────────────────────────
    if match_ids_desc:
        st.markdown("#### Match Details")
        cols = st.columns(min(len(match_ids_desc), 6))
        for i, mid in enumerate(match_ids_desc):
            m = next((x for x in matches_sorted_asc if x["match_id"] == mid), None)
            label = m["title"] if m else mid
            with cols[i % 6]:
                if st.button(label, key=f"lb_{mid}"):
                    st.session_state["page"]     = "match"
                    st.session_state["match_id"] = mid
                    st.session_state["match_list"] = \
                        [x["match_id"] for x in matches_sorted_asc]
                    st.session_state["match_tournament_id"] = sel_tid
                    st.session_state["_last_nav"] = "home"
                    st.rerun()


def _short_title(mid: str, matches: list) -> str:
    m = next((x for x in matches if x["match_id"] == mid), None)
    return m["title"][:12] if m else mid


def _fmt_cell(val) -> str:
    if val is None or val == "": return "—"
    if val == "miss": return "⚠️"
    if isinstance(val, str) and val.startswith("−"): return f"❌ {val}"
    try:
        f = float(val)
        if f > 0:  return f"✅ +{f:.2f}"
        if f < 0:  return f"❌ {f:.2f}"
        return "❌ 0"
    except Exception:
        return str(val)


def _col_config(short_titles: list, matches: list) -> dict:
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
