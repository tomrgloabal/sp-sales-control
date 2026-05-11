import streamlit as st
from auth import require_login, current_user

st.set_page_config(
    page_title="SP Sales Control | Arbitrage Global",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global RTL CSS ────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Heebo:wght@300;400;600;700&display=swap');

html, body, [class*="css"] { font-family: 'Heebo', sans-serif !important; }

.stApp { direction: rtl; }
section[data-testid="stSidebar"] { direction: rtl; }
.stTextInput input, .stTextArea textarea,
.stSelectbox div[data-baseweb="select"] { direction: rtl; text-align: right; }
table { direction: rtl; }
th, td { text-align: right !important; }

/* Sidebar styling — Arbitrage Global brand */
section[data-testid="stSidebar"] > div:first-child {
    background: linear-gradient(180deg, #003327 0%, #005059 100%);
}
section[data-testid="stSidebar"] .stMarkdown p,
section[data-testid="stSidebar"] label { color: #fff !important; }

/* Cards */
.kpi-card {
    background: #fff;
    border-radius: 12px;
    padding: 1.2rem 1.5rem;
    box-shadow: 0 2px 12px rgba(0,51,39,.1);
    border-right: 4px solid #FFC300;
    margin-bottom: .75rem;
}
.kpi-value { font-size: 2rem; font-weight: 700; color: #003327; }
.kpi-label { font-size: .85rem; color: #666; margin-top: .2rem; }

/* Stage badges */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: .8rem;
    font-weight: 600;
}
.badge-high  { background:#C6EFCE; color:#003327; }
.badge-mid   { background:#FFF2CC; color:#7B5200; }
.badge-low   { background:#FDEBD0; color:#C55A11; }
.badge-done  { background:#C6EFCE; color:#003327; }
.badge-stage { background:rgba(255,195,0,.18); color:#003327; }

/* Hide Streamlit default header */
header[data-testid="stHeader"] { display:none; }
</style>
""", unsafe_allow_html=True)

require_login()

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
    <div style='padding:1rem 0 .5rem; text-align:center;'>
      <div style='font-size:1.3rem; font-weight:700; color:#FFC300;'>Arbitrage Global</div>
      <div style='font-size:.85rem; color:#FFD235; margin-top:.2rem;'>SP Sales Control</div>
    </div>
    <hr style='border-color:rgba(255,195,0,.3); margin:.5rem 0 1rem;'>
    <div style='color:#FFD235; font-size:.85rem; padding:.25rem 0;'>
      👤 שלום, <strong style='color:#fff;'>{current_user()}</strong>
    </div>
    <hr style='border-color:rgba(255,195,0,.3); margin:.75rem 0;'>
    """, unsafe_allow_html=True)

    if st.button("יציאה", use_container_width=True):
        st.session_state.clear()
        st.rerun()

# ── Home page (redirect hint) ─────────────────────────────────────────────────
st.markdown("""
<div style='text-align:right; padding:2rem 0 1rem;'>
  <h1 style='color:#003327; font-size:2rem; margin-bottom:.5rem;'>SP Sales Control</h1>
  <p style='color:#555; font-size:1.05rem;'>בחר דף מהתפריט הצדדי כדי להתחיל</p>
</div>
""", unsafe_allow_html=True)

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown("""<div class='kpi-card'>
      <div class='kpi-label'>📊 דשבורד</div>
      <div style='color:#555; font-size:.9rem; margin-top:.5rem;'>סיכום גיוס, פייפליין ושלבי מכירה</div>
    </div>""", unsafe_allow_html=True)
with col2:
    st.markdown("""<div class='kpi-card'>
      <div class='kpi-label'>📋 פייפליין</div>
      <div style='color:#555; font-size:.9rem; margin-top:.5rem;'>ניהול מאגר לקוחות לפני פתיחת פקדון</div>
    </div>""", unsafe_allow_html=True)
with col3:
    st.markdown("""<div class='kpi-card'>
      <div class='kpi-label'>💼 מעקב מכירות</div>
      <div style='color:#555; font-size:.9rem; margin-top:.5rem;'>מעקב 7 שלבי תהליך המכירה</div>
    </div>""", unsafe_allow_html=True)
