"""
app.py — SportsPoll
Fixed top navbar (selectbox). Password login with plain text username input.
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
</style>
""", unsafe_allow_html=True)

from data.db import (
    get_all_users, get_user_by_name, get_user_by_id,
    verify_password, change_password, admin_exists,
    create_user, get_display_name, update_nickname,
    update_user_timezone, is_legacy_password
)
from utils.timezone import COMMON_TIMEZONES
import streamlit_authenticator as stauth
from data.activity_log import log_login
import pytz

for k, v in [("user", None), ("page", "home"),
             ("match_id", None), ("tournament_id", None),
             ("_last_nav", "home")]:
    if k not in st.session_state:
        st.session_state[k] = v


# ── Navbar ────────────────────────────────────────────────────────────────────

def render_navbar(user: dict):
    is_admin = user.get("role") == "admin"
    nick     = get_display_name(user["user_id"])
    cur_page = st.session_state.get("page", "home")

    page_map = {
        "home"       : "🏠  Home",
        "leaderboard": "🏅  Leaderboard",
        "profile"    : "👤  Profile",
    }
    if is_admin:
        page_map["admin"] = "⚙️  Admin"

    labels   = list(page_map.values())
    keys     = list(page_map.keys())
    cur_label = page_map.get(cur_page, "🏠  Home")
    cur_idx   = labels.index(cur_label)

    c_brand, c_nav, c_nick, c_out = st.columns([1, 6, 3, 2])
    c_brand.markdown(
        "<div style='padding-top:6px;font-weight:800;font-size:1.1rem;'>🏆</div>",
        unsafe_allow_html=True)

    with c_nav:
        chosen_label = st.selectbox(
            "nav", options=labels, index=cur_idx,
            label_visibility="collapsed", key="navbar_select")

    c_nick.markdown(
        f"<div style='padding-top:8px;font-size:0.85rem;color:#ccc;"
        f"overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'>"
        f"👤 {nick}</div>", unsafe_allow_html=True)

    if c_out.button("Sign Out", use_container_width=True, key="signout_btn"):
        auth = st.session_state.get("_authenticator")
        if auth:
            try: auth.logout()
            except Exception: pass
        for k in ("user","page","match_id","tournament_id","_last_nav"):
            st.session_state[k] = None if k == "user" else "home"
        st.rerun()

    st.markdown("---")

    chosen_page = keys[labels.index(chosen_label)]

    # _last_nav tracks what the navbar dropdown was last explicitly set to.
    # Only navigate when the user actually moves the dropdown.
    # Button navigations (match, leaderboard, etc.) set both page AND
    # _last_nav themselves, so the navbar leaves them undisturbed.
    last_nav = st.session_state.get("_last_nav", "home")

    if chosen_page != last_nav:
        # User moved the dropdown — honour it
        st.session_state["_last_nav"] = chosen_page
        st.session_state["page"]      = chosen_page
        st.session_state["match_id"]  = None
        st.rerun()
    # else: dropdown matches last user selection — do nothing,
    # allow any page set by buttons to render undisturbed


# ── Login ─────────────────────────────────────────────────────────────────────

def _build_authenticator():
    """
    Build stauth.Authenticate from GCS users.
    Key = user name (lowercased) — what they type to login.
    """
    users = get_all_users()
    credentials = {
        "usernames": {
            u["name"].strip().lower(): {
                "name"    : u.get("name", ""),
                "password": u.get("password_hash", ""),
            }
            for u in users
        }
    }
    cfg         = st.secrets.get("auth", {})
    cookie_name = cfg.get("cookie_name", "sportspoll_auth")
    cookie_key  = cfg.get("cookie_key",  "sportspoll-secret-key-change-me")
    expiry_days = int(cfg.get("cookie_expiry_days", 7))

    import inspect
    sig = inspect.signature(stauth.Authenticate.__init__)
    if "cookie_key" in sig.parameters:
        return stauth.Authenticate(credentials, cookie_name,
                                   cookie_key=cookie_key,
                                   cookie_expiry_days=expiry_days)
    else:
        return stauth.Authenticate(credentials, cookie_name, cookie_key,
                                   expiry_days)


def show_login():
    # ── Full-page login styling ──────────────────────────────────────────────
    st.markdown("""
    <style>
    /* Hide authenticator's default "Login" header */
    [data-testid="stForm"] h1,
    [data-testid="stForm"] h2 { display: none !important; }

    /* Card styling */
    .login-card {
        background: #1a1f2e;
        border: 1px solid #2d3548;
        border-radius: 16px;
        padding: 2.5rem 2rem;
        margin-top: 2rem;
    }

    /* Style the authenticator's input fields */
    [data-testid="stForm"] input {
        background: #242938 !important;
        border: 1px solid #3d4560 !important;
        border-radius: 8px !important;
        color: #fff !important;
        font-size: 1rem !important;
        padding: 0.6rem 1rem !important;
    }
    [data-testid="stForm"] input:focus {
        border-color: #4f6ef7 !important;
        box-shadow: 0 0 0 2px rgba(79,110,247,0.25) !important;
    }

    /* Style the Sign In button */
    [data-testid="stForm"] [data-testid="stFormSubmitButton"] button {
        background: linear-gradient(135deg, #4f6ef7, #7c3aed) !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-size: 1rem !important;
        font-weight: 600 !important;
        padding: 0.6rem !important;
        width: 100% !important;
        margin-top: 0.5rem !important;
        transition: opacity 0.2s !important;
    }
    [data-testid="stForm"] [data-testid="stFormSubmitButton"] button:hover {
        opacity: 0.9 !important;
    }

    /* Label styling */
    [data-testid="stForm"] label {
        color: #9aa3b8 !important;
        font-size: 0.85rem !important;
        font-weight: 500 !important;
        letter-spacing: 0.03em !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # ── Centred layout ───────────────────────────────────────────────────────
    _, col, _ = st.columns([1, 2, 1])
    with col:
        # Logo / hero
        st.markdown("""
        <div style="text-align:center; padding: 2rem 0 1rem;">
            <div style="font-size:3.5rem; margin-bottom:0.5rem;">🏆</div>
            <h1 style="font-family:'Syne',sans-serif; font-size:2.4rem;
                       font-weight:800; color:#fff; margin:0;">SportsPoll</h1>
            <p style="color:#6b7a99; font-size:1rem; margin:0.4rem 0 0;">
                Predict &nbsp;·&nbsp; Compete &nbsp;·&nbsp; Win
            </p>
        </div>
        """, unsafe_allow_html=True)

        # First run — create first admin
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

        st.markdown("<div style='height:0.5rem'></div>", unsafe_allow_html=True)

    # Authenticator login — rendered full-width inside centred column
    _, col2, _ = st.columns([1, 2, 1])
    with col2:
        authenticator = _build_authenticator()
        st.session_state["_authenticator"] = authenticator
        authenticator.login(
            location="main",
            fields={
                "Form name": "",
                "Username" : "Username",
                "Password" : "Password",
                "Login"    : "Sign In",
            }
        )
        if st.session_state.get("authentication_status") is False:
            st.error("Username or password is incorrect.")
        elif st.session_state.get("authentication_status"):
            username = st.session_state.get("username", "")
            u = get_user_by_name(username)
            if u:
                st.session_state["user"]      = u
                st.session_state["page"]      = "home"
                st.session_state["_last_nav"] = "home"
                log_login(u["user_id"])
                st.rerun()

        st.markdown("""
        <p style="text-align:center; color:#4a5270; font-size:0.8rem;
                  margin-top:1.5rem;">
            Your session stays active for 7 days after login.
        </p>
        """, unsafe_allow_html=True)


# ── Force password change ─────────────────────────────────────────────────────

def show_change_password(user: dict):
    _, col, _ = st.columns([1, 2, 1])
    with col:
        st.title("🔑 Set Your Password")
        if st.session_state.get("_legacy_pw_reset"):
            st.warning("We've upgraded our password security. Please set a new password to continue.")
        else:
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
        st.caption(f"Shown on leaderboard and results. Current: **{nick}**")
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
            st.session_state["page"] = "home"; st.rerun()
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
    # Build authenticator once — it reads its own cookie and populates
    # st.session_state["authentication_status"] and st.session_state["username"]
    # WITHOUT rendering a visible widget (we pass it to show_login if needed).
    # Calling login(location="unrendered") a second time causes duplicate key errors,
    # so we only build it here and let show_login() call login() once.
    if admin_exists():
        try:
            authenticator = _build_authenticator()
            st.session_state["_authenticator"] = authenticator
            # Check if authenticator already has a valid cookie session
            # (set by a previous login — stored in st.session_state by the library)
            auth_status = st.session_state.get("authentication_status")
            username    = st.session_state.get("username", "")
            if auth_status and username:
                u = get_user_by_name(username)
                if u:
                    st.session_state["user"]      = u
                    st.session_state["page"]      = "home"
                    st.session_state["_last_nav"] = "home"
                    user = u
        except Exception:
            pass

if not user:
    show_login()
    st.stop()

if user.get("must_change_password") or is_legacy_password(user["user_id"]):
    if not user.get("must_change_password"):
        st.session_state["_legacy_pw_reset"] = True
    show_change_password(user)
    st.stop()

render_navbar(user)
route(user)
