import io
import json
import streamlit as st
import pandas as pd
from pathlib import Path
from auth import require_login, current_user
from sheets import append_row, log_action
from config import PIPELINE_STATUS
from datetime import date

require_login()

st.markdown("""<style>.stApp{direction:rtl;} header[data-testid="stHeader"]{display:none;}</style>""", unsafe_allow_html=True)
st.markdown("<h2 style='color:#1E2761;'>🗂️ ארכיון משקיעים — לפי פקדון</h2>", unsafe_allow_html=True)
st.caption("כל המשקיעים שהיו בפקדונות בעבר, מאורגנים לפי מוצר. מקור: PRIVATAM.")

INV_FILE = Path(__file__).parent.parent / "local_data" / "ProductInvestors.json"


@st.cache_data(ttl=60)
def _load_archive() -> dict:
    if INV_FILE.exists():
        return json.loads(INV_FILE.read_text(encoding="utf-8"))
    return {}


archive = _load_archive()

if not archive:
    st.warning("הארכיון ריק. ייבא נתונים מ-PRIVATAM.")
    st.stop()

# ── Build summary table ──────────────────────────────────────────────────────
rows = []
for isin, prod in archive.items():
    investors = prod.get("משקיעים", [])
    total_ils = sum(i.get("סכום", 0) for i in investors if i.get("מטבע", "ILS") == "ILS")
    total_usd = sum(i.get("סכום", 0) for i in investors if i.get("מטבע") == "USD")
    rows.append({
        "ISIN":         isin,
        "שם מוצר":      prod.get("שם מלא", "")[:60],
        "מנפיק":        prod.get("מנפיק", "—"),
        "תאריך הנפקה":  prod.get("ISSUE DATE", ""),
        "משקיעים":      len(investors),
        "סכום ILS":     total_ils,
        "סכום USD":     total_usd,
    })

summary_df = pd.DataFrame(rows)
summary_df = summary_df.sort_values("תאריך הנפקה", ascending=False)

# ── Search / filter ──────────────────────────────────────────────────────────
col_search, col_currency = st.columns([3, 1])
with col_search:
    search = st.text_input("🔍 חיפוש לפי ISIN, שם מוצר, או מניה", placeholder="ISIN / AMD / META...")
with col_currency:
    cur_filter = st.selectbox("מטבע", ["הכל", "ILS", "USD"])

filtered = summary_df.copy()
if search:
    mask = (
        filtered["ISIN"].str.contains(search, case=False, na=False) |
        filtered["שם מוצר"].str.contains(search, case=False, na=False)
    )
    filtered = filtered[mask]
if cur_filter == "ILS":
    filtered = filtered[filtered["סכום ILS"] > 0]
elif cur_filter == "USD":
    filtered = filtered[filtered["סכום USD"] > 0]

# ── Summary KPIs ─────────────────────────────────────────────────────────────
k1, k2, k3, k4 = st.columns(4)
with k1:
    st.markdown(f"""<div style='background:#D6EEF2;border-radius:8px;padding:.6rem 1rem;direction:rtl;'>
      <div style='font-size:.8rem;color:#1F6B75;'>פקדונות בארכיון</div>
      <div style='font-size:1.8rem;font-weight:700;color:#1F6B75;'>{len(filtered)}</div>
    </div>""", unsafe_allow_html=True)
with k2:
    total_investors = filtered["משקיעים"].sum()
    st.markdown(f"""<div style='background:#D6EEF2;border-radius:8px;padding:.6rem 1rem;direction:rtl;'>
      <div style='font-size:.8rem;color:#1F6B75;'>סה"כ השקעות</div>
      <div style='font-size:1.8rem;font-weight:700;color:#1F6B75;'>{total_investors}</div>
    </div>""", unsafe_allow_html=True)
with k3:
    total_ils = filtered["סכום ILS"].sum()
    st.markdown(f"""<div style='background:#C6EFCE;border-radius:8px;padding:.6rem 1rem;direction:rtl;'>
      <div style='font-size:.8rem;color:#1A7A4A;'>סה"כ ILS</div>
      <div style='font-size:1.4rem;font-weight:700;color:#1A7A4A;'>₪{total_ils:,.0f}</div>
    </div>""", unsafe_allow_html=True)
with k4:
    total_usd = filtered["סכום USD"].sum()
    st.markdown(f"""<div style='background:#C6EFCE;border-radius:8px;padding:.6rem 1rem;direction:rtl;'>
      <div style='font-size:.8rem;color:#1A7A4A;'>סה"כ USD</div>
      <div style='font-size:1.4rem;font-weight:700;color:#1A7A4A;'>${total_usd:,.0f}</div>
    </div>""", unsafe_allow_html=True)

st.divider()

# ── Summary table ────────────────────────────────────────────────────────────
display_summary = filtered.copy()
display_summary["סכום ILS"] = display_summary["סכום ILS"].apply(lambda x: f"₪{x:,.0f}" if x > 0 else "—")
display_summary["סכום USD"] = display_summary["סכום USD"].apply(lambda x: f"${x:,.0f}" if x > 0 else "—")

st.dataframe(display_summary, use_container_width=True, hide_index=True, height=300)

# Export summary
buf = io.BytesIO()
with pd.ExcelWriter(buf, engine="openpyxl") as writer:
    filtered.to_excel(writer, index=False, sheet_name="סיכום פקדונות")
st.download_button("📥 ייצוא סיכום Excel", buf.getvalue(), "archive_summary.xlsx",
                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

st.divider()

# ── Drill-down: investors per product ────────────────────────────────────────
st.markdown("### 🔎 פירוט משקיעים לפי פקדון")

isin_options = filtered["ISIN"].tolist()
if not isin_options:
    st.info("אין תוצאות לסינון הנוכחי.")
    st.stop()

sel_isin = st.selectbox("בחר פקדון לפירוט", isin_options,
                         format_func=lambda x: f"{x} — {archive[x]['שם מלא'][:50]}" if x in archive else x)

if sel_isin and sel_isin in archive:
    prod = archive[sel_isin]
    investors = prod.get("משקיעים", [])

    if not investors:
        st.info("אין משקיעים רשומים לפקדון זה.")
    else:
        inv_df = pd.DataFrame(investors)
        # Normalize column names
        col_map = {
            "שם המשקיע": "שם משקיע",
            "סכום": "סכום",
            "מטבע": "מטבע",
            "שותף": "שותף",
            "בנק": "בנק",
            "סטטוס": "סטטוס",
        }
        inv_df = inv_df.rename(columns={k: v for k, v in col_map.items() if k in inv_df.columns})

        # KPIs for this product
        p1, p2, p3 = st.columns(3)
        with p1:
            st.metric("משקיעים", len(inv_df))
        with p2:
            ils = inv_df[inv_df["מטבע"] == "ILS"]["סכום"].sum() if "מטבע" in inv_df.columns else 0
            st.metric("סכום ILS", f"₪{ils:,.0f}")
        with p3:
            usd = inv_df[inv_df["מטבע"] == "USD"]["סכום"].sum() if "מטבע" in inv_df.columns else 0
            st.metric("סכום USD", f"${usd:,.0f}")

        # Bank breakdown
        if "בנק" in inv_df.columns:
            bank_summary = inv_df.groupby("בנק").agg(
                משקיעים=("שם משקיע" if "שם משקיע" in inv_df.columns else inv_df.columns[0], "count"),
                סכום=("סכום", "sum"),
            ).reset_index()
            with st.expander("🏦 פירוט לפי בנק", expanded=True):
                st.dataframe(bank_summary, use_container_width=True, hide_index=True)

        # Full investor list
        st.markdown("**רשימת משקיעים:**")
        display_inv = inv_df.copy()
        if "סכום" in display_inv.columns:
            display_inv["סכום מפורמט"] = display_inv.apply(
                lambda r: f"₪{r['סכום']:,.0f}" if r.get("מטבע","ILS") == "ILS" else f"${r['סכום']:,.0f}",
                axis=1
            )
        st.dataframe(display_inv, use_container_width=True, hide_index=True)

        # Export this product's investors
        exp1, exp2 = st.columns(2)
        with exp1:
            buf2 = io.BytesIO()
            with pd.ExcelWriter(buf2, engine="openpyxl") as writer:
                inv_df.to_excel(writer, index=False, sheet_name="משקיעים")
            st.download_button(
                f"📥 Excel — {sel_isin}",
                buf2.getvalue(),
                f"investors_{sel_isin}.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_inv_excel"
            )
        with exp2:
            csv = inv_df.to_csv(index=False, encoding="utf-8-sig")
            st.download_button(f"📥 CSV — {sel_isin}", csv, f"investors_{sel_isin}.csv", "text/csv", key="dl_inv_csv")

        st.divider()

        # ── Transfer to Pipeline ──────────────────────────────────────────────
        st.markdown("### 🚀 העבר משקיעים מהארכיון לפייפליין")
        st.caption("בחר משקיעים מהפקדון הזה והוסף אותם לפייפליין הגיוס הנוכחי.")

        name_col = "שם משקיע" if "שם משקיע" in inv_df.columns else inv_df.columns[0]
        all_names = inv_df[name_col].dropna().tolist()

        selected = st.multiselect("בחר משקיעים", all_names, key="archive_pipeline_select")

        if selected:
            from sheets import read_df as _read_df
            existing_pipeline = _read_df("Pipeline")
            already_in = set()
            if not existing_pipeline.empty and "שם לקוח" in existing_pipeline.columns:
                already_in = set(existing_pipeline["שם לקוח"].dropna().tolist())

            new_to_add = [n for n in selected if n not in already_in]
            dups = [n for n in selected if n in already_in]

            if dups:
                st.caption(f"ℹ️ כבר בפייפליין: {', '.join(dups)}")

            if new_to_add:
                if st.button(f"→ הוסף {len(new_to_add)} משקיעים לפייפליין",
                             type="primary", use_container_width=True, key="archive_transfer_btn"):
                    added = 0
                    for name in new_to_add:
                        row_data = inv_df[inv_df[name_col] == name].iloc[0]
                        amt = row_data.get("סכום", 0)
                        try:
                            amt = int(float(str(amt).replace(",", "")))
                        except Exception:
                            amt = 0
                        cur = str(row_data.get("מטבע", "ILS"))
                        bank = str(row_data.get("בנק", ""))
                        partner = str(row_data.get("שותף", current_user()))

                        pipeline_row = [
                            name,
                            "",
                            partner if partner else current_user(),
                            "A",
                            sel_isin,
                            amt,
                            cur,
                            "בינונית",
                            date.today().strftime("%d/%m/%Y"),
                            "לא פנו",
                            f"משקיע ארכיון — {sel_isin} | בנק: {bank}",
                        ]
                        append_row("Pipeline", pipeline_row)
                        added += 1

                    log_action(current_user(), "העברה לפייפליין מארכיון", f"{sel_isin} | {added} משקיעים")
                    st.success(f"✓ {added} משקיעים נוספו לפייפליין!")
            else:
                st.info("כל הנבחרים כבר בפייפליין.")
