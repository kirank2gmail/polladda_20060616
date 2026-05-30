"""
app.py — SportsPoll
Navbar selectbox does NOT override page set by buttons.
Key fix: only navigate when user explicitly changes the dropdown.
"""

import streamlit as st

st.set_page_config(
    page_title="SportsPoll 🏆",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'Syne', sans-serif !important; font-weight: 700 !important; }
header[data-testid="stHeader"] { display: none !important; }
#MainMenu { display: none !important; }
footer    { display: none !important; }
.block-container { padding-top: 0.5rem !important; max-width: 1100px; }
div[data-testid="stHorizontalBlock"]:first-of-type {
    background: #0e1117;
    border-bottom: 1px solid #2a2d35;
    padding: 6px 4px;
    position: sticky;
    top: 0;
    z-index: 999;
}
</style>
""", unsafe_allow_html=True)

from data.db import (
    get_all_users, get_user_by_name, get_user_by_id,
    verify_password, change_password, admin_exists,
    create_user, get_display_name, update_nickname,
    update_user_timezone
)
from utils.timezone import COMMON_TIMEZONES
import pytz

# ── Session defaults ──────────────────────────────────────────────────────────
for k, v in [("user", None), ("page", "home"), ("page", "home"),
             ("match_id", None), ("tournament_id", None),
             ("_last_nav", "home")]:
    if k not in st.session_state:
        st.session_state[k] = v


# ── Navbar ────────────────────────────────────────────────────────────────────

def render_navbar(user: dict):
    is_admin = user.get("role") == "admin"
    nick     = get_display_name(user["user_id"])
    cur_page = st.session_state.get("page", "home")

    # Map page keys to display labels
    page_map = {
        "home"       : "🏠  Home",
        "leaderboard": "🏅  Leaderboard",
        "profile"    : "👤  Profile",
    }
    if is_admin:
        page_map["admin"] = "⚙️  Admin"

    labels    = list(page_map.values())
    keys      = list(page_map.keys())

    # Current label — fall back to Home if page not in map (e.g. "match")
    cur_label = page_map.get(cur_page, "🏠  Home")
    cur_idx   = labels.index(cur_label)

    # Render navbar row
    c_brand, c_nav, c_nick, c_out = st.columns([1, 6, 3, 2])

    c_brand.markdown(
        "<div style='padding-top:6px;font-weight:800;font-size:1.1rem;'>🏆</div>",
        unsafe_allow_html=True
    )

    with c_nav:
        chosen_label = st.selectbox(
            "nav",
            options=labels,
            index=cur_idx,
            label_visibility="collapsed",
            key="navbar_select",
        )

    c_nick.markdown(
        f"<div style='padding-top:8px;font-size:0.85rem;"
        f"color:#ccc;overflow:hidden;text-overflow:ellipsis;"
        f"white-space:nowrap;'>👤 {nick}</div>",
        unsafe_allow_html=True
    )

    if c_out.button("Sign Out", use_container_width=True, key="signout_btn"):
        for k in ("user", "page", "match_id", "tournament_id", "_last_nav"):
            st.session_state[k] = None if k == "user" else "home"
        st.rerun()

    # ── Only navigate if user actually changed the dropdown ──────────────────
    chosen_page = keys[labels.index(chosen_label)]

    # _last_nav tracks what the navbar was last set to.
    # Only act if the dropdown changed FROM the last nav state.
    # This prevents the navbar from overriding button-triggered navigation.
    last_nav = st.session_state.get("_last_nav", cur_page)

    if chosen_page != last_nav:
        # User moved the dropdown — honour it
        st.session_state["_last_nav"] = chosen_page
        st.session_state["page"]      = chosen_page
        st.session_state["match_id"]  = None
        st.rerun()
    else:
        # Keep _last_nav in sync with current page for non-match pages
        if cur_page in page_map:
            st.session_state["_last_nav"] = cur_page


# ── Login ─────────────────────────────────────────────────────────────────────

def show_login():
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown(
            "<h1 style='text-align:center;font-size:3rem;'>🏆 SportsPoll</h1>",
            unsafe_allow_html=True)
        st.markdown(
            "<p style='text-align:center;color:#888;'>"
            "Predict · Compete · Win</p>",
            unsafe_allow_html=True)
        st.markdown("<br>", unsafe_allow_html=True)

        if not admin_exists():
            st.info("No admin yet. Create the first admin account.")
            with st.form("first_admin"):
                uname = st.text_input("Admin username")
                pw1   = st.text_input("Password (min 6 chars)", type="password")
                pw2   = st.text_input("Confirm password",       type="password")
                if st.form_submit_button("Create Admin", type="primary",
                                         use_container_width=True):
                    if not uname.strip():
                        st.error("Username required.")
                    elif len(pw1) < 6:
                        st.error("Min 6 characters required.")
                    elif pw1 != pw2:
                        st.error("Passwords do not match.")
                    else:
                        u = create_user(uname.strip(), pw1,
                                        role="admin", created_by="system")
                        change_password(u["user_id"], pw1)
                        st.success("Admin created — sign in below.")
                        st.rerun()
            return

        users = get_all_users()
        names = [u["name"] for u in users]
        if not names:
            st.warning("No users exist. Contact admin.")
            return

        with st.form("login"):
            username = st.selectbox("Username", names)
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Sign In", type="primary",
                                     use_container_width=True):
                u = get_user_by_name(username)
                if u and verify_password(u["user_id"], password):
                    st.session_state["user"]      = u
                    st.session_state["page"]      = "home"
                    st.session_state["_last_nav"] = "home"
                    st.rerun()
                else:
                    st.error("Incorrect password.")


# ── Force password change ─────────────────────────────────────────────────────

def show_change_password(user: dict):
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.title("🔑 Set Your Password")
        st.info("You must set a new password before continuing.")
        with st.form("change_pw"):
            pw1 = st.text_input("New password (min 6 chars)", type="password")
            pw2 = st.text_input("Confirm new password",       type="password")
            if st.form_submit_button("Set Password", type="primary",
                                     use_container_width=True):
                if len(pw1) < 6:
                    st.error("Min 6 characters required.")
                elif pw1 != pw2:
                    st.error("Passwords do not match.")
                else:
                    change_password(user["user_id"], pw1)
                    st.session_state["user"] = get_user_by_id(user["user_id"])
                    st.success("Password set!")
                    st.rerun()


# ── Profile ───────────────────────────────────────────────────────────────────

def show_profile(user: dict):
    st.title("👤 My Profile")
    uid  = user["user_id"]
    nick = get_display_name(uid)

    with st.container(border=True):
        st.subheader("Nickname")
        st.caption(
            "Shown on leaderboard and results instead of your username. "
            f"Current: **{nick}**"
        )
        c1, c2 = st.columns([3, 1])
        new_nick = c1.text_input("Nickname", value=nick,
                                  label_visibility="collapsed")
        if c2.button("Save", use_container_width=True,
                     type="primary", key="save_nick"):
            if new_nick.strip():
                update_nickname(uid, new_nick.strip())
                st.success("Nickname saved!")
                st.rerun()
            else:
                st.error("Nickname cannot be empty.")

    with st.container(border=True):
        st.subheader("Change Password")
        with st.form("pw_form"):
            old = st.text_input("Current password",     type="password")
            n1  = st.text_input("New password (min 6)", type="password")
            n2  = st.text_input("Confirm new password", type="password")
            if st.form_submit_button("Update Password", type="primary"):
                if not verify_password(uid, old):
                    st.error("Current password is incorrect.")
                elif len(n1) < 6:
                    st.error("Min 6 characters required.")
                elif n1 != n2:
                    st.error("Passwords do not match.")
                else:
                    change_password(uid, n1)
                    st.success("Password updated!")

    with st.container(border=True):
        st.subheader("Timezone")
        all_tz  = COMMON_TIMEZONES + [
            t for t in pytz.all_timezones if t not in COMMON_TIMEZONES
        ]
        cur_tz  = (get_user_by_id(uid) or {}).get("timezone", "Asia/Kolkata")
        cur_idx = all_tz.index(cur_tz) if cur_tz in all_tz else 0
        new_tz  = st.selectbox("Your Timezone", all_tz, index=cur_idx)
        if st.button("Save Timezone", type="primary", key="save_tz"):
            update_user_timezone(uid, new_tz)
            st.success(f"Timezone set to {new_tz}")


# ── Router ────────────────────────────────────────────────────────────────────

def route(user: dict):
    page = st.session_state.get("page", "home")

    if page == "home":
        from pages.home import show_home
        show_home(user)

    elif page == "match":
        mid = st.session_state.get("match_id")
        if mid:
            from pages.match import show_match
            show_match(user, mid)
        else:
            st.session_state["page"] = "home"
            st.rerun()

    elif page == "leaderboard":
        from pages.leaderboard import show_leaderboard
        show_leaderboard(user)

    elif page == "profile":
        show_profile(user)

    elif page == "admin":
        if user.get("role") != "admin":
            st.error("Admin access only.")
        else:
            from admin.dashboard import show_admin
            show_admin(user)

    else:
        from pages.home import show_home
        show_home(user)


# ── Main ──────────────────────────────────────────────────────────────────────

user = st.session_state.get("user")

if not user:
    show_login()
    st.stop()

if user.get("must_change_password"):
    show_change_password(user)
    st.stop()

render_navbar(user)
route(user)
