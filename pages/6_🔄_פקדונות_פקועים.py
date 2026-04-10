import io
import json
import streamlit as st
import pandas as pd
from datetime import date
from pathlib import Path
from auth import require_login, current_user
from sheets import read_df, write_df, append_row, log_action
from config import CONFIDENCE, CURRENCIES, REDEMP_COLS, PIPELINE_COLS

require_login()

st.markdown("""<style>.stApp{direction:rtl;} header[data-testid="stHeader"]{display:none;}</style>""", unsafe_allow_html=True)
st.markdown("<h2 style='color:#1F6B75;'>🔄 פקדונות שפקעו — לידים חמים</h2>", unsafe_allow_html=True)
st.info("💡 משקיע שפקד לו מוצר = הליד הכי חם לפקדון הבא. כבר מכיר ומאמין. לגשת ראשון.")

CONTACT_STATUS = ["לא", "בשיחה", "מעוניין"]

INV_FILE = Path(__file__).parent.parent / "local_data" / "ProductInvestors.json"

# Ensure local_data directory exists
(Path(__file__).parent.parent / "local_data").mkdir(parents=True, exist_ok=True)


def _load_archive() -> dict:
    if INV_FILE.exists():
        return json.loads(INV_FILE.read_text(encoding="utf-8"))
    return {}


def _existing_names() -> set:
    df = read_df("Redemptions")
    if df.empty or "שם לקוח" not in df.columns:
        return set()
    return set(df["שם לקוח"].dropna().tolist())


# ══════════════════════════════════════════════════════════════════════════════
# ISIN Auto-Import
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("### 🔍 הכנסת ISIN — טעינה אוטומטית")
st.caption("הכנס את ה-ISIN של הפקדון שפקע — המערכת תמצא את כל המשקיעים ותעביר אותם אוטומטית.")

col_isin, col_date = st.columns([2, 1])
with col_isin:
    isin_input = st.text_input("ISIN של הפקדון שפקע", placeholder="XS3293111806",
                                key="auto_isin").strip().upper()
with col_date:
    exp_date_auto = st.date_input("תאריך פקיעה", value=date.today(), key="auto_exp_date")

archive = _load_archive()

if isin_input:
    if isin_input in archive:
        prod = archive[isin_input]
        investors = prod["משקיעים"]

        # Product info card
        st.markdown(
            f"<div style='background:#D6EEF2;border-radius:10px;padding:.8rem 1.2rem;direction:rtl;margin:.5rem 0;'>"
            f"<b style='color:#1E2761;'>{isin_input}</b> — {prod['שם מלא'][:80]}<br>"
            f"<small style='color:#555;'>מנפיק: {prod['מנפיק']} &nbsp;|&nbsp; הנפקה: {prod['ISSUE DATE']}"
            f" &nbsp;|&nbsp; {len(investors)} משקיעים</small>"
            f"</div>",
            unsafe_allow_html=True
        )

        if investors:
            existing = _existing_names()
            new_investors = [i for i in investors if i["שם המשקיע"] not in existing]
            already_in   = [i for i in investors if i["שם המשקיע"] in existing]

            # Preview table
            df_preview = pd.DataFrame(new_investors if new_investors else investors)
            st.dataframe(df_preview, use_container_width=True, hide_index=True)

            if already_in:
                st.caption(f"ℹ️ {len(already_in)} משקיעים כבר קיימים ברשימה: {', '.join(i['שם המשקיע'] for i in already_in)}")

            if new_investors:
                total_ils = sum(i["סכום"] for i in new_investors if i.get("מטבע", "ILS") == "ILS")
                total_usd = sum(i["סכום"] for i in new_investors if i.get("מטבע") == "USD")
                summary = f"₪{total_ils:,.0f}" + (f"  +  ${total_usd:,.0f}" if total_usd else "")

                st.markdown(f"**{len(new_investors)} משקיעים חדשים יועברו — סה\"כ {summary}**")

                if st.button(f"✅ העבר את כולם לפקדונות פקועים ({len(new_investors)} משקיעים)",
                             use_container_width=True, type="primary", key="auto_import_btn"):
                    added = 0
                    for inv in new_investors:
                        row = [
                            inv["שם המשקיע"],
                            isin_input,
                            prod["מנפיק"],
                            inv["סכום"],
                            inv.get("מטבע", "ILS"),
                            exp_date_auto.strftime("%d/%m/%Y"),
                            "",   # סכום + קופון — יעודכן אחר כך
                            "לא",
                            "נמוכה",
                            f"נטען אוטומטית מארכיון | {prod['שם מלא'][:50]}",
                        ]
                        append_row("Redemptions", row)
                        added += 1
                    log_action(current_user(), "ייבוא אוטומטי פקדונות פקועים", f"{isin_input} | {added} משקיעים")
                    st.success(f"✓ {added} משקיעים הועברו לרשימת פקדונות פקועים!")
                    st.rerun()
            else:
                st.success("כל המשקיעים מ-ISIN זה כבר קיימים ברשימה.")
        else:
            st.info("לא נמצאו משקיעים עבור ISIN זה בארכיון.")

    elif isin_input:
        # Partial match
        matches = [k for k in archive if isin_input in k]
        if matches:
            st.caption(f"ISIN לא נמצא בדיוק. תוצאות דומות: {', '.join(matches[:5])}")
        else:
            st.warning(f"ISIN `{isin_input}` לא נמצא בארכיון. ניתן להוסיף ידנית למטה.")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# Manual add (fallback)
# ══════════════════════════════════════════════════════════════════════════════
with st.expander("➕ הוספה ידנית (לא נמצא בארכיון)", expanded=False):
    with st.form("add_redemption", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            name        = st.text_input("שם לקוח *")
            isin_manual = st.text_input("ISIN")
            issuer_bank = st.text_input("בנק מנפיק")
            amount      = st.number_input("סכום מקורי", min_value=0, step=50000)
            currency    = st.selectbox("מטבע", CURRENCIES)
        with c2:
            exp_date    = st.date_input("תאריך פקיעה", value=date.today())
            total_recv  = st.number_input("סכום + קופון שהתקבל", min_value=0, step=1000)
            contacted   = st.selectbox("פנינו לגבי פקדון חדש", CONTACT_STATUS)
            interest    = st.selectbox("רמת עניין", CONFIDENCE)
        notes = st.text_area("הערות")
        sub = st.form_submit_button("הוסף", use_container_width=True)

    if sub:
        if not name:
            st.error("שם לקוח חובה")
        else:
            row = [name, isin_manual, issuer_bank, amount, currency,
                   exp_date.strftime("%d/%m/%Y"), total_recv, contacted, interest, notes]
            append_row("Redemptions", row)
            log_action(current_user(), "הוסף פקדון פקוע ידנית", name)
            st.success(f"✓ {name} נוסף")
            st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# Table + KPIs
# ══════════════════════════════════════════════════════════════════════════════
df = read_df("Redemptions")

# Ensure all expected columns exist
for col in REDEMP_COLS:
    if col not in df.columns:
        df[col] = ""

if df.empty:
    st.info("אין פקדונות פקועים עדיין.")
else:
    total = len(df)
    hot   = len(df[df["פנינו לגבי חדש"].isin(["מעוניין", "בשיחה"])]) if "פנינו לגבי חדש" in df.columns else 0
    try:
        total_freed = pd.to_numeric(df["סכום + קופון"].astype(str).str.replace(",", ""), errors="coerce").fillna(0).sum()
    except Exception:
        total_freed = 0

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f"""<div style='background:#D6EEF2;border-radius:8px;padding:.75rem 1rem;direction:rtl;'>
          <div style='font-size:.85rem;color:#1F6B75;'>פקדונות שפקעו</div>
          <div style='font-size:2rem;font-weight:700;color:#1F6B75;'>{total}</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div style='background:#C6EFCE;border-radius:8px;padding:.75rem 1rem;direction:rtl;'>
          <div style='font-size:.85rem;color:#1A7A4A;'>בשיחה / מעוניין</div>
          <div style='font-size:2rem;font-weight:700;color:#1A7A4A;'>{hot}</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div style='background:#D6EEF2;border-radius:8px;padding:.75rem 1rem;direction:rtl;'>
          <div style='font-size:.85rem;color:#1F6B75;'>סכום כולל שהתקבל</div>
          <div style='font-size:1.5rem;font-weight:700;color:#1F6B75;'>₪{total_freed:,.0f}</div>
        </div>""", unsafe_allow_html=True)

    st.divider()

    # ── Tabs: grouped view vs flat list ──────────────────────────────────────
    tab_grouped, tab_flat = st.tabs(["📊 לפי פקדון (ISIN)", "📋 כל הרשימה"])

    def color_interest(val):
        colors = {"גבוהה": "background-color:#C6EFCE", "בינונית": "background-color:#FFF2CC", "נמוכה": "background-color:#FDEBD0"}
        return colors.get(val, "")

    with tab_grouped:
        if "ISIN" in df.columns:
            # Build grouped summary
            df_num = df.copy()
            df_num["סכום"] = pd.to_numeric(df_num["סכום"].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
            df_num["סכום + קופון"] = pd.to_numeric(df_num["סכום + קופון"].astype(str).str.replace(",", ""), errors="coerce").fillna(0)

            grouped = (
                df_num.groupby("ISIN", as_index=False)
                .agg(
                    מנפיק=("בנק מנפיק", lambda x: x.mode().iloc[0] if not x.mode().empty else ""),
                    משקיעים=("שם לקוח", "count"),
                    סכום_מקורי=("סכום", "sum"),
                    סכום_וקופון=("סכום + קופון", "sum"),
                    חמים=("רמת עניין", lambda x: (x.isin(["גבוהה", "בינונית"])).sum()),
                )
            )
            grouped.columns = ["ISIN", "מנפיק", "מספר משקיעים", "סכום מקורי", "סכום + קופון", "לידים חמים"]
            grouped["סכום מקורי"] = grouped["סכום מקורי"].apply(lambda x: f"₪{x:,.0f}")
            grouped["סכום + קופון"] = grouped["סכום + קופון"].apply(lambda x: f"₪{x:,.0f}" if x > 0 else "—")

            st.dataframe(grouped, use_container_width=True, hide_index=True)

            # Drill-down: show investors for selected ISIN
            isin_list = grouped["ISIN"].tolist()
            sel_isin = st.selectbox("בחר ISIN לפירוט משקיעים", ["— בחר —"] + isin_list, key="grouped_drill")
            if sel_isin != "— בחר —":
                drill_df = df[df["ISIN"] == sel_isin][REDEMP_COLS].copy()
                st.dataframe(drill_df, use_container_width=True, hide_index=True)

                # Excel export for specific ISIN
                buf = io.BytesIO()
                with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                    drill_df.to_excel(writer, index=False, sheet_name="פקדון פקוע")
                st.download_button(
                    f"📥 ייצוא Excel — {sel_isin}",
                    buf.getvalue(),
                    f"redemption_{sel_isin}.xlsx",
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dl_isin_excel"
                )
        else:
            st.info("אין נתוני ISIN בטבלה.")

    with tab_flat:
        display_df = df[REDEMP_COLS].copy()
        styled = display_df.style.map(color_interest, subset=["רמת עניין"] if "רמת עניין" in display_df.columns else [])
        st.dataframe(styled, use_container_width=True, height=350)

        # Export buttons
        exp_c1, exp_c2 = st.columns(2)
        with exp_c1:
            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as writer:
                display_df.to_excel(writer, index=False, sheet_name="פקדונות פקועים")
            st.download_button(
                "📥 ייצוא Excel",
                buf.getvalue(),
                "redemptions.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_all_excel"
            )
        with exp_c2:
            csv = display_df.to_csv(index=False, encoding="utf-8-sig")
            st.download_button("📥 ייצוא CSV", csv, "redemptions.csv", "text/csv", key="dl_all_csv")

    st.divider()

    # ── Move to Pipeline ──────────────────────────────────────────────────────
    st.markdown("### 🚀 העברה לפייפליין")
    st.caption("בחר משקיעים ברמת עניין גבוהה/בינונית והוסף אותם ישירות לפייפליין הגיוס.")

    all_names = df["שם לקוח"].dropna().tolist() if "שם לקוח" in df.columns else []
    hot_names = df[df["רמת עניין"].isin(["גבוהה", "בינונית"])]["שם לקוח"].tolist() if "רמת עניין" in df.columns else []

    filter_hot = st.checkbox("הצג לידים חמים בלבד (גבוהה/בינונית)", value=True)
    name_options = hot_names if filter_hot else all_names

    if name_options:
        selected_for_pipeline = st.multiselect(
            "בחר משקיעים להעברה לפייפליין",
            name_options,
            key="pipeline_transfer_select"
        )

        if selected_for_pipeline:
            # Check which already exist in pipeline
            existing_pipeline = read_df("Pipeline")
            already_in_pipeline = set()
            if not existing_pipeline.empty and "שם לקוח" in existing_pipeline.columns:
                already_in_pipeline = set(existing_pipeline["שם לקוח"].dropna().tolist())

            new_to_add = [n for n in selected_for_pipeline if n not in already_in_pipeline]
            duplicates = [n for n in selected_for_pipeline if n in already_in_pipeline]

            if duplicates:
                st.caption(f"ℹ️ כבר בפייפליין: {', '.join(duplicates)}")

            btn_label = f"→ הוסף {len(new_to_add)} משקיעים לפייפליין" if new_to_add else "כולם כבר בפייפליין"
            btn_disabled = len(new_to_add) == 0

            if st.button(btn_label, type="primary", use_container_width=True,
                         disabled=btn_disabled, key="transfer_to_pipeline_btn"):
                added_count = 0
                for name in new_to_add:
                    row_data = df[df["שם לקוח"] == name].iloc[0]
                    isin_val = str(row_data.get("ISIN", "")) if "ISIN" in df.columns else ""
                    amt_val  = row_data.get("סכום", 0)
                    try:
                        amt_val = int(float(str(amt_val).replace(",", "")))
                    except Exception:
                        amt_val = 0
                    currency_val = str(row_data.get("מטבע", "ILS"))
                    interest_val = str(row_data.get("רמת עניין", "בינונית"))
                    notes_val    = f"משקיע חוזר — פקד לו {isin_val}" if isin_val else "משקיע חוזר"

                    pipeline_row = [
                        name,                                   # שם לקוח
                        "",                                     # טלפון
                        current_user(),                         # דרך נציג
                        "A",                                    # כלי
                        isin_val,                               # ISIN פקדון
                        amt_val,                                # סכום משוער
                        currency_val,                           # מטבע
                        interest_val,                           # רמת וודאות
                        date.today().strftime("%d/%m/%Y"),      # תאריך פנייה
                        "לא פנו",                               # סטטוס
                        notes_val,                              # הערות
                    ]
                    append_row("Pipeline", pipeline_row)
                    added_count += 1

                log_action(current_user(), "העברה לפייפליין", f"{added_count} משקיעים חוזרים")
                st.success(f"✓ {added_count} משקיעים נוספו לפייפליין! עבור לדף פייפליין לצפייה.")
    else:
        st.info("אין לידים חמים להעברה. עדכן רמת עניין למשקיעים רלוונטיים.")

# ══════════════════════════════════════════════════════════════════════════════
# Quick update
# ══════════════════════════════════════════════════════════════════════════════
full_df = read_df("Redemptions")
if not full_df.empty and "שם לקוח" in full_df.columns:
    st.markdown("---")
    st.markdown("#### עדכון מהיר")
    names   = full_df["שם לקוח"].tolist()
    sel     = st.selectbox("בחר לקוח", names, key="red_sel")
    row_idx = full_df[full_df["שם לקוח"] == sel].index[0]

    c1, c2 = st.columns(2)
    with c1:
        cur_isin    = full_df.at[row_idx, "ISIN"] if "ISIN" in full_df.columns else ""
        new_isin    = st.text_input("ISIN", value=str(cur_isin), key="upd_isin")
        cur_recv    = full_df.at[row_idx, "סכום + קופון"] if "סכום + קופון" in full_df.columns else ""
        new_recv    = st.text_input("סכום + קופון שהתקבל", value=str(cur_recv), key="upd_recv")
        cur_contact = full_df.at[row_idx, "פנינו לגבי חדש"] if "פנינו לגבי חדש" in full_df.columns else "לא"
        new_contact = st.selectbox("פנינו לגבי פקדון חדש", CONTACT_STATUS,
            index=CONTACT_STATUS.index(cur_contact) if cur_contact in CONTACT_STATUS else 0)
    with c2:
        cur_interest = full_df.at[row_idx, "רמת עניין"] if "רמת עניין" in full_df.columns else "נמוכה"
        new_interest = st.selectbox("רמת עניין", CONFIDENCE,
            index=CONFIDENCE.index(cur_interest) if cur_interest in CONFIDENCE else 0)
        new_notes   = st.text_input("הערות", value=str(full_df.at[row_idx, "הערות"]) if "הערות" in full_df.columns else "")

    if st.button("✓ עדכן", use_container_width=True, type="primary"):
        full_df.at[row_idx, "ISIN"]             = new_isin
        full_df.at[row_idx, "סכום + קופון"]    = new_recv
        full_df.at[row_idx, "פנינו לגבי חדש"]  = new_contact
        full_df.at[row_idx, "רמת עניין"]        = new_interest
        full_df.at[row_idx, "הערות"]            = new_notes
        write_df("Redemptions", full_df)
        log_action(current_user(), "עדכון פקדון פקוע", sel)
        st.success("✓ עודכן")
        st.rerun()
