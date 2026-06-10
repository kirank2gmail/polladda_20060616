"""
admin/dashboard.py
Admin panel — users, tournaments, matches, results.

New in this version:
  - Title → options auto-suggest (parses "A vs B" → "A|B")
  - Scoring mode: ratio (existing) or fixed odds
  - Poll mode: closed (votes hidden till end) or open (always visible)
"""

import re
import streamlit as st
import pandas as pd
from datetime import date, time
from data.db import (
    get_all_users, create_user, delete_user, set_user_role,
    get_display_name, change_password,
    get_tournaments, create_tournament, update_tournament_status,
    get_matches, create_match, bulk_create_matches,
    update_match_result, delete_match,
    get_votes, delete_vote, get_user_by_id, verify_password
)
from data.points import run_points_calculation
from utils.timezone import COMMON_TIMEZONES, get_match_cutoff_utc, is_voting_open


# ── Options auto-suggest from title ──────────────────────────────────────────

def _options_from_title(title: str) -> str:
    """
    Parse a match title and extract pipe-separated vote options.

    Patterns handled:
      "SRH vs RCB"           → "SRH|RCB"
      "SRH vs RCB vs DC"     → "SRH|RCB|DC"
      "Man Utd v Arsenal"    → "Man Utd|Arsenal"
      "VER / HAM / LEC"      → "VER|HAM|LEC"
      "India - Australia"    → "India|Australia"
    """
    if not title.strip():
        return ""

    # Split on common separators: vs, v, /, - (with surrounding spaces)
    parts = re.split(r'\s+(?:vs\.?|v\.?)\s+|\s*/\s*|\s+-\s+', title.strip(), flags=re.IGNORECASE)
    parts = [p.strip() for p in parts if p.strip()]

    if len(parts) >= 2:
        return "|".join(parts)

    return ""


def _validate_options(s: str) -> tuple[bool, str]:
    parts = [o.strip() for o in s.split("|") if o.strip()]
    if len(parts) < 2:
        return False, "At least 2 options required, pipe-separated e.g. `SRH|RCB`"
    return True, ""


# ── Main ──────────────────────────────────────────────────────────────────────

def show_admin(user: dict):
    st.title("⚙️ Admin Panel")
    st.caption(f"Logged in as **{get_display_name(user['user_id'])}**")

    tab1, tab2, tab3, tab4 = st.tabs([
        "👥 Users", "🏆 Tournaments", "📋 Matches", "🎯 Results"
    ])
    with tab1: _users_tab(user)
    with tab2: _tournaments_tab(user)
    with tab3: _matches_tab(user)
    with tab4: _results_tab()


# ── Users ─────────────────────────────────────────────────────────────────────

def _users_tab(admin: dict):
    st.subheader("Create New User")
    st.caption("User receives a temporary password and must change it on first login. "
               "Nickname defaults to their first name.")

    with st.form("create_user"):
        c1, c2 = st.columns(2)
        uname  = c1.text_input("Username", placeholder="john")
        role   = c2.selectbox("Role", ["user", "admin"])
        pw     = c1.text_input("Temporary Password", type="password",
                                placeholder="min 6 characters")
        pw2    = c2.text_input("Confirm Password", type="password")
        if st.form_submit_button("Create User", type="primary"):
            if not uname.strip():
                st.error("Username required.")
            elif len(pw) < 6:
                st.error("Password must be at least 6 characters.")
            elif pw != pw2:
                st.error("Passwords do not match.")
            elif any(u["name"].lower() == uname.lower() for u in get_all_users()):
                st.error("Username already exists.")
            else:
                new_u = create_user(uname.strip(), pw, role,
                                    created_by=admin["name"])
                st.success(
                    f"User **{uname}** created.  "
                    f"Nickname set to **{new_u['nickname']}**.  "
                    f"User ID: `{new_u['user_id']}`"
                )
                st.rerun()

    st.markdown("---")
    st.subheader("All Users")
    users = get_all_users()
    if not users:
        st.caption("No users yet.")
        return

    for u in users:
        nick    = get_display_name(u["user_id"])
        is_self = u["user_id"] == admin["user_id"]
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
            with c1:
                st.markdown(f"**{u['name']}**  —  nickname: `{nick}`")
                st.caption(
                    f"ID: `{u['user_id']}`  ·  "
                    f"Created: {u.get('created_at','')[:10]}  ·  "
                    f"{'⚠️ Must change password' if u.get('must_change_password') else '✅ Password set'}"
                )
            with c2:
                opts     = ["user", "admin"]
                cur_idx  = opts.index(u.get("role", "user"))
                new_role = st.selectbox("Role", opts, index=cur_idx,
                                        key=f"role_{u['user_id']}",
                                        disabled=is_self)
                if not is_self and st.button("Update Role",
                                              key=f"roleb_{u['user_id']}"):
                    set_user_role(u["user_id"], new_role)
                    st.success("Role updated.")
                    st.rerun()
            with c3:
                st.caption("Reset password")
                with st.form(f"rst_{u['user_id']}"):
                    npw = st.text_input("New password", type="password",
                                        key=f"npw_{u['user_id']}")
                    if st.form_submit_button("Reset"):
                        if len(npw) < 6:
                            st.error("Min 6 chars.")
                        else:
                            change_password(u["user_id"], npw)
                            from data.db import _update_where
                            _update_where("users",
                                lambda r, uid=u["user_id"]: r["user_id"] == uid,
                                lambda r: r.update({"must_change_password": True}))
                            st.success("Password reset.")
            with c4:
                if not is_self:
                    if st.button("🗑️", key=f"delu_{u['user_id']}",
                                  help="Delete user"):
                        st.session_state[f"del_u_{u['user_id']}"] = True
            if st.session_state.get(f"del_u_{u['user_id']}"):
                st.warning(f"Delete user **{u['name']}**?")
                cc1, cc2 = st.columns(2)
                if cc1.button("Yes", key=f"deluyes_{u['user_id']}", type="primary"):
                    delete_user(u["user_id"])
                    st.session_state.pop(f"del_u_{u['user_id']}", None)
                    st.rerun()
                if cc2.button("Cancel", key=f"deluno_{u['user_id']}"):
                    st.session_state.pop(f"del_u_{u['user_id']}", None)
                    st.rerun()


# ── Tournaments ───────────────────────────────────────────────────────────────

def _tournaments_tab(user: dict):
    st.subheader("Create Tournament")
    with st.form("create_t"):
        c1, c2  = st.columns(2)
        t_id    = c1.text_input("Tournament ID", placeholder="IPL2026")
        name    = c2.text_input("Name",          placeholder="IPL 2026")
        sport   = c1.selectbox("Sport", [
            "Cricket","Football","Formula 1","Tennis",
            "Basketball","Rugby","Golf","Hockey","Other"])
        s_date  = c2.date_input("Start Date", value=date.today())
        c3, c4  = st.columns(2)
        allowed = c3.number_input("Free Misses Allowed",
                                   min_value=0, max_value=20, value=3)
        penalty = c4.number_input("Penalty Points per Miss",
                                   min_value=0.0, max_value=10.0,
                                   value=0.5, step=0.25)
        st.info(f"Users get **{int(allowed)}** free misses. "
                f"Each extra miss deducts **{penalty}** pts and adds to winner pool.")
        if st.form_submit_button("Create Tournament", type="primary"):
            if not t_id or not name:
                st.error("ID and Name required.")
            else:
                create_tournament({
                    "tournament_id": t_id, "name": name, "sport": sport,
                    "start_date": str(s_date), "allowed_misses": allowed,
                    "penalty_points": penalty, "created_by": user["name"]})
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
            status = t.get("status","upcoming")
            opts   = ["upcoming","active","completed"]
            new_s  = c3.selectbox("Status", opts, index=opts.index(status),
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
    with tab_a: _bulk_upload(sel_tid, user)
    with tab_b: _single_form(sel_tid, user)

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
                scoring = m.get("scoring_mode","ratio")
                poll    = m.get("poll_mode","closed")
                odds    = m.get("fixed_odds","")
                st.markdown(f"**{m['title']}**")
                st.caption(
                    f"`{m['match_id']}`  ·  {m['location']}  ·  "
                    f"{m['match_date']} {m['start_time']} {m['timezone'].split('/')[-1]}  ·  "
                    f"Options: `{m['options']}`  ·  "
                    f"Scoring: **{scoring}**"
                    + (f" @ {odds}" if scoring == "fixed" else "") +
                    f"  ·  Poll: **{poll}**  ·  Status: **{m['status']}**"
                    + (f"  ·  Result: **{m['result']}**" if m.get("result") else "")
                )
            with c2:
                st.caption("🟢 Poll open" if is_voting_open(m) else "🔴 Poll closed")
                votes = get_votes(match_id=m["match_id"])
                if votes:
                    with st.expander(f"👁 Votes ({len(votes)})"):
                        all_u = get_all_users()
                        umap  = {u["user_id"]: get_display_name(u["user_id"])
                                 for u in all_u}
                        for v in votes:
                            dn = umap.get(v["user_id"], v["user_id"])
                            cc1, cc2 = st.columns([3, 1])
                            cc1.markdown(f"**{dn}** → {v['vote']}")
                            if cc2.button("🗑️", key=f"dv_{v['vote_id']}"):
                                delete_vote(v["user_id"], m["match_id"])
                                st.success(f"Vote by {dn} deleted.")
                                st.rerun()
            with c3:
                if st.button("🗑️ Delete", key=f"del_{m['match_id']}"):
                    st.session_state[f"del_m_{m['match_id']}"] = True
            if st.session_state.get(f"del_m_{m['match_id']}"):
                st.warning(f"Delete **{m['title']}**?")
                cc1, cc2 = st.columns(2)
                if cc1.button("Yes", key=f"delmy_{m['match_id']}", type="primary"):
                    delete_match(m["match_id"])
                    st.session_state.pop(f"del_m_{m['match_id']}", None)
                    st.rerun()
                if cc2.button("No", key=f"delmn_{m['match_id']}"):
                    st.session_state.pop(f"del_m_{m['match_id']}", None)
                    st.rerun()


def _bulk_upload(tid: str, user: dict):
    st.markdown("""
**CSV columns:** `match_id, title, location, match_date, start_time, timezone, options, scoring_mode, fixed_odds, poll_mode`

- `scoring_mode`: `ratio` (default) or `fixed`
- `fixed_odds`: points for correct pick when scoring_mode=fixed (e.g. `2.5`)
- `poll_mode`: `closed` (default, votes hidden till end) or `open` (always visible)

```
match_id,title,location,match_date,start_time,timezone,options,scoring_mode,fixed_odds,poll_mode
IPL2026-M001,SRH vs RCB,Hyderabad,2026-05-24,19:30,Asia/Kolkata,SRH|RCB,ratio,,closed
IPL2026-M002,MI vs CSK,Mumbai,2026-05-25,19:30,Asia/Kolkata,MI|CSK,fixed,2.5,open
```
    """)
    uploaded = st.file_uploader("Upload CSV", type="csv")
    if not uploaded: return
    try:
        df = pd.read_csv(uploaded, dtype=str).fillna("")
        st.dataframe(df, use_container_width=True)
        required = ["match_id","title","location","match_date","start_time","timezone","options"]
        missing  = [c for c in required if c not in df.columns]
        if missing: st.error(f"Missing columns: {missing}"); return

        errors = []
        for _, row in df.iterrows():
            # Auto-suggest options from title if blank
            opts = str(row.get("options","")).strip()
            if not opts:
                opts = _options_from_title(str(row.get("title","")))
            valid, err = _validate_options(opts)
            if not valid: errors.append(f"`{row['match_id']}`: {err}")
        if errors:
            for e in errors: st.error(e)
            return

        for _, row in df.iterrows():
            try:
                utc = get_match_cutoff_utc(row.to_dict())
                st.caption(f"`{row['match_id']}` closes {utc.strftime('%d %b %Y %H:%M UTC')}")
            except Exception as e:
                st.warning(f"{row['match_id']}: {e}")

        if st.button("Import All", type="primary"):
            rows = []
            for _, row in df.iterrows():
                r = row.to_dict()
                if not r.get("options","").strip():
                    r["options"] = _options_from_title(r.get("title",""))
                if not r.get("scoring_mode","").strip():
                    r["scoring_mode"] = "ratio"
                if not r.get("poll_mode","").strip():
                    r["poll_mode"] = "closed"
                rows.append(r)
            bulk_create_matches(tid, rows, user["name"])
            st.success(f"{len(rows)} matches imported!")
            st.rerun()
    except Exception as e:
        st.error(f"CSV error: {e}")


def _single_form(tid: str, user: dict):
    # Use session state to allow live title → options suggestion
    # outside of form (forms don't support dynamic updates mid-entry)

    st.markdown("#### Match Details")

    c1, c2   = st.columns(2)
    match_id = c1.text_input("Match ID", placeholder="IPL2026-M001",
                              key="sf_match_id")
    title    = c2.text_input("Title",    placeholder="SRH vs RCB",
                              key="sf_title")
    location = c1.text_input("Location", placeholder="Hyderabad",
                              key="sf_location")
    m_date   = c2.date_input("Match Date", value=date.today(),
                              key="sf_date")
    c3, c4   = st.columns(2)
    s_time   = c3.time_input("Start Time (venue local)", value=time(19, 30),
                              key="sf_time")
    tz       = c4.selectbox("Venue Timezone", COMMON_TIMEZONES, key="sf_tz")

    # Auto-suggest options from title
    suggested = _options_from_title(title) if title else ""
    options   = st.text_input(
        "Vote Options (pipe separated, min 2)",
        value=suggested,
        placeholder="SRH|RCB  or  VER|HAM|LEC|NOR",
        key="sf_options",
        help="Auto-filled from title — edit freely"
    )
    if options:
        valid, err = _validate_options(options)
        if not valid:
            st.error(err)
        else:
            parts = [o.strip() for o in options.split("|") if o.strip()]
            st.success(f"{len(parts)} options: {' · '.join(parts)}")

    # Scoring mode
    st.markdown("#### Scoring & Poll Settings")
    sc1, sc2, sc3 = st.columns(3)
    scoring_mode  = sc1.selectbox(
        "Scoring Mode",
        ["ratio", "fixed"],
        format_func=lambda x: "📊 Ratio (dynamic)" if x == "ratio" else "🎯 Fixed Odds",
        key="sf_scoring"
    )
    fixed_odds = sc2.number_input(
        "Fixed Odds (winner points)",
        min_value=0.1, max_value=100.0,
        value=2.0, step=0.5,
        key="sf_odds",
        disabled=(scoring_mode == "ratio"),
        help="Points awarded to correct pickers. Losers get 1 pt."
    )
    poll_mode = sc3.selectbox(
        "Poll Mode",
        ["closed", "open"],
        format_func=lambda x: "🔒 Closed (votes hidden till end)"
                               if x == "closed" else "👁 Open (votes always visible)",
        key="sf_poll"
    )

    # Scoring explanation
    if scoring_mode == "ratio":
        st.info(
            "**Ratio mode:**  "
            "Winner pts = (loser votes ÷ winner votes) + (penalty pool ÷ winner votes).  "
            "Loser = **−1 pt**.  "
            "Penalised missed voters contribute to winner bonus pool."
        )
    else:
        st.info(
            f"**Fixed mode:**  "
            f"Every correct picker gets **+{fixed_odds} pts** (flat).  "
            f"Every incorrect picker loses **−1 pt**.  "
            "Penalised missed voters lose penalty pts → goes to bank fund "
            "(not distributed to winners)."
        )

    try:
        utc = get_match_cutoff_utc({"match_date": str(m_date),
                                     "start_time": s_time.strftime("%H:%M"),
                                     "timezone": tz})
        st.caption(f"Voting closes: **{utc.strftime('%d %b %Y %H:%M UTC')}**")
    except Exception:
        pass

    if st.button("Add Match", type="primary", key="sf_submit"):
        if not match_id or not title:
            st.error("ID and Title required.")
        else:
            valid, err = _validate_options(options)
            if not valid:
                st.error(err)
            else:
                create_match({
                    "match_id"     : match_id,
                    "tournament_id": tid,
                    "title"        : title,
                    "location"     : location,
                    "match_date"   : str(m_date),
                    "start_time"   : s_time.strftime("%H:%M"),
                    "timezone"     : tz,
                    "options"      : options,
                    "scoring_mode" : scoring_mode,
                    "fixed_odds"   : fixed_odds,
                    "poll_mode"    : poll_mode,
                    "created_by"   : user["name"],
                })
                st.success(f"Match `{match_id}` added!")
                st.rerun()


# ── Results ───────────────────────────────────────────────────────────────────

def _results_tab():
    ts = get_tournaments()
    if not ts: st.warning("No tournaments found."); return

    t_names = [t["name"] for t in ts]
    t_ids   = [t["tournament_id"] for t in ts]
    sel_n   = st.selectbox("Tournament", t_names, key="adm_r_t")
    sel_tid = t_ids[t_names.index(sel_n)]

    all_ms     = get_matches(sel_tid)
    if not all_ms: st.info("No matches yet."); return

    pending    = [m for m in all_ms if m["status"] != "completed" and not is_voting_open(m)]
    still_open = [m for m in all_ms if m["status"] != "completed" and is_voting_open(m)]
    done       = [m for m in all_ms if m["status"] == "completed"]

    if still_open:
        st.info(f"**{len(still_open)}** match(es) still have voting open — "
                "results cannot be entered until poll closes.")
        for m in still_open:
            scoring = m.get("scoring_mode","ratio")
            st.caption(f"⏳ `{m['match_id']}` — {m['title']} — "
                       f"closes {m['start_time']} {m['timezone'].split('/')[-1]} — "
                       f"scoring: {scoring}")

    st.subheader("Awaiting Result Entry")
    if not pending:
        st.caption("No matches awaiting result.")
    else:
        for m in pending:
            opts = [o.strip() for o in m["options"].split("|") if o.strip()]
            scoring = m.get("scoring_mode","ratio")
            odds    = m.get("fixed_odds","")
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 2])
                c1.markdown(f"**{m['title']}**")
                c1.caption(
                    f"`{m['match_id']}`  ·  {m['match_date']} {m['start_time']}  ·  "
                    f"Scoring: **{scoring}**"
                    + (f" @ {odds} pts" if scoring == "fixed" else "")
                )
                winner = c2.selectbox("Winner / Result", opts,
                                       key=f"r_{m['match_id']}")
                if c3.button("Save Result", key=f"rb_{m['match_id']}",
                              type="primary"):
                    with st.spinner("Calculating points..."):
                        update_match_result(m["match_id"], winner)
                        records = run_points_calculation(
                            m["match_id"], sel_tid, winner)
                    correct = sum(1 for r in records if r.get("total_points",0) > 0)
                    st.success(f"**{winner}** won — {correct} correct voter(s) awarded points")
                    st.rerun()

    if done:
        st.markdown("---")
        st.subheader("Update / Correct Result")
        st.caption("Changing result recalculates all points.")
        for m in done:
            opts    = [o.strip() for o in m["options"].split("|") if o.strip()]
            cur_idx = opts.index(m["result"]) if m["result"] in opts else 0
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 2])
                c1.markdown(f"**{m['title']}**")
                c1.caption(f"`{m['match_id']}`  ·  Result: **{m['result']}**  ·  "
                           f"Scoring: **{m.get('scoring_mode','ratio')}**")
                new_w = c2.selectbox("Change to", opts, index=cur_idx,
                                      key=f"corr_{m['match_id']}")
                if c3.button("Update Result", key=f"corrb_{m['match_id']}",
                              type="primary", disabled=(new_w == m["result"])):
                    with st.spinner("Recalculating..."):
                        update_match_result(m["match_id"], new_w)
                        run_points_calculation(m["match_id"], sel_tid, new_w)
                    st.success(f"Updated to **{new_w}** — points recalculated.")
                    st.rerun()
