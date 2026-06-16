"""
pages/leaderboard.py
Leaderboard table styled to match the email body:
  - Dark header row, alternating row striping
  - Colour-coded cells (green=win, red=loss, amber=miss, grey=abandoned)
  - Right-aligned numbers, bold player names
  - Match Details in a neat bordered frame, 6 per row
"""

import streamlit as st
from data.db import get_matches, get_points, get_tournaments, get_all_users
from utils.streaks import build_leaderboard, leaderboard_heroes
import re


def _match_label(match_id: str) -> str:
    m = re.search(r'M0*(\d+)', match_id, re.IGNORECASE)
    if m: return f"M{m.group(1)}"
    m = re.search(r'(\d+)$', match_id)
    if m: return f"M{int(m.group(1))}"
    return match_id[-4:]


def _cell_html(val) -> str:
    """Return a <td> with colour coding matching the email body style."""
    if val is None or val == "":
        return '<td style="color:#999;text-align:right">—</td>'
    if val == "A":
        return '<td style="background:#e0e0e0;color:#777;text-align:center;font-weight:600">A</td>'
    if val == "miss":
        return '<td style="background:#fff3cd;color:#8c5500;text-align:center;font-weight:600">M</td>'
    if isinstance(val, str) and val.startswith("−"):
        num = val[1:]
        return f'<td style="background:#fcd7d7;color:#a01414;text-align:right;font-weight:600">-{num}</td>'
    try:
        f = float(val)
        if f > 0:
            return f'<td style="background:#d1f0d7;color:#0e6e24;text-align:right;font-weight:600">+{f:.2f}</td>'
        if f < 0:
            return f'<td style="background:#fcd7d7;color:#a01414;text-align:right;font-weight:600">{f:.2f}</td>'
        return '<td style="color:#555;text-align:right">0</td>'
    except Exception:
        return f'<td style="text-align:right">{val}</td>'


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
    matches = [m for m in get_matches(tournament_id=sel_tid)
               if m["status"] in ("completed", "abandoned")]
    users   = get_all_users()

    if not points:
        st.info("No results recorded yet for this tournament.")
        return

    matches_asc    = sorted(matches, key=lambda m: m["match_date"] + " " + m["start_time"])
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

    # ── Toolbar: Download CSV ────────────────────────────────────────────────
    import pandas as pd, io

    # Build plain DataFrame for download
    fixed_cols = ["rank","name","total_points","win_pct","missed"]
    all_cols   = fixed_cols + match_ids_desc
    df = pd.DataFrame(lb)
    df = df[[c for c in all_cols if c in df.columns]]
    df = df.rename(columns={
        "rank":"#","name":"Player","total_points":"Points",
        "win_pct":"Win%","missed":"Missed"})
    rename_map = {mid: _match_label(mid) for mid in match_ids_desc}
    df = df.rename(columns=rename_map)

    def _fmt_dl(val):
        if val is None or val == "": return "—"
        if val == "A":    return "A"
        if val == "miss": return "M"
        if isinstance(val, str) and val.startswith("−"): return f"-{val[1:]}"
        try:
            f = float(val)
            return f"+{f:.2f}" if f > 0 else (f"{f:.2f}" if f < 0 else "0")
        except Exception:
            return str(val)

    for col in rename_map.values():
        if col in df.columns:
            df[col] = df[col].apply(_fmt_dl)

    csv_buf = io.StringIO()
    df.to_csv(csv_buf, index=False)
    csv_bytes = csv_buf.getvalue().encode()

    tc1, tc2, tc3 = st.columns([4, 1, 1])
    tc1.markdown("### 📊 Leaderboard")
    tc2.download_button(
        "⬇️ CSV", data=csv_bytes,
        file_name=f"leaderboard_{sel_tid}.csv",
        mime="text/csv",
        use_container_width=True,
        key="lb_download"
    )

    # ── Build HTML table ──────────────────────────────────────────────────────
    m_labels = [_match_label(mid) for mid in match_ids_desc]

    # Header
    fixed_headers = ["#", "Player", "Points", "Win%", "Missed"]
    all_headers   = fixed_headers + m_labels

    th_style = "padding:10px 12px;text-align:left;font-weight:700;font-size:14px;white-space:nowrap"
    th_r     = th_style.replace("text-align:left", "text-align:right")
    th_c     = th_style.replace("text-align:left", "text-align:center")

    header_html = (
        f'<th style="{th_c}">#</th>'
        f'<th style="{th_style}">Player</th>'
        f'<th style="{th_r}">Points</th>'
        f'<th style="{th_r}">Win%</th>'
        f'<th style="{th_r}">Missed</th>'
    )
    for lbl in m_labels:
        header_html += f'<th style="{th_c}">{lbl}</th>'

    medals = ["🥇", "🥈", "🥉"]

    rows_html = ""
    for i, row in enumerate(lb):
        rank    = medals[i] if i < 3 else str(i + 1)
        name    = row.get("name", "")
        pts     = float(row.get("total_points", 0))
        winp    = float(row.get("win_pct", 0))
        missed  = int(row.get("missed", 0))

        bg      = "#f9f9f9" if i % 2 == 1 else "#ffffff"
        pts_col = "#0e6e24" if pts >= 0 else "#a01414"
        pts_bg  = "#d1f0d7" if pts >= 0 else "#fcd7d7"
        pts_str = f"+{pts:.2f}" if pts >= 0 else f"{pts:.2f}"
        miss_bg = "#fff3cd" if missed > 0 else bg
        miss_fg = "#8c5500" if missed > 0 else "#111"

        td = f"padding:9px 12px;font-size:14px;border-bottom:1px solid #e8e8e8"

        row_html = (
            f'<td style="{td};text-align:center;background:{bg}">{rank}</td>'
            f'<td style="{td};background:{bg};font-weight:600">{name}</td>'
            f'<td style="{td};text-align:right;background:{pts_bg};color:{pts_col};font-weight:700">{pts_str}</td>'
            f'<td style="{td};text-align:right;background:{bg};color:#555">{winp:.0f}%</td>'
            f'<td style="{td};text-align:right;background:{miss_bg};color:{miss_fg};font-weight:600">{missed}</td>'
        )

        for mid in match_ids_desc:
            row_html += _cell_html(row.get(mid))

        rows_html += f'<tr style="background:{bg}">{row_html}</tr>'

    st.caption(
        "Latest match first  ·  "
        "<span style='background:#d1f0d7;padding:1px 6px;border-radius:3px;font-size:12px;color:#0e6e24'>Win</span> &nbsp;"
        "<span style='background:#fcd7d7;padding:1px 6px;border-radius:3px;font-size:12px;color:#a01414'>Loss</span> &nbsp;"
        "<span style='background:#fff3cd;padding:1px 6px;border-radius:3px;font-size:12px;color:#8c5500'>M=miss</span> &nbsp;"
        "<span style='background:#e0e0e0;padding:1px 6px;border-radius:3px;font-size:12px;color:#777'>A=abandoned</span>",
        unsafe_allow_html=True
    )

    table_html = f"""
    <style>
      .lb-table {{ width:100%; border-collapse:collapse; font-family:Arial,sans-serif; }}
      .lb-table td {{ white-space:nowrap; }}
      .lb-table th {{ white-space:nowrap; }}
    </style>
    <div style="overflow-x:auto;border-radius:6px;border:1px solid #ddd;margin-top:8px">
      <table class="lb-table">
        <thead>
          <tr style="background:#28324f;color:#ffffff">{header_html}</tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
    """
    st.html(table_html)

    # ── Match Details — bordered frame, 6 per row ──────────────────────────────
    if match_ids_desc:
        st.markdown("")
        st.markdown("#### 🔍 Match Details")
        COLS_PER_ROW = 6
        chunks       = [match_ids_desc[i:i+COLS_PER_ROW]
                        for i in range(0, len(match_ids_desc), COLS_PER_ROW)]
        frame_h = min(len(chunks), 5) * 48 * 2 + 16

        with st.container(border=True, height=frame_h):
            for chunk in chunks:
                cols = st.columns(COLS_PER_ROW)
                for ci, mid in enumerate(chunk):
                    m   = next((x for x in matches_asc if x["match_id"] == mid), None)
                    tip = m["title"] if m else mid
                    with cols[ci]:
                        if st.button(_match_label(mid), key=f"lb_{mid}",
                                     help=tip, use_container_width=True):
                            st.session_state["page"]                = "match"
                            st.session_state["match_id"]            = mid
                            st.session_state["match_list"]          =                                 [x["match_id"] for x in matches_asc]
                            st.session_state["match_tournament_id"] = sel_tid
                            # Must match a valid navbar page so navbar
                            # doesn't detect a mismatch and override
                            st.session_state["_last_nav"]           = "leaderboard"
                            st.rerun()
                for ci in range(len(chunk), COLS_PER_ROW):
                    cols[ci].empty()
