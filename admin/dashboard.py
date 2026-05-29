"""
admin/dashboard.py
Admin panel — tournaments, matches (with delete), results (with update).

Fixes applied:
  1. Options validated for at least 2 pipe-separated values
  2. Results tab blocks entry until poll is closed (match start time passed)
  3. Admin can delete any match
  4. Admin can update/correct result at any time after poll closes
"""

import streamlit as st
import pandas as pd
from datetime import date, time
from data.db import (
    create_tournament, get_tournaments, get_matches,
    create_match, bulk_create_matches, update_match_result,
    update_tournament_status, delete_match
)
from data.points import run_points_calculation
from utils.timezone import COMMON_TIMEZONES, get_match_cutoff_utc, is_voting_open


def show_admin(user: dict):
    st.title("⚙️ Admin Panel")
    st.caption(f"Logged in as **{user['name']}**")

    tab1, tab2, tab3 = st.tabs([
        "🏆 Tournaments", "📋 Matches", "🎯 Results"
    ])
    with tab1:
        _tournaments_tab(user)
    with tab2:
        _matches_tab(user)
    with tab3:
        _results_tab()


# ── Tournaments ───────────────────────────────────────────────────────────────

def _tournaments_tab(user: dict):
    st.subheader("Create Tournament")
    with st.form("create_t"):
        c1, c2  = st.columns(2)
        t_id    = c1.text_input("Tournament ID", placeholder="IPL2026")
        name    = c2.text_input("Name",          placeholder="IPL 2026")
        sport   = c1.selectbox("Sport", [
            "Cricket", "Football", "Formula 1", "Tennis",
            "Basketball", "Rugby", "Golf", "Hockey", "Other"
        ])
        s_date  = c2.date_input("Start Date", value=date.today())
        c3, c4  = st.columns(2)
        allowed = c3.number_input("Free Misses Allowed",
                                   min_value=0, max_value=20, value=3)
        penalty = c4.number_input("Penalty Points per Miss",
                                   min_value=0.0, max_value=10.0,
                                   value=0.5, step=0.25)
        st.info(
            f"Users get **{int(allowed)}** free misses. "
            f"Each extra miss deducts **{penalty}** pts and adds to winner pool."
        )
        if st.form_submit_button("Create Tournament", type="primary"):
            if not t_id or not name:
                st.error("ID and Name required.")
            else:
                create_tournament({
                    "tournament_id" : t_id,
                    "name"          : name,
                    "sport"         : sport,
                    "start_date"    : str(s_date),
                    "allowed_misses": allowed,
                    "penalty_points": penalty,
                    "created_by"    : user["name"],
                })
                st.success(f"Tournament **{name}** created!")
                st.rerun()

    st.markdown("---")
    st.subheader("Existing Tournaments")
    for t in get_tournaments():
        with st.container(border=True):
            c1, c2, c3 = st.columns([4, 2, 2])
            c1.markdown(f"**{t['name']}** — {t['sport']}")
            c1.caption(f"ID: `{t['tournament_id']}`  ·  Starts: {t['start_date']}")
            c2.metric("Free Misses",  t["allowed_misses"])
            c2.metric("Penalty Pts",  t["penalty_points"])
            status = t.get("status", "upcoming")
            opts   = ["upcoming", "active", "completed"]
            new_s  = c3.selectbox("Status", opts,
                                   index=opts.index(status),
                                   key=f"ts_{t['tournament_id']}")
            if c3.button("Update", key=f"tsb_{t['tournament_id']}"):
                update_tournament_status(t["tournament_id"], new_s)
                st.rerun()


# ── Matches ───────────────────────────────────────────────────────────────────

def _matches_tab(user: dict):
    ts = get_tournaments()
    if not ts:
        st.warning("Create a tournament first.")
        return

    t_names = [t["name"] for t in ts]
    t_ids   = [t["tournament_id"] for t in ts]
    sel_n   = st.selectbox("Tournament", t_names, key="adm_m_t")
    sel_tid = t_ids[t_names.index(sel_n)]

    tab_a, tab_b = st.tabs(["📤 Bulk Upload CSV", "➕ Add Single Match"])
    with tab_a:
        _bulk_upload(sel_tid, user)
    with tab_b:
        _single_form(sel_tid, user)

    st.markdown("---")
    st.subheader(f"Matches — {sel_n}")
    ms = get_matches(sel_tid)
    if not ms:
        st.caption("No matches yet.")
        return

    for m in ms:
        with st.container(border=True):
            c1, c2, c3 = st.columns([5, 2, 1])
            with c1:
                st.markdown(f"**{m['title']}**")
                st.caption(
                    f"`{m['match_id']}`  ·  {m['location']}  ·  "
                    f"{m['match_date']} {m['start_time']} {m['timezone'].split('/')[-1]}  ·  "
                    f"Options: `{m['options']}`  ·  "
                    f"Status: **{m['status']}**"
                    + (f"  ·  Result: **{m['result']}**" if m.get("result") else "")
                )
            with c2:
                poll_open = is_voting_open(m)
                if poll_open:
                    st.caption("🟢 Poll open")
                else:
                    st.caption("🔴 Poll closed")
            with c3:
                # Delete button — confirm via checkbox
                del_key = f"del_confirm_{m['match_id']}"
                if st.button("🗑️ Delete", key=f"del_{m['match_id']}",
                              type="secondary"):
                    st.session_state[del_key] = True

                if st.session_state.get(del_key):
                    st.warning(f"Delete **{m['title']}**?")
                    cc1, cc2 = st.columns(2)
                    if cc1.button("Yes, delete", key=f"delyes_{m['match_id']}",
                                   type="primary"):
                        delete_match(m["match_id"])
                        st.session_state.pop(del_key, None)
                        st.success("Match deleted.")
                        st.rerun()
                    if cc2.button("Cancel", key=f"delno_{m['match_id']}"):
                        st.session_state.pop(del_key, None)
                        st.rerun()


def _validate_options(options_str: str) -> tuple[bool, str]:
    """Returns (valid, error_message). Valid if 2+ non-empty pipe-separated options."""
    parts = [o.strip() for o in options_str.split("|") if o.strip()]
    if len(parts) < 2:
        return False, "At least 2 options required, separated by `|`  e.g. `SRH|RCB`"
    return True, ""


def _bulk_upload(tournament_id: str, user: dict):
    st.markdown("""
**CSV columns:** `match_id, title, location, match_date, start_time, timezone, options`

```
match_id,title,location,match_date,start_time,timezone,options
IPL2026-M001,SRH vs RCB,Hyderabad,2026-05-24,19:30,Asia/Kolkata,SRH|RCB
F12026-R001,Monaco GP,Monaco,2026-05-26,14:00,Europe/Monaco,VER|HAM|LEC|NOR
```
Options must have at least 2 pipe-separated values.
    """)
    uploaded = st.file_uploader("Upload CSV", type="csv")
    if not uploaded:
        return
    try:
        df = pd.read_csv(uploaded, dtype=str)
        st.dataframe(df, use_container_width=True)
        required = ["match_id", "title", "location",
                    "match_date", "start_time", "timezone", "options"]
        missing  = [c for c in required if c not in df.columns]
        if missing:
            st.error(f"Missing columns: {missing}")
            return

        # Validate options column
        errors = []
        for _, row in df.iterrows():
            valid, err = _validate_options(str(row["options"]))
            if not valid:
                errors.append(f"`{row['match_id']}`: {err}")
        if errors:
            for e in errors:
                st.error(e)
            return

        # Preview UTC cutoffs
        for _, row in df.iterrows():
            try:
                utc = get_match_cutoff_utc(row.to_dict())
                st.caption(
                    f"`{row['match_id']}` — "
                    f"voting closes {utc.strftime('%d %b %Y %H:%M UTC')}"
                )
            except Exception as e:
                st.warning(f"{row['match_id']}: {e}")

        if st.button("Import All", type="primary"):
            bulk_create_matches(tournament_id, df.to_dict("records"), user["name"])
            st.success(f"{len(df)} matches imported!")
            st.rerun()
    except Exception as e:
        st.error(f"CSV error: {e}")


def _single_form(tournament_id: str, user: dict):
    with st.form("add_match"):
        c1, c2   = st.columns(2)
        match_id = c1.text_input("Match ID",  placeholder="IPL2026-M001")
        title    = c2.text_input("Title",     placeholder="SRH vs RCB")
        location = c1.text_input("Location",  placeholder="Hyderabad")
        m_date   = c2.date_input("Match Date", value=date.today())
        c3, c4   = st.columns(2)
        s_time   = c3.time_input("Start Time (venue local)", value=time(19, 30))
        tz       = c4.selectbox("Venue Timezone", COMMON_TIMEZONES)
        options  = st.text_input(
            "Vote Options (pipe separated — minimum 2)",
            placeholder="SRH|RCB  or  VER|HAM|LEC|NOR"
        )

        # Live validation hint
        if options:
            valid, err = _validate_options(options)
            if not valid:
                st.error(err)
            else:
                parts = [o.strip() for o in options.split("|") if o.strip()]
                st.success(f"{len(parts)} options: {' · '.join(parts)}")

        try:
            utc = get_match_cutoff_utc({
                "match_date": str(m_date),
                "start_time": s_time.strftime("%H:%M"),
                "timezone"  : tz,
            })
            st.caption(f"Voting closes: **{utc.strftime('%d %b %Y %H:%M UTC')}**")
        except Exception:
            pass

        if st.form_submit_button("Add Match", type="primary"):
            if not match_id or not title:
                st.error("ID and Title required.")
            else:
                valid, err = _validate_options(options)
                if not valid:
                    st.error(err)
                else:
                    create_match({
                        "match_id"      : match_id,
                        "tournament_id" : tournament_id,
                        "title"         : title,
                        "location"      : location,
                        "match_date"    : str(m_date),
                        "start_time"    : s_time.strftime("%H:%M"),
                        "timezone"      : tz,
                        "options"       : options,
                        "created_by"    : user["name"],
                    })
                    st.success(f"Match `{match_id}` added!")
                    st.rerun()


# ── Results ───────────────────────────────────────────────────────────────────

def _results_tab():
    ts = get_tournaments()
    if not ts:
        st.warning("No tournaments found.")
        return

    t_names = [t["name"] for t in ts]
    t_ids   = [t["tournament_id"] for t in ts]
    sel_n   = st.selectbox("Tournament", t_names, key="adm_r_t")
    sel_tid = t_ids[t_names.index(sel_n)]

    all_ms  = get_matches(sel_tid)
    if not all_ms:
        st.info("No matches in this tournament.")
        return

    # ── Pending results (poll closed, no result yet) ───────────────────────
    st.subheader("Awaiting Result")
    st.caption("Only matches where voting has closed are shown here.")

    pending = [
        m for m in all_ms
        if m["status"] != "completed" and not is_voting_open(m)
    ]
    still_open = [
        m for m in all_ms
        if m["status"] != "completed" and is_voting_open(m)
    ]

    if still_open:
        st.info(
            f"**{len(still_open)}** match(es) still have voting open — "
            f"results cannot be entered until the poll closes."
        )
        for m in still_open:
            st.caption(f"⏳ `{m['match_id']}` — {m['title']} — poll closes at "
                       f"{m['start_time']} {m['timezone'].split('/')[-1]}")

    if not pending:
        st.caption("No matches awaiting result entry.")
    else:
        for m in pending:
            opts = [o.strip() for o in m["options"].split("|") if o.strip()]
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 2])
                c1.markdown(f"**{m['title']}**")
                c1.caption(f"`{m['match_id']}`  ·  {m['match_date']}  {m['start_time']}")
                winner = c2.selectbox("Winner / Result", opts,
                                       key=f"r_{m['match_id']}")
                if c3.button("Save Result", key=f"rb_{m['match_id']}",
                              type="primary"):
                    with st.spinner("Calculating points..."):
                        update_match_result(m["match_id"], winner)
                        records = run_points_calculation(
                            m["match_id"], sel_tid, winner
                        )
                    correct = sum(
                        1 for r in records if r.get("total_points", 0) > 0
                    )
                    st.success(
                        f"**{winner}** won — "
                        f"{correct} correct voter(s) awarded points"
                    )
                    st.rerun()

    # ── Completed — allow result update ───────────────────────────────────
    done = [m for m in all_ms if m["status"] == "completed"]
    if done:
        st.markdown("---")
        st.subheader("Update / Correct Result")
        st.caption("Select a different winner to recalculate all points.")
        for m in done:
            opts    = [o.strip() for o in m["options"].split("|") if o.strip()]
            cur_idx = opts.index(m["result"]) if m["result"] in opts else 0
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 2])
                c1.markdown(f"**{m['title']}**")
                c1.caption(
                    f"`{m['match_id']}`  ·  "
                    f"Current result: **{m['result']}**"
                )
                new_w = c2.selectbox(
                    "Change result to", opts,
                    index=cur_idx,
                    key=f"corr_{m['match_id']}"
                )
                btn_disabled = (new_w == m["result"])
                if c3.button(
                    "Update Result",
                    key=f"corrb_{m['match_id']}",
                    type="primary",
                    disabled=btn_disabled
                ):
                    with st.spinner("Recalculating points..."):
                        update_match_result(m["match_id"], new_w)
                        run_points_calculation(m["match_id"], sel_tid, new_w)
                    st.success(f"Result updated to **{new_w}** — points recalculated.")
                    st.rerun()
