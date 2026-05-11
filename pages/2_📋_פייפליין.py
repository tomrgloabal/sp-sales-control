import streamlit as st
import pandas as pd
from datetime import date
from auth import require_login, current_user
from sheets import read_df, write_df, append_row, log_action
from config import CONFIDENCE, CURRENCIES, TOOLS, TOOL_DESCRIPTIONS, PIPELINE_STATUS, USERS, PIPELINE_COLS

require_login()

st.markdown("""<style>.stApp{direction:rtl;} header[data-testid="stHeader"]{display:none;}</style>""", unsafe_allow_html=True)
st.markdown("<h2 style='color:#003327;'>📋 פייפליין — מאגר לקוחות</h2>", unsafe_allow_html=True)
st.caption("לקוחות שמוכנים מראש. כשהפקדון יוצא — אלה הראשונים שפונים אליהם.")


def _active_isins() -> list[str]:
    """Return list of active ISINs from Products tab."""
    df = read_df("Products")
    if df.empty or "ISIN" not in df.columns:
        # Fall back to single product
        p = read_df("Product")
        if not p.empty and "שדה" in p.columns:
            d = dict(zip(p["שדה"], p["ערך"]))
            isin = d.get("ISIN", "")
            return [isin] if isin else []
        return []
    active = df[df["סטטוס"].isin(["פעיל", ""])] if "סטטוס" in df.columns else df
    return active["ISIN"].dropna().tolist()


# ── Returning investor lookup ─────────────────────────────────────────────────
def _all_known_investors() -> dict[str, dict]:
    """Return {name: {bank, amount, currency, ...}} from ProductInvestors archive."""
    from pathlib import Path
    import json
    inv_file = Path(__file__).parent.parent / "local_data" / "ProductInvestors.json"
    if not inv_file.exists():
        return {}
    db = json.loads(inv_file.read_text(encoding="utf-8"))
    known: dict[str, dict] = {}
    for isin, data in db.items():
        for inv in data["משקיעים"]:
            name = inv["שם המשקיע"]
            if name not in known:
                known[name] = {
                    "בנק": inv.get("בנק", ""),
                    "סכום": inv.get("סכום", 0),
                    "מטבע": inv.get("מטבע", "ILS"),
                    "שותף": inv.get("שותף", ""),
                    "ISIN": isin,
                }
    return known

known_investors = _all_known_investors()

if known_investors:
    with st.expander("🔄 חיפוש משקיע חוזר", expanded=False):
        st.caption("משקיע שהיה בפקדון ישן — המערכת תמלא פרטים אוטומטית")
        search_name = st.text_input("הקלד שם לחיפוש", key="returning_search", placeholder="שם משקיע...")
        if search_name:
            matches = {k: v for k, v in known_investors.items() if search_name.strip().lower() in k.lower()}
            if matches:
                for inv_name, inv_data in list(matches.items())[:5]:
                    col_info, col_btn = st.columns([4, 1])
                    with col_info:
                        st.markdown(f"**{inv_name}** — {inv_data['מטבע']} {inv_data['סכום']:,.0f} | בנק: {inv_data['בנק']} | ISIN: {inv_data['ISIN']}")
                    with col_btn:
                        if st.button("טען →", key=f"load_{inv_name}"):
                            st.session_state["prefill_name"]     = inv_name
                            st.session_state["prefill_bank"]     = inv_data["בנק"]
                            st.session_state["prefill_amount"]   = int(inv_data["סכום"])
                            st.session_state["prefill_currency"] = inv_data["מטבע"]
                            st.session_state["prefill_isin"]     = inv_data["ISIN"]
                            st.rerun()
            else:
                st.caption("לא נמצאו תוצאות")

# Pre-fill from session state — inject into widget keys so value= doesn't override
# Check BEFORE popping which keys were actually set by another page
_had_pf_name     = "prefill_name"     in st.session_state
_had_pf_amount   = "prefill_amount"   in st.session_state
_had_pf_currency = "prefill_currency" in st.session_state
_had_pf_isin     = "prefill_isin"     in st.session_state

_pf_name     = st.session_state.pop("prefill_name",     "")
_pf_bank     = st.session_state.pop("prefill_bank",     "")
_pf_amount   = st.session_state.pop("prefill_amount",   0)
_pf_currency = st.session_state.pop("prefill_currency", "ILS")
_pf_isin     = st.session_state.pop("prefill_isin",     "")

# Inject ONLY when there was a real prefill — never overwrite user's current input
if _had_pf_name     and _pf_name:   st.session_state["al_name"]     = _pf_name
if _had_pf_amount   and _pf_amount: st.session_state["al_amount"]   = _pf_amount
if _had_pf_currency:                st.session_state["al_currency"] = _pf_currency
if _had_pf_isin     and _pf_isin:   st.session_state["al_isin"]     = _pf_isin

# ── Add lead ──────────────────────────────────────────────────────────────────
with st.expander("➕ הוספת ליד חדש", expanded=True):
    with st.form("add_lead"):
        c1, c2 = st.columns(2)
        with c1:
            st.text_input("שם לקוח *", key="al_name")
            st.text_input("טלפון",      key="al_phone")
            st.selectbox("דרך נציג", USERS, key="al_agent")
            st.selectbox("כלי", ["A — נציג מורשה", "B — סוכן ביטוח"], key="al_tool")
        with c2:
            isins = _active_isins()
            if _pf_isin and _pf_isin not in isins:
                isins = [_pf_isin] + isins
            isin_options = isins + ["— כללי —"] if isins else ["— כללי —"]
            st.selectbox("פקדון (ISIN)", isin_options, key="al_isin")
            st.number_input("סכום משוער", min_value=0, step=50000, key="al_amount")
            st.selectbox("מטבע", CURRENCIES, key="al_currency")
            st.selectbox("רמת וודאות", CONFIDENCE, key="al_conf")
            st.date_input("תאריך פנייה", key="al_date")
            st.selectbox("סטטוס", PIPELINE_STATUS, key="al_status")
        st.text_area("הערות", key="al_notes")
        submitted = st.form_submit_button("➕ הוסף ליד", use_container_width=True, type="primary")

    if submitted:
        # Read values directly from session_state — most reliable approach in Streamlit
        name_val     = str(st.session_state.get("al_name", "")).strip()
        phone_val    = str(st.session_state.get("al_phone", ""))
        agent_val    = str(st.session_state.get("al_agent", USERS[0]))
        tool_raw     = str(st.session_state.get("al_tool", "A — נציג מורשה"))
        isin_sel     = str(st.session_state.get("al_isin", "— כללי —"))
        amount_val   = st.session_state.get("al_amount", 0)
        currency_val = str(st.session_state.get("al_currency", "ILS"))
        conf_val     = str(st.session_state.get("al_conf", "בינונית"))
        date_val     = st.session_state.get("al_date", date.today())
        status_val   = str(st.session_state.get("al_status", "לא פנו"))
        notes_val    = str(st.session_state.get("al_notes", ""))

        if not name_val:
            st.error("שם לקוח חובה")
        else:
            try:
                tool_final = "A" if tool_raw.startswith("A") else "B"
                isin_final = isin_sel if isin_sel != "— כללי —" else ""
                date_str   = date_val.strftime("%d/%m/%Y") if hasattr(date_val, "strftime") else str(date_val)
                today = date.today().strftime("%d/%m/%Y")
                row = [name_val, phone_val, agent_val, tool_final, isin_final,
                       amount_val, currency_val, conf_val, date_str, status_val, notes_val, today]
                append_row("Pipeline", row)
                log_action(current_user(), "הוסף ליד לפייפליין", name_val)
                st.success(f"✓ {name_val} נוסף לפייפליין")
                st.rerun()
            except Exception as e:
                st.error(f"שגיאה בשמירה: {e}")

# Tool A/B info box
with st.expander("💡 מה ההבדל בין כלי A ל-B?", expanded=False):
    st.markdown(f"""
| כלי | מי | מה מותר |
|-----|----|---------|
| **A** | נציג מורשה (תום, רון, אורן) | שיווק מלא — פרטי מוצר, תשואה, מחסום, ISIN |
| **B** | סוכן ביטוח (75 סוכנים) | **הסבר כללי בלבד** — מה זה פקדון מובנה, למה זה מעניין. **אסור:** שם מנפיק, אחוז תשואה, שם מניות ספציפיות. חובה להפנות לנציג מורשה לסגירה |

> ⚠️ לפי חוק ניירות ערך: סוכן ביטוח ללא רישיון שמציע ני"ע עובר עבירה פלילית.
""")

# ── Filters ───────────────────────────────────────────────────────────────────
st.markdown("---")
fc1, fc2, fc3, fc4 = st.columns(4)
with fc1:
    filter_conf = st.multiselect("וודאות", CONFIDENCE, default=CONFIDENCE)
with fc2:
    filter_status = st.multiselect("סטטוס", PIPELINE_STATUS, default=PIPELINE_STATUS)
with fc3:
    filter_agent = st.multiselect("נציג", USERS, default=USERS)
with fc4:
    filter_tool = st.multiselect("כלי", ["A", "B"], default=["A", "B"])

# ── Table ─────────────────────────────────────────────────────────────────────
df = read_df("Pipeline")

if df.empty:
    st.info("הפייפליין ריק. הוסף ליד ראשון.")
else:
    for col in PIPELINE_COLS:
        if col not in df.columns:
            df[col] = ""

    if filter_conf and "רמת וודאות" in df.columns:
        df = df[df["רמת וודאות"].isin(filter_conf)]
    if filter_status and "סטטוס" in df.columns:
        df = df[df["סטטוס"].isin(filter_status)]
    if filter_agent and "דרך נציג" in df.columns:
        df = df[df["דרך נציג"].isin(filter_agent)]
    if filter_tool and "כלי" in df.columns:
        df = df[df["כלי"].isin(filter_tool)]

    # ── Status funnel ─────────────────────────────────────────────────────────
    if "סטטוס" in df.columns:
        funnel_cols = st.columns(len(PIPELINE_STATUS))
        funnel_colors = {"לא פנו": "#EEF0F8", "בשיחה": "#FFF2CC", "מעוניין": "#C6EFCE", "לא מעוניין": "#FDEBD0"}
        for fc, status in zip(funnel_cols, PIPELINE_STATUS):
            cnt = len(df[df["סטטוס"] == status])
            with fc:
                st.markdown(f"""<div style='background:{funnel_colors.get(status,"#eee")};
                    border-radius:8px; padding:.6rem .5rem; text-align:center; margin-bottom:.4rem;'>
                  <div style='font-size:1.5rem; font-weight:700; color:#003327;'>{cnt}</div>
                  <div style='font-size:.72rem; color:#555;'>{status}</div>
                </div>""", unsafe_allow_html=True)

    st.caption(f"מציג {len(df)} לידים")

    def style_conf(val):
        colors = {"גבוהה": "background-color:#C6EFCE", "בינונית": "background-color:#FFF2CC", "נמוכה": "background-color:#FDEBD0"}
        return colors.get(val, "")

    display_df = df[PIPELINE_COLS].copy() if all(c in df.columns for c in PIPELINE_COLS) else df
    styled = display_df.style.map(style_conf, subset=["רמת וודאות"] if "רמת וודאות" in display_df.columns else [])
    st.dataframe(styled, use_container_width=True, height=400)

    # ── Totals by currency ────────────────────────────────────────────────────
    if "סכום משוער" in df.columns and "מטבע" in df.columns:
        def _to_num(v):
            try: return float(str(v).replace(",","").strip() or 0)
            except: return 0.0
        df_t = df.copy()
        df_t["_n"] = df_t["סכום משוער"].apply(_to_num)
        tc1, tc2, tc3 = st.columns(3)
        for col_obj, cur, sym in [(tc1,"ILS","₪"), (tc2,"USD","$"), (tc3,"EUR","€")]:
            sub  = df_t[df_t["מטבע"] == cur]
            tot  = sub["_n"].sum()
            cnt  = len(sub)
            with col_obj:
                st.metric(f"סה\"כ {cur}", f"{sym}{tot:,.0f}", f"{cnt} לידים")

    # ── Per-agent breakdown ───────────────────────────────────────────────────
    if "דרך נציג" in df.columns and "סכום משוער" in df.columns:
        with st.expander("👤 פירוט לפי נציג"):
            agent_rows = []
            for agent in sorted(df["דרך נציג"].dropna().unique()):
                adf = df[df["דרך נציג"] == agent]
                adf_t = adf.copy()
                adf_t["_n"] = adf_t["סכום משוער"].apply(lambda v: float(str(v).replace(",","").strip() or 0) if pd.notna(v) else 0)
                for cur, sym in [("ILS","₪"),("USD","$"),("EUR","€")]:
                    sub = adf_t[adf_t["מטבע"] == cur] if "מטבע" in adf_t.columns else pd.DataFrame()
                    if len(sub):
                        agent_rows.append({"נציג": agent, "מטבע": cur,
                                           "לידים": len(sub),
                                           "סה\"כ": f"{sym}{sub['_n'].sum():,.0f}",
                                           "מעוניין": len(sub[sub["סטטוס"]=="מעוניין"]) if "סטטוס" in sub.columns else 0})
            if agent_rows:
                st.dataframe(pd.DataFrame(agent_rows), hide_index=True, use_container_width=True)

    csv = df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button("📥 ייצוא CSV", csv, "pipeline.csv", "text/csv")

# ── Edit row ──────────────────────────────────────────────────────────────────
full_df = read_df("Pipeline")
if not full_df.empty and "שם לקוח" in full_df.columns:
    st.markdown("---")
    st.markdown("#### עריכת ליד קיים")
    names = full_df["שם לקוח"].tolist()
    sel_name = st.selectbox("בחר לקוח לעריכה", names, key="edit_sel")
    row_idx = full_df[full_df["שם לקוח"] == sel_name].index[0]
    row_data = full_df.loc[row_idx]

    with st.form("edit_lead"):
        c1, c2 = st.columns(2)
        with c1:
            cur_agent = str(row_data.get("דרך נציג", USERS[0]))
            new_agent = st.selectbox("דרך נציג", USERS,
                index=USERS.index(cur_agent) if cur_agent in USERS else 0)
            new_status = st.selectbox("סטטוס", PIPELINE_STATUS,
                index=PIPELINE_STATUS.index(row_data.get("סטטוס", PIPELINE_STATUS[0])) if row_data.get("סטטוס") in PIPELINE_STATUS else 0)
            new_conf = st.selectbox("רמת וודאות", CONFIDENCE,
                index=CONFIDENCE.index(row_data.get("רמת וודאות", CONFIDENCE[0])) if row_data.get("רמת וודאות") in CONFIDENCE else 0)
        with c2:
            cur_currency = str(row_data.get("מטבע", "ILS"))
            new_currency = st.selectbox("מטבע", CURRENCIES,
                index=CURRENCIES.index(cur_currency) if cur_currency in CURRENCIES else 0)
            cur_amount = int(row_data.get("סכום משוער", 0) or 0)
            new_amount = st.number_input("סכום משוער", min_value=0, step=50000, value=cur_amount)
            new_notes = st.text_area("הערות", value=str(row_data.get("הערות", "")))
        save = st.form_submit_button("שמור שינויים", use_container_width=True)

    if save:
        full_df.at[row_idx, "דרך נציג"]    = new_agent
        full_df.at[row_idx, "סטטוס"]       = new_status
        full_df.at[row_idx, "רמת וודאות"]  = new_conf
        full_df.at[row_idx, "מטבע"]         = new_currency
        full_df.at[row_idx, "סכום משוער"]  = new_amount
        full_df.at[row_idx, "הערות"]        = new_notes
        full_df.at[row_idx, "עדכון אחרון"] = date.today().strftime("%d/%m/%Y")
        write_df("Pipeline", full_df)
        log_action(current_user(), "עדכון ליד", sel_name)
        st.success("✓ נשמר")
        st.rerun()

    # ── Delete lead ───────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### מחיקת ליד")

    if "confirm_delete" not in st.session_state:
        st.session_state["confirm_delete"] = False

    if not st.session_state["confirm_delete"]:
        if st.button(f"🗑️ מחק את '{sel_name}' מהפייפליין", use_container_width=True):
            st.session_state["confirm_delete"] = True
            st.rerun()
    else:
        st.warning(f"⚠️ בטוח שרוצה למחוק את **{sel_name}**? פעולה זו אינה הפיכה.")
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("✅ כן, מחק", type="primary", use_container_width=True):
                updated_df = full_df.drop(index=row_idx).reset_index(drop=True)
                write_df("Pipeline", updated_df)
                log_action(current_user(), "מחיקת ליד", sel_name)
                st.session_state["confirm_delete"] = False
                st.success(f"✓ {sel_name} נמחק מהפייפליין")
                st.rerun()
        with col_no:
            if st.button("❌ ביטול", use_container_width=True):
                st.session_state["confirm_delete"] = False
                st.rerun()
