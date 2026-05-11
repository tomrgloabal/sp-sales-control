import json
import streamlit as st
import pandas as pd
from datetime import date
from pathlib import Path
from auth import require_login, current_user
from sheets import read_df, write_df, log_action
from config import SALES_STAGES

INV_FILE = Path(__file__).parent.parent / "local_data" / "ProductInvestors.json"

def _archive_product_sales(isin: str, prod_row, sales_df: pd.DataFrame):
    """Copy closed product + its Sales rows into ProductInvestors.json."""
    archive = {}
    if INV_FILE.exists():
        try:
            archive = json.loads(INV_FILE.read_text(encoding="utf-8"))
        except Exception:
            archive = {}

    # Sales for this ISIN
    investors = []
    if not sales_df.empty and "ISIN פקדון" in sales_df.columns:
        subset = sales_df[sales_df["ISIN פקדון"].astype(str).str.strip() == isin]
        for _, r in subset.iterrows():
            investors.append({
                "שם המשקיע": str(r.get("שם לקוח", "")),
                "סכום":      float(str(r.get("סכום", 0) or 0).replace(",", "") or 0),
                "מטבע":      str(r.get("מטבע", "ILS")),
                "שותף":      str(r.get("דרך נציג", "")),
                "בנק":       str(r.get("בנק", "")),
                "סטטוס":     str(r.get("שלב", "")),
            })

    issuer   = str(prod_row.get("מנפיק", ""))
    prod_name = f"{issuer} | {prod_row.get('נכסי בסיס', '')} | {prod_row.get('קופון שנתי', '')}%"
    archive[isin] = {
        "שם מלא":    prod_name.strip(" |"),
        "מנפיק":     issuer,
        "ISSUE DATE": str(prod_row.get("תאריך סגירת גיוס", "") or date.today().strftime("%Y-%m-%d")),
        "משקיעים":   investors,
    }
    INV_FILE.write_text(json.dumps(archive, ensure_ascii=False, indent=2), encoding="utf-8")

require_login()

st.markdown("""
<style>
.stApp { direction: rtl; }
.kpi-card { background:#fff; border-radius:12px; padding:1.2rem 1.5rem;
            box-shadow:0 2px 12px rgba(30,39,97,.1); border-right:4px solid #1E2761; }
.kpi-value { font-size:2rem; font-weight:700; color:#1E2761; }
.kpi-label { font-size:.85rem; color:#666; }
header[data-testid="stHeader"] { display:none; }
div[data-testid="stButton"] button { white-space:nowrap !important; }

/* Product row card */
.prod-card {
  background:#fff;
  border-radius:12px;
  padding:.85rem 1.2rem;
  box-shadow:0 2px 10px rgba(30,39,97,.09);
  border-right:5px solid #1E2761;
  display:flex;
  align-items:center;
  gap:1.5rem;
  margin-bottom:.5rem;
  flex-wrap:nowrap;
  direction:rtl;
}
.prod-field { display:flex; flex-direction:column; min-width:80px; }
.prod-field .lbl { font-size:.72rem; color:#888; margin-bottom:.1rem; white-space:nowrap; }
.prod-field .val { font-size:1rem; font-weight:700; color:#1E2761; white-space:nowrap; }
.prod-field .val.small { font-size:.82rem; }
.prod-sep { width:1px; height:36px; background:#e0e3ef; flex-shrink:0; }
</style>""", unsafe_allow_html=True)

st.markdown("<h2 style='color:#1E2761; direction:rtl;'>📊 דשבורד</h2>", unsafe_allow_html=True)

# ── Load data ─────────────────────────────────────────────────────────────────
products_df   = read_df("Products")
pipeline_df   = read_df("Pipeline")
sales_df      = read_df("Sales")
redemptions_df= read_df("Redemptions")

# ── Active products overview ─────────────────────────────────────────────────
st.markdown("### פקדונות פעילים")
if not products_df.empty and "ISIN" in products_df.columns:
    active = products_df[(products_df["סטטוס"] == "פעיל") & (products_df["ISIN"].str.strip() != "")].copy()
    if not active.empty:
        for row_i, row in active.iterrows():
            isin_val  = row.get("ISIN", "")
            issuer    = row.get("מנפיק", "—")
            currency  = row.get("מטבע", "—")
            size      = row.get("גודל עסקה", "—")
            _coupon_raw = str(row.get("קופון שנתי", "—"))
            coupon    = _coupon_raw if "%" in _coupon_raw or _coupon_raw == "—" else f"{_coupon_raw}%"
            duration  = row.get('מח"מ (חודשים)', "—")
            maturity  = row.get("תאריך פדיון", "—")
            barrier   = row.get("מחסום", "—")

            def _cell(label, value):
                return f"""
                <div style="display:flex;flex-direction:column;padding:.45rem .7rem;
                            border-left:1px solid #eaecf5;">
                  <span style="font-size:.68rem;color:#999;margin-bottom:2px;white-space:nowrap;">{label}</span>
                  <span style="font-size:.95rem;font-weight:700;color:#1E2761;word-break:break-word;">{value}</span>
                </div>"""

            card_col, btn_col = st.columns([11, 1])
            with card_col:
                st.markdown(f"""
                <div style="background:#fff;border-radius:12px;
                            box-shadow:0 2px 10px rgba(30,39,97,.09);
                            border-right:5px solid #1E2761;
                            display:grid;
                            grid-template-columns:repeat(4,1fr);
                            direction:rtl;margin-bottom:.6rem;overflow:hidden;">
                  {_cell("מנפיק", issuer)}
                  {_cell("ISIN", isin_val)}
                  {_cell("מטבע", currency)}
                  {_cell("גודל עסקה", size)}
                  {_cell("קופון שנתי", coupon)}
                  {_cell('מח"מ (חודשים)', f"{duration} ח'")}
                  {_cell("תאריך פדיון", maturity)}
                  {_cell("מחסום", barrier)}
                </div>
                """, unsafe_allow_html=True)
            with btn_col:
                st.markdown("<div style='padding-top:1.4rem'></div>", unsafe_allow_html=True)
                if st.button("🔒 סגור", key=f"close_{isin_val}", use_container_width=True):
                    st.session_state[f"_confirm_close_{isin_val}"] = True

            # Confirmation panel — appears below the card
            if st.session_state.get(f"_confirm_close_{isin_val}"):
                sales_for_isin = sales_df[sales_df["ISIN פקדון"].astype(str).str.strip() == isin_val] if not sales_df.empty and "ISIN פקדון" in sales_df.columns else pd.DataFrame()
                n_sales = len(sales_for_isin)
                st.warning(f"**סגירת פקדון {isin_val}** — נמצאו **{n_sales} מכירות** הקשורות לפקדון זה.")
                ca, cb, cc = st.columns(3)
                with ca:
                    if st.button("📦 סגור + העבר לארכיון", key=f"confirm_archive_{isin_val}", type="primary", use_container_width=True):
                        _archive_product_sales(isin_val, row, sales_df)
                        products_df.at[row_i, "סטטוס"] = "סגור"
                        write_df("Products", products_df)
                        log_action(current_user(), "סגירת פקדון + ארכוב", f"{isin_val} | {n_sales} מכירות")
                        st.session_state.pop(f"_confirm_close_{isin_val}", None)
                        st.rerun()
                with cb:
                    if st.button("🔒 סגור בלבד", key=f"confirm_close_only_{isin_val}", use_container_width=True):
                        products_df.at[row_i, "סטטוס"] = "סגור"
                        write_df("Products", products_df)
                        log_action(current_user(), "סגירת פקדון", isin_val)
                        st.session_state.pop(f"_confirm_close_{isin_val}", None)
                        st.rerun()
                with cc:
                    if st.button("ביטול", key=f"cancel_close_{isin_val}", use_container_width=True):
                        st.session_state.pop(f"_confirm_close_{isin_val}", None)
                        st.rerun()

    # Show closed products collapsible
    closed = products_df[(products_df["סטטוס"] == "סגור") & (products_df["ISIN"].str.strip() != "")].copy()
    if not closed.empty:
        with st.expander(f"📁 פקדונות סגורים ({len(closed)})", expanded=False):
            for row_i, row in closed.iterrows():
                isin_val = row.get("ISIN", "")
                cc1, cc2, cc3, cc4 = st.columns([2, 2.5, 2, 1])
                with cc1: st.write(f"**{row.get('מנפיק','—')}**")
                with cc2: st.write(isin_val)
                with cc3: st.write(f"{row.get('מטבע','—')} {row.get('גודל עסקה','—')}")
                with cc4:
                    if st.button("♻️ הפעל", key=f"reopen_{isin_val}", use_container_width=True):
                        products_df.at[row_i, "סטטוס"] = "פעיל"
                        write_df("Products", products_df)
                        log_action(current_user(), "פתיחת פקדון מחדש", isin_val)
                        st.rerun()
    if active.empty:
        st.info("אין פקדונות פעילים כרגע")
else:
    st.info("טרם הוזנו פקדונות — עבור לדף 'פרטי פקדון'")

st.divider()

# ── Fundraising progress ──────────────────────────────────────────────────────
st.markdown("### מצב גיוס")

def _to_float(v):
    try: return float(str(v).replace(",","").replace("'","").replace("₪","").replace("$","").replace("€","").strip() or 0)
    except: return 0.0

# Committed = sum of all ACTIVE products per currency
committed_by_cur = {"ILS": 0.0, "USD": 0.0, "EUR": 0.0}
if not products_df.empty and "סטטוס" in products_df.columns:
    act = products_df[products_df["סטטוס"] == "פעיל"]
    for cur in ["ILS", "USD", "EUR"]:
        sub = act[act["מטבע"] == cur] if "מטבע" in act.columns else pd.DataFrame()
        committed_by_cur[cur] = sum(_to_float(v) for v in sub.get("גודל עסקה", []))

# Raised = sales that reached "נכנס לפקדון"
raised_by_cur = {"ILS": 0.0, "USD": 0.0, "EUR": 0.0}
if not sales_df.empty and "שלב" in sales_df.columns and "סכום" in sales_df.columns:
    done = sales_df[sales_df["שלב"] == "נכנס לפקדון"]
    if "מטבע" in done.columns:
        for cur in ["ILS", "USD", "EUR"]:
            sub = done[done["מטבע"] == cur]
            raised_by_cur[cur] = sum(_to_float(v) for v in sub.get("סכום", []))
    else:
        raised_by_cur["ILS"] = sum(_to_float(v) for v in done.get("סכום", []))

# Show per-currency committed vs raised
for cur, sym, label in [("ILS","₪","שקל"), ("USD","$","דולר"), ("EUR","€","יורו")]:
    comm = committed_by_cur[cur]
    rais = raised_by_cur[cur]
    if comm == 0 and rais == 0:
        continue
    remain = max(0, comm - rais)
    pct    = int(rais / comm * 100) if comm > 0 else 0
    st.markdown(f"**{sym} {label}**")
    gc1, gc2, gc3 = st.columns(3)
    with gc1:
        st.markdown(f"""<div class='kpi-card' style='border-color:#1A7A4A;'>
          <div class='kpi-label'>גויס ({label})</div>
          <div class='kpi-value' style='color:#1A7A4A;'>{sym}{rais:,.0f}</div>
        </div>""", unsafe_allow_html=True)
    with gc2:
        st.markdown(f"""<div class='kpi-card'>
          <div class='kpi-label'>מתחייב ({label})</div>
          <div class='kpi-value'>{sym}{comm:,.0f}</div>
        </div>""", unsafe_allow_html=True)
    with gc3:
        st.markdown(f"""<div class='kpi-card' style='border-color:#C55A11;'>
          <div class='kpi-label'>יתרה ({label})</div>
          <div class='kpi-value' style='color:#C55A11;'>{sym}{remain:,.0f}</div>
        </div>""", unsafe_allow_html=True)
    st.progress(pct / 100, text=f"התקדמות גיוס {label}: {pct}%")
    st.markdown("<div style='margin-bottom:.5rem'></div>", unsafe_allow_html=True)

# Fallback if no active products
if all(v == 0 for v in committed_by_cur.values()) and all(v == 0 for v in raised_by_cur.values()):
    st.info("אין פקדונות פעילים עם סכומים — עדכן גודל עסקה בדף 'פרטי פקדון'")

committed = committed_by_cur["ILS"]  # keep for pipeline coverage calc below

st.divider()

# ── Pipeline breakdown ────────────────────────────────────────────────────────
st.markdown("### פייפליין לפי וודאות")
if not pipeline_df.empty and "רמת וודאות" in pipeline_df.columns:
    c1, c2, c3 = st.columns(3)
    for col_obj, level, color in [(c1,"גבוהה","#C6EFCE"), (c2,"בינונית","#FFF2CC"), (c3,"נמוכה","#FDEBD0")]:
        count = len(pipeline_df[pipeline_df["רמת וודאות"] == level])
        try:
            amt = pipeline_df[pipeline_df["רמת וודאות"] == level]["סכום משוער"].astype(str).str.replace(",","").astype(float).sum()
        except Exception:
            amt = 0
        with col_obj:
            st.markdown(f"""<div class='kpi-card' style='background:{color}; border-color:#aaa;'>
              <div class='kpi-label'>וודאות {level}</div>
              <div class='kpi-value'>{count}</div>
              <div style='font-size:.85rem; color:#555;'>₪{amt:,.0f}</div>
            </div>""", unsafe_allow_html=True)
else:
    st.info("הפייפליין ריק")

st.divider()

# ── Pipeline potential ────────────────────────────────────────────────────────
st.markdown("### 🎯 פוטנציאל פייפליין (וודאות גבוהה + בינונית)")
if not pipeline_df.empty and "רמת וודאות" in pipeline_df.columns and "סכום משוער" in pipeline_df.columns:
    hot = pipeline_df[pipeline_df["רמת וודאות"].isin(["גבוהה", "בינונית"])].copy()
    def _amt(series):
        try: return series.astype(str).str.replace(",","").replace("","0").astype(float)
        except: return pd.Series([0.0]*len(series))
    hot["_n"] = _amt(hot["סכום משוער"])
    pp_cols = st.columns(3)
    for col_obj, cur, sym in zip(pp_cols, ["ILS","USD","EUR"], ["₪","$","€"]):
        sub   = hot[hot["מטבע"] == cur] if "מטבע" in hot.columns else pd.DataFrame()
        total = sub["_n"].sum()
        cnt   = len(sub)
        with col_obj:
            st.markdown(f"""<div class='kpi-card' style='border-color:#1F6B75;'>
              <div class='kpi-label'>פוטנציאל {cur} ({cnt} לידים)</div>
              <div class='kpi-value' style='color:#1F6B75;'>{sym}{total:,.0f}</div>
            </div>""", unsafe_allow_html=True)
    # Coverage vs committed
    pot_ils = hot[hot["מטבע"]=="ILS"]["_n"].sum() if "מטבע" in hot.columns else hot["_n"].sum()
    if committed > 0:
        coverage = int(pot_ils / committed * 100)
        bar_color = "#1A7A4A" if coverage >= 100 else ("#C55A11" if coverage < 70 else "#B8860B")
        st.markdown(f"<div style='margin-top:.8rem; font-size:.9rem; color:{bar_color};'>"
                    f"<b>כיסוי שקלי: {coverage}%</b> מהסכום המתחייב (₪{committed:,.0f})</div>",
                    unsafe_allow_html=True)
else:
    st.info("אין נתוני פייפליין")

st.divider()

# ── Sales stages ──────────────────────────────────────────────────────────────
st.markdown("### שלבי מכירה")
if not sales_df.empty and "שלב" in sales_df.columns:
    cols = st.columns(len(SALES_STAGES))
    for col_obj, stage in zip(cols, SALES_STAGES):
        count = len(sales_df[sales_df["שלב"] == stage])
        with col_obj:
            st.markdown(f"""<div style='background:#F2F4FA; border-radius:8px; padding:.75rem .5rem;
                                        text-align:center; border-top:3px solid #1E2761;'>
              <div style='font-size:1.6rem; font-weight:700; color:#1E2761;'>{count}</div>
              <div style='font-size:.72rem; color:#555; margin-top:.2rem;'>{stage}</div>
            </div>""", unsafe_allow_html=True)
else:
    st.info("אין נתוני מכירות עדיין")

st.divider()

# ── Hot leads (redemptions) ───────────────────────────────────────────────────
st.markdown("### 🔥 לידים חמים — פקדונות שפקעו")
if not redemptions_df.empty:
    hot = redemptions_df[redemptions_df.get("פנינו לגבי חדש", pd.Series(dtype=str)).isin(["מעוניין", "בשיחה"])] if "פנינו לגבי חדש" in redemptions_df.columns else pd.DataFrame()
    total = len(redemptions_df)
    contacted = len(hot)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"""<div class='kpi-card' style='border-color:#1F6B75;'>
          <div class='kpi-label'>פקדונות שפקעו</div>
          <div class='kpi-value' style='color:#1F6B75;'>{total}</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class='kpi-card' style='border-color:#1A7A4A;'>
          <div class='kpi-label'>בשיחה / מעוניין בפקדון הבא</div>
          <div class='kpi-value' style='color:#1A7A4A;'>{contacted}</div>
        </div>""", unsafe_allow_html=True)
else:
    st.info("אין פקדונות פקועים עדיין")
