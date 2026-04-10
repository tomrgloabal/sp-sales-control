import streamlit as st
import pandas as pd
import os
from datetime import date
from pathlib import Path
from auth import require_login, current_user
from sheets import read_df, write_df, log_action
from config import BANKS, BANKS_COLS, BANK_DETAILS, PRIVATAM

require_login()

st.markdown("""<style>.stApp{direction:rtl;} header[data-testid="stHeader"]{display:none;}</style>""", unsafe_allow_html=True)
st.markdown("<h2 style='color:#1E2761;'>🏦 הנחיות ביצוע לפי בנק</h2>", unsafe_allow_html=True)

BANKS_DIR = Path(__file__).parent.parent / "בנקים"

# ── Map folder names to bank names ────────────────────────────────────────────
BANK_FOLDER_MAP = {
    "לאומי":       "לאומי",
    "מזרחי":       "מזרחי",
    "פועלים":      "פועלים",
    "דיסקונט":     "דיסקונט",
    "הבינלאומי":   "הבינלאומי",
    "גלובלנט":     "גלובלנט",
    "SAFRA":       "SAFRA",
    "UBP":         "UBP",
}

SUB_FOLDER_LABELS = {
    "הוראות":        "📋 הוראות לברוקר",
    "טיקטים":        "📝 טיקטים",
    "מייל":          "📧 מיילים לדוגמא",
    "קובץ אקסל":     "📊 קבצי סליקה",
}


def _list_bank_files(bank_folder: str) -> dict[str, list[str]]:
    """Return {subfolder_label: [filename, ...]} for a given bank folder."""
    bank_path = BANKS_DIR / bank_folder
    result: dict[str, list[str]] = {}
    if not bank_path.exists():
        return result
    for sub in bank_path.iterdir():
        if sub.is_dir():
            label = sub.name
            for key in SUB_FOLDER_LABELS:
                if key in sub.name:
                    label = SUB_FOLDER_LABELS[key]
                    break
            files = [f.name for f in sub.iterdir() if f.is_file()]
            if files:
                result[label] = files
    return result


# ─── Tab layout ────────────────────────────────────────────────────────────────
tab_hanchayot, tab_gen, tab_edit = st.tabs(["📋 הנחיות לפי בנק", "✉️ יצירת מייל הנחיות", "⚙️ עריכת פרטי בנקים"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Bank instructions browser
# ══════════════════════════════════════════════════════════════════════════════
with tab_hanchayot:
    if not BANKS_DIR.exists():
        st.info("תיקיית 'בנקים' לא נמצאה בתיקיית sp-sales-app.")
    else:
        available_banks = [d.name for d in BANKS_DIR.iterdir() if d.is_dir() and d.name != "גיוסים"]
        if not available_banks:
            st.info("לא נמצאו תיקיות בנקים.")
        else:
            sel_bank = st.selectbox("בחר בנק", available_banks, key="bank_browser_sel")
            st.markdown(f"### 🏦 {sel_bank}")

            files_by_folder = _list_bank_files(sel_bank)
            if not files_by_folder:
                st.info("אין קבצים בתיקייה זו.")
            else:
                for folder_label, files in files_by_folder.items():
                    st.markdown(f"**{folder_label}**")
                    for fname in sorted(files):
                        ext = fname.split(".")[-1].lower()
                        icon = {"pdf": "📄", "docx": "📝", "xlsx": "📊", "msg": "📧"}.get(ext, "📎")
                        st.markdown(f"- {icon} {fname}")
                    st.markdown("")

            # Show general notes from DB
            df_banks = read_df("Banks")
            if not df_banks.empty:
                match = df_banks[df_banks["שם הבנק"].str.contains(sel_bank, case=False, na=False)]
                if not match.empty:
                    row = match.iloc[0]
                    if row.get("הוראות מיוחדות", ""):
                        st.markdown("**הוראות מיוחדות שנשמרו:**")
                        st.info(row["הוראות מיוחדות"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Email generator
# ══════════════════════════════════════════════════════════════════════════════
with tab_gen:
    st.markdown("#### ✉️ יצירת מייל הנחיות רכישה")
    st.caption("בחר פקדון ומשקיע — כל השדות ימולאו אוטומטית.")

    # ── Product selector ──────────────────────────────────────────────────────
    products_df = read_df("Products")
    prod_df     = read_df("Product")

    # Build product list: from Products tab + fallback to Product tab
    prod_options: dict[str, dict] = {}  # ISIN → fields dict
    if not products_df.empty and "ISIN" in products_df.columns:
        for _, row in products_df.iterrows():
            isin_key = str(row.get("ISIN", "")).strip()
            if isin_key:
                prod_options[isin_key] = {
                    "מנפיק":      row.get("מנפיק", ""),
                    "נכסי בסיס": row.get("נכסי בסיס", ""),
                    "קופון שנתי": row.get("קופון שנתי", ""),
                    'מח"מ (חודשים)': row.get('מח"מ (חודשים)', ""),
                    "מטבע":       row.get("מטבע", "ILS"),
                    "תאריך סגירה": row.get("תאריך סגירה", ""),
                }
    # Fallback: use the single Product tab
    fallback_prod = {}
    if not prod_df.empty and "שדה" in prod_df.columns:
        fallback_prod = dict(zip(prod_df["שדה"], prod_df["ערך"]))
        fb_isin = fallback_prod.get("ISIN", "")
        if fb_isin and fb_isin not in prod_options:
            prod_options[fb_isin] = fallback_prod

    isin_list = list(prod_options.keys()) or [""]
    sel_prod_isin = st.selectbox(
        "בחר פקדון (ISIN)",
        isin_list,
        format_func=lambda x: f"{x} — {prod_options.get(x, {}).get('מנפיק', '')} | {prod_options.get(x, {}).get('נכסי בסיס', '')}",
        key="gen_prod_sel"
    )
    # Auto-load product fields
    prod = prod_options.get(sel_prod_isin, fallback_prod)
    # For full details (barrier, triggers, etc.) load from Product tab if ISIN matches
    if fallback_prod.get("ISIN") == sel_prod_isin:
        prod = fallback_prod

    # ── Investor + bank selection ─────────────────────────────────────────────
    pip_df   = read_df("Pipeline")
    sales_df = read_df("Sales")
    investor_names: list[str] = []
    investor_data: dict[str, dict] = {}

    # Build investor list with their data
    for df_, isin_col in [(pip_df, "ISIN פקדון"), (sales_df, "ISIN פקדון")]:
        if df_.empty or "שם לקוח" not in df_.columns:
            continue
        # Filter to selected product if possible
        if isin_col in df_.columns:
            filtered = df_[df_[isin_col].fillna("") == sel_prod_isin]
            if filtered.empty:
                filtered = df_
        else:
            filtered = df_
        for _, r in filtered.iterrows():
            name = str(r.get("שם לקוח", "")).strip()
            if name and name not in investor_data:
                investor_names.append(name)
                investor_data[name] = {
                    "בנק":    str(r.get("בנק", "")),
                    "סכום":   r.get("סכום", 0),
                    "מטבע":   str(r.get("מטבע", "ILS")),
                }
    investor_names = sorted(set(investor_names))

    c1, c2 = st.columns(2)
    with c1:
        inv_opts = ["— הקלד ידנית —"] + investor_names
        inv_choice = st.selectbox("משקיע", inv_opts, key="gen_inv_sel")
        inv_prefill = investor_data.get(inv_choice, {}) if inv_choice != "— הקלד ידנית —" else {}
        investor_name = st.text_input(
            "שם משקיע",
            value="" if inv_choice == "— הקלד ידנית —" else inv_choice,
            key="gen_inv_manual"
        )
        account_num = st.text_input("מספר חשבון", placeholder="12345678", key="gen_account")

    with c2:
        if BANKS_DIR.exists():
            bank_options = [d.name for d in BANKS_DIR.iterdir() if d.is_dir() and d.name != "גיוסים"]
        else:
            bank_options = BANKS
        # Auto-select bank from investor data
        inv_bank = inv_prefill.get("בנק", "")
        bank_default_idx = next((i for i, b in enumerate(bank_options) if inv_bank and inv_bank in b), 0)
        sel_gen_bank = st.selectbox("בנק", bank_options, index=bank_default_idx, key="gen_bank")

        # Auto-select currency from product
        prod_currency = prod.get("מטבע", "ILS")
        currencies_list = ["ILS", "USD", "EUR", "CHF"]
        cur_idx = currencies_list.index(prod_currency) if prod_currency in currencies_list else 0
        currency = st.selectbox("מטבע", currencies_list, index=cur_idx, key="gen_currency")

        # Auto-fill amount from investor data
        inv_amount = int(inv_prefill.get("סכום", 0)) if inv_prefill.get("סכום") else 0
        amount = st.number_input("סכום", min_value=0, step=50000, value=inv_amount, key="gen_amount")

    # Product fields (auto-filled, shown for reference)
    isin         = sel_prod_isin or prod.get("ISIN", "XXXXXXXX")
    issuer       = prod.get("מנפיק", "")
    und1, und2, und3 = prod.get("נכס בסיס 1", ""), prod.get("נכס בסיס 2", ""), prod.get("נכס בסיס 3", "")
    product_name = prod.get("נכסי בסיס", "") or " / ".join(filter(None, [und1, und2, und3]))
    coupon       = prod.get("קופון שנתי", "")
    maturity     = prod.get('מח"מ (חודשים)', "")
    strike_date  = prod.get("תאריך Strike", "")
    close_date   = prod.get("תאריך סגירת גיוס", "") or prod.get("תאריך סגירה", "")

    trade_date = st.text_input("תאריך עסקה (Trade Date)", value=date.today().strftime("%d/%m/%Y"), key="gen_trade_date")
    settlement_date = st.text_input("תאריך ערך (Value Date)", placeholder="DD/MM/YYYY", key="gen_value_date")

    # Load bank-specific instructions
    df_banks = read_df("Banks")
    bank_instructions = ""
    if not df_banks.empty:
        match = df_banks[df_banks["שם הבנק"].str.contains(sel_gen_bank, case=False, na=False)]
        if not match.empty:
            bank_instructions = match.iloc[0].get("הוראות מיוחדות", "")
            bank_contact = match.iloc[0].get("איש קשר", "")
            bank_method = match.iloc[0].get("שיטת ביצוע", "")

    # Get bank clearing code from BANK_DETAILS (normalize: strip "בנק " prefix)
    bank_key = sel_gen_bank.replace("בנק ", "").strip()
    bank_detail = BANK_DETAILS.get(bank_key, BANK_DETAILS.get(sel_gen_bank, {}))
    bank_name_en = bank_detail.get("name_en", sel_gen_bank)
    clearing_code = bank_detail.get("clearing_code", "")
    attachments_list = bank_detail.get("attachments", [])
    bank_exec_notes = bank_detail.get("notes", "") or bank_instructions

    if st.button("🖊️ צור מייל", use_container_width=True, type="primary", key="gen_btn"):
        investor_display = investor_name or "____________"
        account_display  = account_num   or "____________"
        amount_display   = f"{amount:,.0f}" if amount else "____________"

        email_subject = f"רכישת מוצר מובנה {isin} בחשבון ע\"ש {investor_display}"

        attachments_text = "\n".join(f"  • {a}" for a in attachments_list) if attachments_list else "  • Ticket (ממולא)"

        email_body = f"""נושא: {email_subject}

שלום,

הרינו להורות על רכישת מוצר מובנה עבור לקוחינו בפרטים הבאים:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PARTIES:
  Seller:  {PRIVATAM}
  Buyer:   {bank_name_en} ({clearing_code})

TRANSACTION DETAILS:
  ISIN:           {isin}
  Issuer:         {issuer}
  Product:        {product_name}
  Coupon (p.a.):  {coupon}
  Maturity:       {maturity} months
  Barrier:        {prod.get('מחסום', '')}

  Notional:       {amount_display} {currency}
  Trade price:    100.00%
  Trade date:     {trade_date}
  Value date:     {settlement_date or "Trade date + 5 business days"}
  Strike date:    {strike_date}
  Closing date:   {close_date}

  Client:         {investor_display}
  Account:        {account_display} ({sel_gen_bank})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{('הוראות מיוחדות:' + chr(10) + bank_exec_notes + chr(10)) if bank_exec_notes else ''}
קבצים מצורפים:
{attachments_text}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Please notify the seller of any inconsistency. The seller will consider all information
contained in this confirmation as correct and binding if no notification is received
within 1 working day.

Many thanks and best regards,
{current_user()}
Arbitrage Global Wealth Management
"""

        st.markdown("---")
        st.markdown(f"**📋 נושא המייל:**  `{email_subject}`")
        st.text_area("גוף המייל — העתק ושלח", value=email_body, height=500, key="gen_email_output")

        # Show attachment checklist
        if attachments_list:
            st.markdown("**✅ רשימת קבצים לצרף:**")
            for att in attachments_list:
                st.checkbox(att, key=f"att_{att[:20]}")

        log_action(current_user(), "יצירת מייל הנחיות", f"{investor_display} | {isin} | {sel_gen_bank}")
        st.success("✓ המייל מוכן — העתק מהתיבה למעלה")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Edit bank details (original functionality)
# ══════════════════════════════════════════════════════════════════════════════
with tab_edit:
    df = read_df("Banks")
    if df.empty:
        rows = []
        for b in BANKS:
            det = BANK_DETAILS.get(b.replace("בנק ", "").strip(), BANK_DETAILS.get(b, {}))
            rows.append({
                "שם הבנק":         b,
                "איש קשר":         "",
                "שיטת ביצוע":      det.get("method", ""),
                "שדות SWIFT":      det.get("clearing_code", ""),
                "הוראות מיוחדות":  det.get("notes", ""),
                "עדכון אחרון":     "",
            })
        df = pd.DataFrame(rows)
        write_df("Banks", df)

    search = st.text_input("🔍 חיפוש בנק", placeholder="הקלד שם בנק...", key="bank_search_edit")
    filtered = df[df["שם הבנק"].str.contains(search, case=False, na=False)] if search else df

    if not filtered.empty and "שם הבנק" in filtered.columns:
        sel_bank = st.selectbox("בחר בנק לעריכה", filtered["שם הבנק"].tolist(), key="bank_edit_sel")
        row_idx = df[df["שם הבנק"] == sel_bank].index[0]
        row = df.loc[row_idx]

        with st.form("edit_bank"):
            c1, c2 = st.columns(2)
            with c1:
                contact = st.text_input("איש קשר", value=str(row.get("איש קשר", "")))
                method  = st.text_input("שיטת ביצוע", value=str(row.get("שיטת ביצוע", "")))
            with c2:
                swift   = st.text_area("שדות SWIFT נדרשים", value=str(row.get("שדות SWIFT", "")), height=80)
            special = st.text_area("הוראות מיוחדות", value=str(row.get("הוראות מיוחדות", "")), height=100)
            save = st.form_submit_button("💾 שמור הנחיות", use_container_width=True, type="primary")

        if save:
            df.at[row_idx, "איש קשר"]        = contact
            df.at[row_idx, "שיטת ביצוע"]     = method
            df.at[row_idx, "שדות SWIFT"]      = swift
            df.at[row_idx, "הוראות מיוחדות"]  = special
            df.at[row_idx, "עדכון אחרון"]     = date.today().strftime("%d/%m/%Y")
            write_df("Banks", df)
            log_action(current_user(), "עדכון הנחיות בנק", sel_bank)
            st.success(f"✓ הנחיות {sel_bank} נשמרו")
            st.rerun()

    st.divider()
    st.markdown("#### כל הבנקים")
    st.dataframe(df, use_container_width=True)
