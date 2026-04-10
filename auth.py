import streamlit as st
from config import USER_KEYS


def login_page():
    st.markdown("""
    <style>
    .stApp { direction: rtl; }
    .login-wrap { max-width:400px; margin:80px auto; padding:2.5rem;
                  background:#fff; border-radius:14px;
                  box-shadow:0 4px 28px rgba(30,39,97,.15); direction:rtl; }
    .login-logo { color:#1E2761; font-size:1.6rem; font-weight:700; margin-bottom:.2rem; }
    .login-sub  { color:#666; font-size:.95rem; margin-bottom:1.8rem; }
    header[data-testid="stHeader"] { display:none; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="login-wrap">
      <div class="login-logo">Arbitrage Global</div>
      <div class="login-sub">SP Sales Control — כניסה לשותפים</div>
    </div>
    """, unsafe_allow_html=True)

    with st.form("login_form"):
        username = st.selectbox("בחר שם שותף", USER_KEYS)
        submitted = st.form_submit_button("כניסה →", use_container_width=True, type="primary")

    if submitted:
        st.session_state["logged_in"] = True
        st.session_state["user"] = username
        st.rerun()


def require_login():
    if not st.session_state.get("logged_in"):
        login_page()
        st.stop()


def current_user() -> str:
    return st.session_state.get("user", "לא ידוע")
