"""
app.py — SportsPoll
No auth version. User picks name from list or creates one.
Navigation as fixed dropdown selectbox at top.
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

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
}
h1, h2, h3 {
    font-family: 'Syne', sans-serif !important;
    font-weight: 700 !important;
}
.block-container {
    padding-top: 1rem;
    max-width: 1100px;
}

/* Hide sidebar */
[data-testid="stSidebar"] {
    display: none;
}

/* Fixed navbar */
[data-testid="stVerticalBlockBorderWrapper"]:has(> [data-testid="stHorizontalBlock"]) {
    position: sticky;
    top: 0;
    background: white;
    z-index: 999;
    padding: 0.5rem 0;
    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}
</style>
""", unsafe_allow_html=True)

from data.db import get_all_users, create_user

# ── Session defaults ──────────────────────────────────────────────────────────
for key, val in [("page","home"), ("user",None), ("match_id",None), ("tournament_id",None)]:
    if key not in st.session_state:
        st.session_state[key] = val


# ── Functions ────────────────────────────────────────────────────────────[...]

def show_user_picker():
    _, col, _ = st.columns([1, 2, 1])
    with col:
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

        users = get_all_users()
        names = [u["name"] for u in users]

        tab_exist, tab_new = st.tabs(["Sign In", "New User"])

        with tab_exist:
            if not names:
                st.info("No users yet — create one in the New User tab.")
            else:
                chosen = st.selectbox("Select your name", names)
                if st.button("Continue →", type="primary", use_container_width=True):
                    user = next(u for u in users if u["name"] == chosen)
                    st.session_state["user"] = user
                    st.rerun()

        with tab_new:
            new_name = st.text_input("Your name", placeholder="Enter your name")
            is_admin = st.checkbox("Admin access")
            if st.button("Create & Continue", type="primary", use_container_width=True):
                if not new_name.strip():
                    st.error("Name cannot be empty.")
                elif new_name.strip() in names:
                    st.error("Name already taken — sign in instead.")
                else:
                    role     = "admin" if is_admin else "user"
                    new_user = create_user(new_name.strip(), role)
                    st.session_state["user"] = new_user
                    st.rerun()


def render_navbar(user: dict):
    is_admin = user.get("role") == "admin"

    # Build nav items dynamically
    nav_items = [
        ("🏆 Home",        "home"),
        ("🏅 Leaderboard", "leaderboard"),
    ]
    if is_admin:
        nav_items.append(("⚙️ Admin", "admin"))

    # Create columns: nav dropdown + user info + switch button
    col1, col2 = st.columns([2, 3])

    with col1:
        # Dropdown navigation
        nav_labels = [label for label, _ in nav_items]
        nav_pages = [page for _, page in nav_items]
        current_index = nav_pages.index(st.session_state["page"]) if st.session_state["page"] in nav_pages else 0
        
        selected = st.selectbox(
            "Navigate",
            options=nav_labels,
            index=current_index,
            key="nav_dropdown"
        )
        
        selected_page = nav_pages[nav_labels.index(selected)]
        if selected_page != st.session_state["page"]:
            st.session_state["page"] = selected_page
            st.rerun()

    with col2:
        col_user, col_switch = st.columns([1.5, 1])
        with col_user:
            st.caption(f"👤 **{user['name']}**")
        with col_switch:
            if st.button("Switch User", use_container_width=True, key="switch_user"):
                st.session_state["user"]     = None
                st.session_state["page"]     = "home"
                st.session_state["match_id"] = None
                st.rerun()

    st.markdown("---")


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

    elif page == "admin":
        if user.get("role") != "admin":
            st.error("Admin access only.")
        else:
            from admin.dashboard import show_admin
            show_admin(user)

    else:
        from pages.home import show_home
        show_home(user)


# ── Main ────────────────────────────────────────────────────────────[...]

if not st.session_state["user"]:
    show_user_picker()
    st.stop()

user = st.session_state["user"]
render_navbar(user)
route(user)
