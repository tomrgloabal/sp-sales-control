import streamlit as st
import pandas as pd
from datetime import date
from auth import require_login, current_user
from sheets import read_df, write_df, append_row, log_action
from config import SALES_STAGES, BANKS, CURRENCIES, SALES_COLS

require_login()

st.markdown("""<style>.stApp{direction:rtl;} header[data-testid="stHeader"]{display:none;}</style>""", unsafe_allow_html=True)
st.markdown("<h2 style='color:#1E2761;'>💼 מעקב מכירות</h2>", unsafe_allow_html=True)
st.caption("ניהול 7 שלבי הליך המכירה — מהצעה ועד אישור בנק מנפיק.")

STAGE_COLORS = {
    "הצעה נשלחה":           "#C9D7F5",
    "מעוניין - בבחינה":     "#C9D7F5",
    "אישר כניסה":            "#FFF2CC",
    "הנחיות נשלחו ללקוח":  "#FDEBD0",
    "בנק לקוח מטפל":         "#FDEBD0",
    'אושר ע"י בנק מנפיק':   "#C6EFCE",
    "נכנס לפקדון":            "#1A7A4A",
}


def _active_isins() -> list[str]:
    df = read_df("Products")
    if df.empty or "ISIN" not in df.columns:
        p = read_df("Product")
        if not p.empty and "שדה" in p.columns:
            d = dict(zip(p["שדה"], p["ערך"]))
            isin = d.get("ISIN", "")
            return [isin] if isin else []
        return []
    active = df[df["סטטוס"].isin(["פעיל", ""])] if "סטטוס" in df.columns else df
    return active["ISIN"].dropna().tolist()


# ── Add entry ─────────────────────────────────────────────────────────────────
with st.expander("➕ הוספת לקוח לתהליך מכירה", expanded=True):
    with st.form("add_sale", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            name   = st.text_input("שם לקוח *")
            bank   = st.selectbox("בנק הלקוח", BANKS)
            isins  = _active_isins()
            isin_options = isins + ["— כללי —"] if isins else ["— כללי —"]
            sel_isin = st.selectbox("פקדון (ISIN)", isin_options)
        with c2:
            amount     = st.number_input("סכום", min_value=0, step=50000)
            currency   = st.selectbox("מטבע", CURRENCIES)
            stage      = st.selectbox("שלב נוכחי", SALES_STAGES)
            offer_date = st.date_input("תאריך הצעה", value=date.today())
        notes = st.text_area("הערות")
        sub = st.form_submit_button("הוסף", use_container_width=True, type="primary")

    if sub:
        if not name:
            st.error("שם לקוח חובה")
        else:
            isin_val = sel_isin if sel_isin != "— כללי —" else ""
            row = [name, bank, isin_val, amount, currency, stage,
                   offer_date.strftime("%d/%m/%Y"), "", "לא", "לא", "לא", "לא", notes]
            append_row("Sales", row)
            log_action(current_user(), "הוסף לקוח למכירות", name)
            st.success(f"✓ {name} נוסף")
            st.rerun()

# ── Table ─────────────────────────────────────────────────────────────────────
df = read_df("Sales")

if df.empty:
    st.info("אין לקוחות בתהליך מכירה עדיין.")
else:
    for col in SALES_COLS:
        if col not in df.columns:
            df[col] = ""

    # Summary metrics
    done_df = df[df["שלב"] == "נכנס לפקדון"] if "שלב" in df.columns else pd.DataFrame()
    ils_df  = done_df[done_df.get("מטבע", pd.Series(dtype=str)) == "ILS"] if "מטבע" in done_df.columns else done_df
    usd_df  = done_df[done_df.get("מטבע", pd.Series(dtype=str)) == "USD"] if "מטבע" in done_df.columns else pd.DataFrame()

    def _sum(frame):
        try:
            return frame["סכום"].astype(str).str.replace(",", "").astype(float).sum()
        except Exception:
            return 0

    total_ils = _sum(done_df if "מטבע" not in done_df.columns else done_df[done_df["מטבע"].fillna("ILS") == "ILS"])
    total_usd = _sum(done_df[done_df["מטבע"] == "USD"]) if "מטבע" in done_df.columns else 0

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"<div style='background:#C6EFCE;border-radius:8px;padding:.75rem 1rem;direction:rtl;'>"
                    f"<div style='font-size:.85rem;color:#1A7A4A;'>גויס (₪)</div>"
                    f"<div style='font-size:1.6rem;font-weight:700;color:#1A7A4A;'>₪{total_ils:,.0f}</div>"
                    f"</div>", unsafe_allow_html=True)
    with c2:
        st.markdown(f"<div style='background:#D6EEF2;border-radius:8px;padding:.75rem 1rem;direction:rtl;'>"
                    f"<div style='font-size:.85rem;color:#1F6B75;'>גויס ($)</div>"
                    f"<div style='font-size:1.6rem;font-weight:700;color:#1F6B75;'>${total_usd:,.0f}</div>"
                    f"</div>", unsafe_allow_html=True)
    with c3:
        st.markdown(f"<div style='background:#FFF2CC;border-radius:8px;padding:.75rem 1rem;direction:rtl;'>"
                    f"<div style='font-size:.85rem;color:#7D6608;'>לקוחות בתהליך</div>"
                    f"<div style='font-size:1.6rem;font-weight:700;color:#7D6608;'>{len(df)}</div>"
                    f"</div>", unsafe_allow_html=True)

    st.markdown("")

    # Stage filter
    sel_stages = st.multiselect("סנן לפי שלב", SALES_STAGES, default=SALES_STAGES)
    view_df = df[df["שלב"].isin(sel_stages)] if sel_stages and "שלב" in df.columns else df

    def color_stage(val):
        return f"background-color:{STAGE_COLORS.get(val,'')};color:{'#fff' if val=='נכנס לפקדון' else '#000'}"

    display_df = view_df[SALES_COLS].copy() if all(c in view_df.columns for c in SALES_COLS) else view_df
    styled = display_df.style.map(color_stage, subset=["שלב"] if "שלב" in display_df.columns else [])
    st.dataframe(styled, use_container_width=True, height=400)

# ── Quick stage update ────────────────────────────────────────────────────────
full_df = read_df("Sales")
if not full_df.empty and "שם לקוח" in full_df.columns:
    st.markdown("---")
    st.markdown("#### עדכון שלב מהיר")
    names = full_df["שם לקוח"].tolist()
    sel = st.selectbox("בחר לקוח", names, key="stage_sel")
    row_idx = full_df[full_df["שם לקוח"] == sel].index[0]
    current_stage = full_df.at[row_idx, "שלב"] if "שלב" in full_df.columns else SALES_STAGES[0]

    c1, c2, c3 = st.columns([2, 1, 1])
    with c1:
        new_stage = st.selectbox("שלב חדש", SALES_STAGES,
            index=SALES_STAGES.index(current_stage) if current_stage in SALES_STAGES else 0,
            key="new_stage")
    with c2:
        confirm_date = st.date_input("תאריך אישור", value=date.today(), key="confirm_date")
    with c3:
        cur_curr = str(full_df.at[row_idx, "מטבע"]) if "מטבע" in full_df.columns else "ILS"
        new_currency = st.selectbox("מטבע", CURRENCIES,
            index=CURRENCIES.index(cur_curr) if cur_curr in CURRENCIES else 0,
            key="stage_currency")

    st.markdown("**סימון שלבי ביצוע:**")
    bc1, bc2, bc3, bc4 = st.columns(4)
    with bc1: inst_sent = st.checkbox("הנחיות נשלחו",  value=full_df.at[row_idx, "הנחיות נשלחו"] == "כן"  if "הנחיות נשלחו"  in full_df.columns else False)
    with bc2: docs_done = st.checkbox("מסמכים הוכנו",  value=full_df.at[row_idx, "מסמכים הוכנו"]  == "כן"  if "מסמכים הוכנו"  in full_df.columns else False)
    with bc3: bank_conf = st.checkbox("אישור בנק לקוח",value=full_df.at[row_idx, "אישור בנק לקוח"] == "כן" if "אישור בנק לקוח" in full_df.columns else False)
    with bc4: iss_conf  = st.checkbox("אישור בנק מנפיק",value=full_df.at[row_idx,"אישור בנק מנפיק"]== "כן" if "אישור בנק מנפיק" in full_df.columns else False)

    if st.button("✓ עדכן", use_container_width=True, type="primary"):
        full_df.at[row_idx, "שלב"]             = new_stage
        full_df.at[row_idx, "תאריך אישור"]     = confirm_date.strftime("%d/%m/%Y")
        full_df.at[row_idx, "מטבע"]             = new_currency
        full_df.at[row_idx, "הנחיות נשלחו"]    = "כן" if inst_sent else "לא"
        full_df.at[row_idx, "מסמכים הוכנו"]    = "כן" if docs_done else "לא"
        full_df.at[row_idx, "אישור בנק לקוח"]  = "כן" if bank_conf else "לא"
        full_df.at[row_idx, "אישור בנק מנפיק"] = "כן" if iss_conf  else "לא"
        write_df("Sales", full_df)
        log_action(current_user(), "עדכון שלב מכירה", f"{sel} → {new_stage}")
        st.success(f"✓ {sel} עודכן ל: {new_stage}")
        st.rerun()
