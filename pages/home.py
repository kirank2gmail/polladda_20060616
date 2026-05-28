"""
pages/home.py
Home page — tournament selector, ongoing matches, past matches.
No auth — user is already set in session_state by app.py.
"""

import streamlit as st
from data.store import (
    get_tournaments, get_matches, get_user_vote,
    is_registered, register_user, get_user_by_id
)
from data.store import get_points
from utils.timezone import is_voting_open, format_match_times, format_countdown


def show_home(user: dict):
    user_tz = user.get("timezone", "Asia/Kolkata") or "Asia/Kolkata"

    # ── Tournament selector ──────────────────────────────────────────────────
    tournaments = get_tournaments()
    if not tournaments:
        st.info("No tournaments available yet. Ask the admin to create one.")
        return

    t_names = [t["name"] for t in tournaments]
    t_ids   = [t["tournament_id"] for t in tournaments]

    sel_name = st.selectbox("🏆 Select Tournament", t_names,
                            label_visibility="collapsed")
    sel_tid  = t_ids[t_names.index(sel_name)]

    # ── Registration ─────────────────────────────────────────────────────────
    if not is_registered(user["user_id"], sel_tid):
        st.warning("You are not registered for this tournament.")
        if st.button("Register Now", type="primary"):
            register_user(user["user_id"], sel_tid)
            st.success("Registered! You can now vote on matches.")
            st.rerun()
        return

    # ── Load matches ─────────────────────────────────────────────────────────
    all_matches = get_matches(tournament_id=sel_tid)
    if not all_matches:
        st.info("No matches scheduled yet.")
        return

    upcoming  = [m for m in all_matches if m["status"] == "upcoming"]
    completed = [m for m in all_matches if m["status"] == "completed"]

    # ── Upcoming matches ─────────────────────────────────────────────────────
    st.markdown("### 📌 Upcoming Matches")
    if not upcoming:
        st.caption("No upcoming matches.")
    else:
        for m in upcoming:
            _card_upcoming(m, user["user_id"], user_tz)

    st.markdown("---")

    # ── Past matches ─────────────────────────────────────────────────────────
    st.markdown("### 📋 Past Matches")
    if not completed:
        st.caption("No completed matches yet.")
    else:
        for m in completed:
            _card_completed(m, user["user_id"], user_tz)

    st.markdown("---")

    # ── Leaderboard link ─────────────────────────────────────────────────────
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        if st.button("🏅 View Full Leaderboard", use_container_width=True):
            st.session_state["page"]          = "leaderboard"
            st.session_state["tournament_id"] = sel_tid
            st.rerun()


def _card_upcoming(m: dict, user_id: str, user_tz: str):
    existing  = get_user_vote(user_id, m["match_id"])
    times     = format_match_times(m, user_tz)
    msg, sev  = format_countdown(m)
    open_vote = is_voting_open(m)

    with st.container(border=True):
        c1, c2, c3 = st.columns([4, 3, 2])
        with c1:
            st.markdown(f"**{m['title']}**")
            st.caption(f"📍 {m['location']}   📅 {times['local']}")
            if times["user"]:
                st.caption(f"🕐 Your time: {times['user']}")
        with c2:
            if sev == "error":
                st.error(msg, icon="🔴")
            elif sev == "warning":
                st.warning(msg, icon="⚠️")
            else:
                st.success(msg, icon="🟢")
        with c3:
            if existing:
                st.markdown(f"Your vote: **{existing['vote']}** ✅")
                label = "Change Vote →"
            else:
                label = "Vote Now →"
            if open_vote:
                if st.button(label, key=f"home_btn_{m['match_id']}"):
                    st.session_state["page"]     = "match"
                    st.session_state["match_id"] = m["match_id"]
                    st.rerun()
            else:
                st.caption("Voting closed")


def _card_completed(m: dict, user_id: str, user_tz: str):
    existing = get_user_vote(user_id, m["match_id"])
    result   = m.get("result", "")
    times    = format_match_times(m, user_tz)

    # Points earned
    pts_list = get_points(user_id=user_id)
    pts      = 0.0
    for p in pts_list:
        if p["match_id"] == m["match_id"]:
            pts = float(p.get("total_points", 0))
            break

    with st.container(border=True):
        c1, c2, c3 = st.columns([4, 3, 2])
        with c1:
            st.markdown(f"**{m['title']}**")
            st.caption(f"📍 {m['location']}   📅 {times['local']}")
        with c2:
            st.markdown(f"Result: **{result}**")
            if existing:
                correct = existing["vote"] == result
                st.caption(f"Your vote: {existing['vote']} {'✅' if correct else '❌'}")
            else:
                st.caption("⚠️ No vote cast")
        with c3:
            st.metric("Points", f"+{pts}" if pts > 0 else str(pts))
            if st.button("Details →", key=f"hist_{m['match_id']}"):
                st.session_state["page"]     = "match"
                st.session_state["match_id"] = m["match_id"]
                st.rerun()
