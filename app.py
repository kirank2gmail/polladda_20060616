"""
app.py
SportsPoll — no auth version.
User picks their name from a list (or creates one).
Admin access via a simple toggle for users with role=admin.
"""

import streamlit as st

st.set_page_config(
    page_title = "SportsPoll 🏆",
    page_icon  = "🏆",
    layout     = "wide",
    initial_sidebar_state = "collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Syne:wght@700;800&family=DM+Sans:wght@300;400;500&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
h1, h2, h3 { font-family: 'Syne', sans-serif !important; font-weight: 700 !important; }
.stButton > button { border-radius: 8px; }
.block-container { padding-top: 1.5rem; max-width: 1100px; }
</style>
""", unsafe_allow_html=True)

from data.store import (
    get_all_users, get_or_create_user, create_user
)


# ── Session defaults ──────────────────────────────────────────────────────────
if "page"     not in st.session_state:
    st.session_state["page"]     = "home"
if "user"     not in st.session_state:
    st.session_state["user"]     = None
if "match_id" not in st.session_state:
    st.session_state["match_id"] = None


# ── Not logged in — show user picker ─────────────────────────────────────────
if not st.session_state["user"]:
    _show_user_picker()
    st.stop()


# ── Logged in — show navbar + route ──────────────────────────────────────────
user = st.session_state["user"]
_render_navbar(user)
_route(user)


# ─────────────────────────────────────────────────────────────────────────────

def _show_user_picker():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown(
            "<h1 style='text-align:center;font-size:3rem;'>🏆 SportsPoll</h1>",
            unsafe_allow_html=True
        )
        st.markdown(
            "<p style='text-align:center;color:#888;font-size:1.1rem;'>"
            "Predict. Compete. Win.</p>",
            unsafe_allow_html=True
        )
        st.markdown("<br>", unsafe_allow_html=True)

        users     = get_all_users()
        names     = [u["name"] for u in users]

        tab_exist, tab_new = st.tabs(["Sign In", "New User"])

        with tab_exist:
            if not names:
                st.info("No users yet — create one in the New User tab.")
            else:
                chosen = st.selectbox("Select your name", names)
                if st.button("Continue →", type="primary",
                             use_container_width=True):
                    user = next(u for u in users if u["name"] == chosen)
                    st.session_state["user"] = user
                    st.rerun()

        with tab_new:
            new_name = st.text_input("Your name", placeholder="Enter your name")
            is_admin = st.checkbox("Admin access")
            if st.button("Create & Continue", type="primary",
                         use_container_width=True):
                if not new_name.strip():
                    st.error("Name cannot be empty.")
                elif new_name.strip() in names:
                    st.error("Name already taken — sign in instead.")
                else:
                    role = "admin" if is_admin else "user"
                    user = create_user(new_name.strip(), role)
                    st.session_state["user"] = user
                    st.rerun()


def _render_navbar(user: dict):
    c1, c2, c3 = st.columns([2, 5, 3])

    with c1:
        if st.button("🏆 SportsPoll"):
            st.session_state["page"] = "home"
            st.rerun()

    with c2:
        b1, b2, b3 = st.columns(3)
        if b1.button("🏠 Home"):
            st.session_state["page"] = "home"
            st.rerun()
        if b2.button("🏅 Leaderboard"):
            st.session_state["page"] = "leaderboard"
            st.rerun()
        if user.get("role") == "admin":
            if b3.button("⚙️ Admin"):
                st.session_state["page"] = "admin"
                st.rerun()

    with c3:
        st.caption(f"👤 **{user['name']}**  ({user['role']})")
        if st.button("Switch User"):
            st.session_state["user"] = None
            st.session_state["page"] = "home"
            st.rerun()

    st.markdown("---")


def _route(user: dict):
    page = st.session_state.get("page", "home")

    if page == "home":
        from pages.home        import show_home
        show_home(user)

    elif page == "match":
        mid = st.session_state.get("match_id")
        if mid:
            from pages.match   import show_match
            show_match(user, mid)
        else:
            st.session_state["page"] = "home"
            st.rerun()

    elif page == "leaderboard":
        from pages.leaderboard import show_leaderboard
        show_leaderboard(user)

    elif page == "admin":
        if user.get("role") != "admin":
            st.error("Admin access only.")
        else:
            from admin.dashboard import show_admin
            show_admin(user)

    else:
        from pages.home        import show_home
        show_home(user)
