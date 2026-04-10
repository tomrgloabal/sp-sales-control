"""
ארכיון גיוסים — תצוגת כל הגיוסים ההיסטוריים מהתיקייה
"""
import re
import streamlit as st
import pandas as pd
from pathlib import Path
from auth import require_login, current_user
from sheets import read_df

require_login()

st.markdown("""<style>.stApp{direction:rtl;} header[data-testid="stHeader"]{display:none;}</style>""", unsafe_allow_html=True)
st.markdown("<h2 style='color:#1E2761;'>📁 ארכיון גיוסים היסטוריים</h2>", unsafe_allow_html=True)
st.caption("כל גיוסי העבר לפי תאריך. ניתן לראות קבצים, tickets ו-term sheets לכל גיוס.")

BANKS_DIR  = Path(__file__).parent.parent / "בנקים"
GIYUSIM_DIR = BANKS_DIR / "גיוסים"

ISIN_RE = re.compile(r'(XS\d{10})', re.IGNORECASE)

EXT_ICONS = {"pdf": "📄", "docx": "📝", "doc": "📝", "xlsx": "📊", "msg": "📧", "jpg": "🖼️", "png": "🖼️"}


def _extract_isin(text: str) -> str | None:
    m = ISIN_RE.search(text)
    return m.group(1).upper() if m else None


def _scan_round(round_dir: Path) -> dict:
    """Return {isin_or_None, files: [...], subdirs: {name: files}}"""
    isins: set[str] = set()
    all_files: list[str] = []
    subdirs: dict[str, list[str]] = {}

    for item in sorted(round_dir.iterdir()):
        if item.is_file():
            all_files.append(item.name)
            isin = _extract_isin(item.name)
            if isin:
                isins.add(isin)
        elif item.is_dir():
            sub_files = [f.name for f in sorted(item.iterdir()) if f.is_file()]
            subdirs[item.name] = sub_files
            all_files.extend(sub_files)
            for f in sub_files:
                isin = _extract_isin(f)
                if isin:
                    isins.add(isin)

    return {"isins": isins, "files": all_files, "subdirs": subdirs}


# ── Load investors DB for ISIN cross-reference ────────────────────────────────
investors_db: dict = {}
inv_file = Path(__file__).parent.parent / "local_data" / "ProductInvestors.json"
if inv_file.exists():
    import json
    investors_db = json.loads(inv_file.read_text(encoding="utf-8"))

# ── Main content ──────────────────────────────────────────────────────────────
if not GIYUSIM_DIR.exists():
    st.info("תיקיית 'בנקים/גיוסים' לא נמצאה. ודא שתיקיית 'בנקים' קיימת בתיקיית sp-sales-app.")
    st.stop()

# Scan all round folders
round_folders = sorted(
    [d for d in GIYUSIM_DIR.iterdir() if d.is_dir()],
    reverse=True  # newest first
)

# Summary metrics
total_rounds = len(round_folders)
total_isins = set()
for rf in round_folders:
    scan = _scan_round(rf)
    total_isins.update(scan["isins"])

c1, c2, c3 = st.columns(3)
with c1:
    st.metric("סה\"כ גיוסים", total_rounds)
with c2:
    st.metric("ISINs ייחודיים", len(total_isins))
with c3:
    archive_investors = len(investors_db)
    st.metric("משקיעים בארכיון", archive_investors)

st.divider()

# ── ISIN quick search ─────────────────────────────────────────────────────────
search_isin = st.text_input("🔍 חיפוש לפי ISIN", placeholder="XS3293111806").strip().upper()

# ── Round list ────────────────────────────────────────────────────────────────
for rf in round_folders:
    scan = _scan_round(rf)
    isins = scan["isins"]
    all_files = scan["files"]

    # Filter if searching
    if search_isin:
        if search_isin not in isins:
            continue

    # Title with ISIN badges
    isin_tags = "  ".join([f"`{i}`" for i in sorted(isins)]) if isins else ""
    label = f"📅 **{rf.name}** — {len(all_files)} קבצים {isin_tags}"

    with st.expander(label, expanded=bool(search_isin)):
        # Show ISIN details from archive
        for isin in sorted(isins):
            if isin in investors_db:
                prod = investors_db[isin]
                inv_count = len(prod["משקיעים"])
                total_raised = sum(i["סכום"] for i in prod["משקיעים"])
                st.markdown(
                    f"<div style='background:#D6EEF2; border-radius:8px; padding:.6rem 1rem; direction:rtl; margin-bottom:.5rem;'>"
                    f"<b>{isin}</b> — {prod['שם מלא'][:70]}<br>"
                    f"<small>מנפיק: {prod['מנפיק']} | {inv_count} משקיעים | ₪{total_raised:,.0f}</small>"
                    f"</div>",
                    unsafe_allow_html=True
                )

        # Files in root
        root_files = scan["files"][:50]  # limit display
        if root_files:
            cols = st.columns(2)
            for i, fname in enumerate(root_files):
                ext = fname.split(".")[-1].lower() if "." in fname else ""
                icon = EXT_ICONS.get(ext, "📎")
                cols[i % 2].markdown(f"{icon} {fname}")

        # Subdirs
        for sub_name, sub_files in scan["subdirs"].items():
            if sub_files:
                st.markdown(f"**📂 {sub_name}:**")
                sub_cols = st.columns(2)
                for i, fname in enumerate(sub_files[:20]):
                    ext = fname.split(".")[-1].lower() if "." in fname else ""
                    icon = EXT_ICONS.get(ext, "📎")
                    sub_cols[i % 2].markdown(f"  {icon} {fname}")

# ── File-based extra info (the xlsx kit) ─────────────────────────────────────
kit_files = [f for f in GIYUSIM_DIR.iterdir() if f.is_file() and f.suffix == ".xlsx"]
if kit_files:
    st.divider()
    st.markdown("#### 📊 קבצי Excel בתיקיית הגיוסים")
    for f in kit_files:
        st.markdown(f"- 📊 **{f.name}**")

# ── Fundraising summary from internal DB ─────────────────────────────────────
st.divider()
with st.expander("📋 סיכום גיוסים מהארכיון הפנימי (גיוס סטראקצרים.xlsx)", expanded=False):
    if not investors_db:
        st.info("הארכיון ריק. לך לדף 7 — ארכיון פקדונות כדי לטעון מ-Excel.")
    else:
        rows = []
        for isin, data in investors_db.items():
            total_amount = sum(i["סכום"] for i in data["משקיעים"])
            currencies = list(set(i["מטבע"] for i in data["משקיעים"] if i["מטבע"]))
            rows.append({
                "ISIN": isin,
                "שם מוצר": data["שם מלא"][:60],
                "מנפיק": data["מנפיק"],
                "תאריך הנפקה": data["ISSUE DATE"],
                "# משקיעים": len(data["משקיעים"]),
                "סכום כולל": f'₪{total_amount:,.0f}' if total_amount else "—",
                "מטבעות": ", ".join(currencies),
            })
        df_summary = pd.DataFrame(rows).sort_values("תאריך הנפקה", ascending=False)
        st.dataframe(df_summary, use_container_width=True, hide_index=True)
