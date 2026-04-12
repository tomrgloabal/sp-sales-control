import streamlit as st
import pandas as pd
from datetime import date
from auth import require_login, current_user
from sheets import read_df, write_df, append_row, log_action
from config import SALES_STAGES, BANKS, CURRENCIES, SALES_COLS, BANK_DETAILS, USER_EMAILS

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

def _pipeline_names() -> list[str]:
    """Return list of customer names from Pipeline sheet."""
    df = read_df("Pipeline")
    if df.empty or "שם לקוח" not in df.columns:
        return []
    return sorted(df["שם לקוח"].dropna().unique().tolist())

def _pipeline_data(name: str) -> dict:
    """Return pipeline row data for a given name (bank, amount, currency)."""
    df = read_df("Pipeline")
    if df.empty or "שם לקוח" not in df.columns:
        return {}
    match = df[df["שם לקוח"] == name]
    if match.empty:
        return {}
    row = match.iloc[0]
    return {
        "bank":     str(row.get("בנק", "")),
        "amount":   int(float(str(row.get("סכום משוער", 0) or 0).replace(",", "") or 0)),
        "currency": str(row.get("מטבע", "ILS")),
    }

_NEW_CUSTOMER = "— לקוח חדש (הקלד ידנית) —"
_pipeline_names_list = _pipeline_names()
_name_options = _pipeline_names_list + [_NEW_CUSTOMER]

with st.expander("➕ הוספת לקוח לתהליך מכירה", expanded=True):

    # Name selector — outside form so it can drive pre-fill
    sel_name_opt = st.selectbox(
        "שם לקוח *",
        _name_options,
        index=len(_name_options) - 1,
        key="sale_name_sel",
        help="בחר מהפייפליין או בחר 'לקוח חדש' להקלדה ידנית"
    )

    from_pipeline = sel_name_opt != _NEW_CUSTOMER
    pdata = _pipeline_data(sel_name_opt) if from_pipeline else {}

    if not from_pipeline:
        manual_name = st.text_input("הקלד שם לקוח", key="sale_name_manual")
    else:
        manual_name = ""
        st.caption(f"✓ נבחר מהפייפליין: **{sel_name_opt}**")

    with st.form("add_sale", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            # Pre-fill bank from pipeline if available
            bank_default_idx = BANKS.index(pdata["bank"]) if pdata.get("bank") and pdata["bank"] in BANKS else 0
            bank   = st.selectbox("בנק הלקוח", BANKS, index=bank_default_idx)
            isins  = _active_isins()
            isin_options = isins + ["— כללי —"] if isins else ["— כללי —"]
            sel_isin = st.selectbox("פקדון (ISIN)", isin_options)
        with c2:
            amount     = st.number_input("סכום", min_value=0, step=50000,
                                         value=pdata.get("amount", 0))
            cur_default = pdata.get("currency", "ILS")
            cur_idx = CURRENCIES.index(cur_default) if cur_default in CURRENCIES else 0
            currency   = st.selectbox("מטבע", CURRENCIES, index=cur_idx)
            stage      = st.selectbox("שלב נוכחי", SALES_STAGES)
            offer_date = st.date_input("תאריך הצעה", value=date.today())
        notes = st.text_area("הערות")
        sub = st.form_submit_button("הוסף", use_container_width=True, type="primary")

    if sub:
        name = sel_name_opt if from_pipeline else manual_name.strip()
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

    # Customer selector OUTSIDE form (drives which row we show)
    sel = st.selectbox("בחר לקוח", names, key="stage_sel")
    row_idx = full_df[full_df["שם לקוח"] == sel].index[0]
    current_stage = full_df.at[row_idx, "שלב"] if "שלב" in full_df.columns else SALES_STAGES[0]

    # Everything else inside a form — no rerun on checkbox/selectbox change
    with st.form("update_stage_form"):
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            new_stage = st.selectbox("שלב חדש", SALES_STAGES,
                index=SALES_STAGES.index(current_stage) if current_stage in SALES_STAGES else 0)
        with c2:
            confirm_date = st.date_input("תאריך אישור", value=date.today())
        with c3:
            cur_curr = str(full_df.at[row_idx, "מטבע"]) if "מטבע" in full_df.columns else "ILS"
            new_currency = st.selectbox("מטבע", CURRENCIES,
                index=CURRENCIES.index(cur_curr) if cur_curr in CURRENCIES else 0)

        st.markdown("**סימון שלבי ביצוע:**")
        bc1, bc2, bc3, bc4 = st.columns(4)
        with bc1:
            inst_sent = st.checkbox("הנחיות נשלחו",
                value=(full_df.at[row_idx, "הנחיות נשלחו"] == "כן") if "הנחיות נשלחו" in full_df.columns else False)
        with bc2:
            docs_done = st.checkbox("מסמכים הוכנו",
                value=(full_df.at[row_idx, "מסמכים הוכנו"] == "כן") if "מסמכים הוכנו" in full_df.columns else False)
        with bc3:
            bank_conf = st.checkbox("אישור בנק לקוח",
                value=(full_df.at[row_idx, "אישור בנק לקוח"] == "כן") if "אישור בנק לקוח" in full_df.columns else False)
        with bc4:
            iss_conf = st.checkbox("אישור בנק מנפיק",
                value=(full_df.at[row_idx, "אישור בנק מנפיק"] == "כן") if "אישור בנק מנפיק" in full_df.columns else False)

        update_btn = st.form_submit_button("✓ עדכן", use_container_width=True, type="primary")

    if update_btn:
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

    # ── Partner email ─────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 📧 שלח עדכון לשותף")

    # Find which partner brought this customer (from Pipeline)
    pipeline_df = read_df("Pipeline")
    partner_name = ""
    if not pipeline_df.empty and "שם לקוח" in pipeline_df.columns and "דרך נציג" in pipeline_df.columns:
        match = pipeline_df[pipeline_df["שם לקוח"] == sel]
        if not match.empty:
            partner_name = str(match.iloc[0].get("דרך נציג", ""))

    # Get product details for ISIN
    isin_val  = str(full_df.at[row_idx, "ISIN פקדון"]) if "ISIN פקדון" in full_df.columns else ""
    bank_name = str(full_df.at[row_idx, "בנק"])        if "בנק"        in full_df.columns else ""
    amount    = str(full_df.at[row_idx, "סכום"])        if "סכום"       in full_df.columns else ""
    currency  = str(full_df.at[row_idx, "מטבע"])        if "מטבע"       in full_df.columns else ""

    prod_line = ""
    if isin_val:
        prod_df = read_df("Products")
        if not prod_df.empty and "ISIN" in prod_df.columns:
            pm = prod_df[prod_df["ISIN"] == isin_val]
            if not pm.empty:
                p = pm.iloc[0]
                issuer  = p.get("מנפיק", "—")
                coupon  = p.get("קופון שנתי", "—")
                dur     = p.get('מח"מ (חודשים)', "—")
                barrier = p.get("מחסום", "—")
                prod_line = f"פקדון: {issuer} | ISIN: {isin_val} | קופון: {coupon}% | מח\"מ: {dur} חודשים | מחסום: {barrier}"

    # Bank instructions lookup (partial match)
    bank_key = next((k for k in BANK_DETAILS if k in bank_name), None)
    bank_info = BANK_DETAILS.get(bank_key, {}) if bank_key else {}
    clearing  = bank_info.get("clearing_code", "—")
    method    = bank_info.get("method", "—")
    attachments_list = bank_info.get("attachments", [])
    bank_notes = bank_info.get("notes", "")

    # Build email body
    stage_display = str(full_df.at[row_idx, "שלב"]) if "שלב" in full_df.columns else ""
    partner_short = partner_name.split()[0] if partner_name else "שותף"
    attachments_text = "\n".join(f"  • {a}" for a in attachments_list) if attachments_list else "  • אין קבצים מיוחדים"

    email_subject = f"עדכון תהליך — {sel} | {stage_display}"
    email_body = f"""שלום {partner_short},

עדכון לגבי המשקיע שהכנסת — {sel}:

שלב נוכחי: {stage_display}
{prod_line}
בנק: {bank_name} | סכום: {currency} {amount}

── הנחיות לבנק ──
שיטת ביצוע: {method}
קוד סליקה: {clearing}
{("הערות: " + bank_notes) if bank_notes else ""}

── קבצים לצרף ──
{attachments_text}

לשאלות — צור קשר.
בברכה,
Arbitrage Global"""

    # Display partner info
    if partner_name:
        partner_email = USER_EMAILS.get(partner_name, "")
        col_p1, col_p2 = st.columns([3, 1])
        with col_p1:
            st.markdown(f"**שותף:** {partner_name}"
                        + (f"  |  📬 `{partner_email}`" if partner_email else "  |  *(אין מייל רשום)*"))
        with col_p2:
            if partner_email:
                import urllib.parse
                mailto = f"mailto:{partner_email}?subject={urllib.parse.quote(email_subject)}&body={urllib.parse.quote(email_body)}"
                st.link_button("📤 פתח בתוכנת מייל", mailto, use_container_width=True)
    else:
        st.caption("לא נמצא שותף מקשר ללקוח זה בפייפליין")

    # Email preview
    with st.expander("📄 תצוגה מקדימה של המייל", expanded=False):
        st.markdown(f"**נושא:** {email_subject}")
        st.text_area("גוף המייל", value=email_body, height=320, key="email_preview_body")
        st.caption("ניתן לערוך את הטקסט לפני שליחה")

    # Attachments checklist
    if attachments_list:
        with st.expander(f"📎 קבצים נלווים ({len(attachments_list)})", expanded=True):
            st.caption(f"קבצים נדרשים עבור {bank_name}:")
            for att in attachments_list:
                st.checkbox(att, key=f"att_{sel}_{att[:20]}")
            if bank_notes:
                st.info(f"💡 {bank_notes}")
