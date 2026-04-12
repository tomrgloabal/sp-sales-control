import re
import streamlit as st
import pandas as pd
from pathlib import Path
from auth import require_login, current_user
from sheets import read_df, write_df, log_action
from config import CURRENCIES, PRODUCTS_COLS

require_login()

st.markdown("""<style>.stApp{direction:rtl;} header[data-testid="stHeader"]{display:none;}</style>""", unsafe_allow_html=True)
st.markdown("<h2 style='color:#1E2761;'>📄 פקדונות פעילים</h2>", unsafe_allow_html=True)

TS_DIR = Path(__file__).parent.parent / "local_data" / "term_sheets"
TS_DIR.mkdir(exist_ok=True)


# ── Multi-product text parser ─────────────────────────────────────────────────
def _normalize_currency(raw: str) -> str:
    r = raw.upper().strip()
    if "EUR" in r or "EURO" in r:  return "EUR"
    if "USD" in r or "DOLLAR" in r: return "USD"
    if "ILS" in r or "NIS" in r:   return "ILS"
    return raw.strip() or "ILS"


def _parse_multi_ts(text: str) -> list:
    """Parse a pasted multi-product term sheet → list of product dicts (one per ISIN)."""
    # 1. Find all ISINs (preserve order, deduplicate)
    isins = list(dict.fromkeys(re.findall(r'\b((?:XS|CH)\d{10})\b', text)))
    if not isins:
        return []

    # 2. Shared fields
    issuer = _find(r'Issuer\s*[:\|]\s*([A-Za-z]+[\w\s,\.&-]{1,40}?)(?:\s*\n|\s*ISIN|\s*Size|\s*\|)', text)
    if not issuer:
        issuer = _find(r'Issuer\s*[:\|]\s*(\S+)', text)

    maturity = _find(r'Maturity\s*[:\|\t]+\s*(\d+)\s*[Mm]onths?', text)
    barrier  = _find(r'Barrier\s*[:\|\t]+\s*([\d\.]+%[^\n\|]{0,20})', text)
    obs_m    = _find(r'first\s+autocall[^\d]*(\d+)\s*[Mm]onths?', text) or \
               _find(r'Observations?[^\n]*?(\d+)\s*[Mm]onths?', text) or "6"
    ac_trig  = _find(r'Autocall\s+trigger\s*[:\|\t]+\s*([^\n\|]+)', text)

    # Underlyings — grab up to 3 lines after "Underlyings (Worst-Of)"
    und_block = re.search(
        r'Underlyings?\s*\(?Worst-Of\)?\s*[:\|\t]*\n?((?:(?!\n\n)[^\n]+\n?){1,6})',
        text, re.IGNORECASE)
    if und_block:
        raw_u = und_block.group(1)
        underlyings = [u.strip() for u in re.split(r'[\n/|]', raw_u) if u.strip()][:3]
    else:
        underlyings = []

    # 3. Build table from lines that have (n_isins + 1) pipe/tab-separated parts
    lines = text.replace('\t', '|').split('\n')
    table: dict = {}
    for line in lines:
        parts = [p.strip() for p in line.split('|') if p.strip()]
        if len(parts) >= len(isins) + 1:
            key = parts[0].lower().strip()
            table[key] = parts[1:]

    def _tval(keys: list, idx: int, default: str = "") -> str:
        for k in keys:
            for tk, tv in table.items():
                if k in tk and idx < len(tv):
                    return tv[idx]
        return default

    # 4. Build one dict per ISIN
    products = []
    for i, isin in enumerate(isins):
        coupon = _tval(['conditional memory coupon', 'guaranteed coupon', 'coupon'], i)
        currency = _normalize_currency(_tval(['currency'], i, "ILS"))
        notional = _tval(['notional', 'size', 'nominal'], i, "").replace("'", "").replace(",", "").replace(" ", "")

        p = {
            "ISIN":                           isin,
            "מנפיק":                           issuer,
            "נכסי בסיס":                      " / ".join(underlyings),
            'מח"מ (חודשים)':                  maturity,
            "מחסום":                           barrier,
            "קופון שנתי":                     coupon,
            "קופון חודשי":                    "",
            "מטבע":                           currency,
            "גודל עסקה":                      notional,
            "נכס בסיס 1":                     underlyings[0] if len(underlyings) > 0 else "",
            "נכס בסיס 2":                     underlyings[1] if len(underlyings) > 1 else "",
            "נכס בסיס 3":                     underlyings[2] if len(underlyings) > 2 else "",
            "תצפית Autocall ראשונה (חודש)":  obs_m,
            "לוח Autocall Triggers":          ac_trig,
            "תאריך Strike":                   "",
            "תאריך סגירת גיוס":               "",
            "הערות":                          "",
        }
        # Auto-compute monthly coupon if annual is present
        if p["קופון שנתי"] and not p["קופון חודשי"]:
            try:
                ann = float(p["קופון שנתי"].replace("%", "").strip())
                p["קופון חודשי"] = f"{ann/12:.2f}%"
            except Exception:
                pass
        products.append(p)
    return products


# ── PDF Parser ────────────────────────────────────────────────────────────────
def _extract_text(pdf_bytes: bytes) -> str:
    try:
        import pdfplumber, io
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages)
    except Exception:
        return ""


def _find(pattern: str, text: str, default: str = "") -> str:
    m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    return m.group(1).strip() if m else default


def _normalize_size(raw: str) -> str:
    """Convert '500K ILS', '1M USD', '500,000' → clean number string."""
    raw = raw.strip()
    m = re.match(r'([\d,\.]+)\s*([KkMm]?)', raw.replace("'", ""))
    if not m:
        return raw
    num_str = m.group(1).replace(",", "")
    suffix  = m.group(2).upper()
    try:
        num = float(num_str)
        if suffix == "K": num *= 1_000
        if suffix == "M": num *= 1_000_000
        return str(int(num))
    except Exception:
        return raw


def _parse_ts(text: str) -> dict:
    """Extract term-sheet fields from raw PDF text or free-text bullet format."""
    # Normalise bullet-point and tab formats → colon format for consistent parsing
    # • Key : Value  →  Key: Value
    # Key\tValue     →  Key: Value
    text = re.sub(r'^[•·\-\*]\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\t+', ': ', text)

    p = {}

    # ISIN — XS or CH followed by 10 digits
    p["ISIN"] = _find(r'\b((?:XS|CH)\d{10})\b', text)

    # Issuer — look for common patterns
    for pat in [
        r'Issuer[:\s]+([A-Za-z][\w\s,\.\(\)&-]{3,50}?)(?:\n|ISIN|Product)',
        r'Issued by[:\s]+([A-Za-z][\w\s,\.\(\)&-]{3,50}?)(?:\n|ISIN)',
        r'(Goldman Sachs[\w\s,\.]*)',
        r'(BNP Paribas[\w\s,\.]*)',
        r'(BBVA[\w\s,\.]*)',
        r'(Morgan Stanley[\w\s,\.]*)',
        r'(Citigroup[\w\s,\.]*)',
        r'(Barclays[\w\s,\.]*)',
        r'(Société Générale[\w\s,\.]*)',
        r'(UBS[\w\s,\.]*)',
    ]:
        val = _find(pat, text)
        if val:
            p["מנפיק"] = val[:60].strip().rstrip(",")
            break
    if "מנפיק" not in p:
        p["מנפיק"] = ""

    # Notional / Size
    for pat in [
        r"(?:Notional|Nominal|Size)[:\s]+([\d,.']+\s*[KkMm]?\s*(?:ILS|USD|EUR|CHF)?)",
        r"([\d,.']+\s*[KkMm])\s*(?:ILS|USD|EUR|CHF)",
        r'([\d,]+)\s*(?:ILS|USD|EUR)',
    ]:
        val = _find(pat, text)
        if val:
            # Strip trailing currency suffix before normalizing
            raw_size = re.sub(r'\s*(ILS|USD|EUR|CHF)\s*$', '', val.strip(), flags=re.IGNORECASE)
            p["גודל עסקה"] = _normalize_size(raw_size)
            break
    if "גודל עסקה" not in p:
        p["גודל עסקה"] = ""

    # Currency
    for cur in ["ILS", "USD", "EUR", "CHF"]:
        if cur in text:
            p["מטבע"] = cur
            break
    if "מטבע" not in p:
        p["מטבע"] = "ILS"

    # Maturity in months
    for pat in [
        r'Maturity[:\s]+(\d+)\s*[Mm]onths?',
        r'(\d+)[- ]month',
        r'Term[:\s]+(\d+)\s*[Mm]onths?',
        r'Tenor[:\s]+(\d+)\s*[Mm]onths?',
    ]:
        val = _find(pat, text)
        if val:
            p['מח"מ (חודשים)'] = val
            break
    if 'מח"מ (חודשים)' not in p:
        p['מח"מ (חודשים)'] = ""

    # Barrier / Capital Guarantee
    for pat in [
        r'CAPITALGUARANTEED[:\s]+([\d\.]+%)',
        r'Capital\s+[Gg]uarantee(?:d)?[:\s]+([\d\.]+%)',
        r'Barrier[:\s]+([\d\.]+%[^,\n]{0,30})',
        r'Capital [Pp]rotection[:\s]+([\d\.]+%)',
        r'([\d\.]+%)\s*(?:European|American)?\s*(?:Barrier|barrier)',
        r'Barrier Level[:\s]+([\d\.]+%)',
        r'Protection Level[:\s]+([\d\.]+%)',
        r'(100%)\s*Capital\s+[Gg]uarantee',
    ]:
        val = _find(pat, text)
        if val:
            p["מחסום"] = val.strip()
            break
    if "מחסום" not in p:
        p["מחסום"] = ""

    # Coupon annual
    for pat in [
        r'(?:Coupon\s+if\s+called[^:]*)[:\s]+([\d\.]+%)\s*p\.?a\.?',
        r'(?:Guaranteed\s+)?Coupon[:\s]+([\d\.]+%)\s*p\.?a\.?',
        r'(?:Annual\s+)?(?:Coupon|Yield)[:\s]+([\d\.]+%)\s*(?:per annum|p\.a\.)',
        r'([\d\.]+%)\s*(?:p\.a\.|per annum)',
        r'Coupon Rate[:\s]+([\d\.]+%)',
        r'Interest[:\s]+([\d\.]+%)\s*p\.a',
        r'(?:Coupon|Yield)[:\s]+([\d\.]+%)',
    ]:
        val = _find(pat, text)
        if val:
            p["קופון שנתי"] = val.strip()
            break
    if "קופון שנתי" not in p:
        p["קופון שנתי"] = ""

    # Monthly coupon (divide annual by 12 if not found separately)
    for pat in [
        r'(?:Monthly\s+)?Coupon[:\s]+([\d\.]+%)\s*(?:per month|p\.m\.)',
        r'([\d\.]+%)\s*per month',
        r'Monthly[:\s]+([\d\.]+%)',
    ]:
        val = _find(pat, text)
        if val:
            p["קופון חודשי"] = val.strip()
            break
    if "קופון חודשי" not in p and p.get("קופון שנתי"):
        try:
            annual_pct = float(p["קופון שנתי"].replace("%", "").strip())
            p["קופון חודשי"] = f"{annual_pct/12:.2f}%"
        except Exception:
            p["קופון חודשי"] = ""

    # Underlyings — look for stock tickers or company names
    und_text = ""
    for pat in [
        r"Underlying[s']?\s*\(?(?:WO|Worst[- ]Of)?\)?[:\s]+([A-Z\u05d0-\u05ea][^\n]{3,120})",
        r'Underlying[s]?[:\s]+([A-Z][^\n]{5,120})',
        r'Reference[s]?[:\s]+([A-Z][^\n]{5,80})',
        r'Worst[- ]of[:\s]+([A-Z][^\n]{5,80})',
        r'Basket[:\s]+([A-Z][^\n]{5,80})',
    ]:
        val = _find(pat, text)
        if val:
            und_text = val.strip()
            break

    # Also try to find ticker symbols (3-5 uppercase letters)
    if not und_text:
        tickers = re.findall(r'\b([A-Z]{2,5})\b', text)
        known_irrelevant = {"ISIN", "ILS", "USD", "EUR", "CHF", "GBP", "ATK", "BNP", "GS", "UBS", "IDD", "NVO", "ARM", "LLY", "AMD", "MU", "WDC", "META", "CRM", "SHOP"}
        tickers = [t for t in tickers if t not in known_irrelevant and len(t) >= 2]

    # Split underlyings into 1/2/3
    if und_text:
        parts = re.split(r'[/,&]|\s+-\s+|\s+and\s+|\s+AND\s+', und_text)
        parts = [p2.strip() for p2 in parts if p2.strip()]
        p["נכס בסיס 1"] = parts[0] if len(parts) > 0 else ""
        p["נכס בסיס 2"] = parts[1] if len(parts) > 1 else ""
        p["נכס בסיס 3"] = parts[2] if len(parts) > 2 else ""
    else:
        p["נכס בסיס 1"] = ""
        p["נכס בסיס 2"] = ""
        p["נכס בסיס 3"] = ""

    # First autocall observation month
    for pat in [
        r'[Ff]irst\s+observation\s+in[:\s]+(\d+)\s*[Mm]onths?',
        r'[Ff]irst\s+(?:[Aa]utocall|[Oo]bservation)[:\s]+(?:Month\s+)?(\d+)',
        r'[Cc]allability[^\n]*[Ff]irst\s+observation\s+in\s+(\d+)',
        r'[Aa]utocall[:\s]+M(\d+)',
        r'M(\d+)\s+100%',   # first trigger at 100%
    ]:
        val = _find(pat, text)
        if val:
            p["תצפית Autocall ראשונה (חודש)"] = val
            break
    if "תצפית Autocall ראשונה (חודש)" not in p:
        p["תצפית Autocall ראשונה (חודש)"] = "6"

    # Strike / Trade date
    for pat in [
        r'[Ss]trike\s+[Dd]ate[:\s]+([\d]{1,2}[./\-][\d]{1,2}[./\-][\d]{2,4})',
        r'[Tt]rade\s+[Dd]ate[:\s]+([\d]{1,2}[./\-][\d]{1,2}[./\-][\d]{2,4})',
        r'[Ss]trike[:\s]+([\d]{1,2}[./\-][\d]{1,2}[./\-][\d]{2,4})',
        r'[Ii]nitial\s+[Vv]aluation[:\s]+([\d]{1,2}[./\-][\d]{1,2}[./\-][\d]{2,4})',
    ]:
        val = _find(pat, text)
        if val:
            p["תאריך Strike"] = val
            break
    if "תאריך Strike" not in p:
        p["תאריך Strike"] = ""

    # Closing / Issue date
    for pat in [
        r'[Ii]ssue\s+[Dd]ate[:\s]+([\d]{1,2}[./\-][\d]{1,2}[./\-][\d]{2,4})',
        r'[Cc]losing\s+[Dd]ate[:\s]+([\d]{1,2}[./\-][\d]{1,2}[./\-][\d]{2,4})',
        r'[Ss]ettlement\s+[Dd]ate[:\s]+([\d]{1,2}[./\-][\d]{1,2}[./\-][\d]{2,4})',
        r'[Pp]ayment\s+[Dd]ate[:\s]+([\d]{1,2}[./\-][\d]{1,2}[./\-][\d]{2,4})',
    ]:
        val = _find(pat, text)
        if val:
            p["תאריך סגירת גיוס"] = val
            break
    if "תאריך סגירת גיוס" not in p:
        p["תאריך סגירת גיוס"] = ""

    # Autocall trigger table — find M6, M7... patterns
    trigger_matches = re.findall(r'M(\d+)[:\s]*([\d\.]+%)', text)
    if trigger_matches:
        p["לוח Autocall Triggers"] = " / ".join(f"M{m} {pct}" for m, pct in trigger_matches[:20])
    else:
        p["לוח Autocall Triggers"] = ""

    p["הערות"] = ""
    return p


# ── Multi-product import UI ───────────────────────────────────────────────────
with st.expander("📋 ייבוא מרובה — הדבק Term Sheet (מספר פקדונות במקביל)", expanded=False):
    pasted = st.text_area("הדבק כאן את הטקסט מה-Term Sheet", height=220, key="multi_ts_paste",
                          placeholder="Issuer: BBVA\nISIN: XS3317187857 // XS3317187931\n...")
    if st.button("🔍 נתח", key="parse_multi_btn"):
        if pasted.strip():
            results = _parse_multi_ts(pasted)
            st.session_state["multi_parsed"] = results
            if not results:
                st.warning("לא נמצאו ISINs בטקסט — בדוק שהפורמט מכיל XS... או CH...")
        else:
            st.warning("הדבק טקסט תחילה")

    if st.session_state.get("multi_parsed"):
        results = st.session_state["multi_parsed"]
        st.success(f"נמצאו **{len(results)}** מוצרים — בדוק לפני שמירה:")
        preview_df = pd.DataFrame([{
            "ISIN":        p["ISIN"],
            "מנפיק":       p["מנפיק"],
            "מטבע":        p["מטבע"],
            "גודל עסקה":   p["גודל עסקה"],
            "קופון שנתי":  p["קופון שנתי"],
            "מחסום":       p["מחסום"],
            'מח"מ':        p.get('מח"מ (חודשים)', ""),
            "נכסי בסיס":   p["נכסי בסיס"],
        } for p in results])
        st.dataframe(preview_df, hide_index=True, use_container_width=True)

        if st.button("💾 שמור את כולם ל-Products", key="save_multi_btn", type="primary"):
            products_df = read_df("Products")
            if products_df.empty:
                products_df = pd.DataFrame(columns=PRODUCTS_COLS)
            for col in PRODUCTS_COLS:
                if col not in products_df.columns:
                    products_df[col] = ""
            saved = 0
            for p in results:
                isin = p["ISIN"]
                underlyings_str = p.get("נכסי בסיס", "")
                row_data = {
                    "ISIN": isin, "מנפיק": p["מנפיק"], "נכסי בסיס": underlyings_str,
                    "קופון שנתי": p["קופון שנתי"], 'מח"מ (חודשים)': p.get('מח"מ (חודשים)', ""),
                    "מטבע": p["מטבע"], "גודל עסקה": p["גודל עסקה"],
                    "תאריך סגירה": "", "סטטוס": "פעיל",
                }
                if isin and "ISIN" in products_df.columns and isin in products_df["ISIN"].values:
                    idx = products_df[products_df["ISIN"] == isin].index[0]
                    for field, val in row_data.items():
                        if field != "סטטוס":
                            products_df.at[idx, field] = val
                else:
                    products_df = pd.concat([products_df, pd.DataFrame([row_data])], ignore_index=True)
                saved += 1
            write_df("Products", products_df)
            log_action(current_user(), "ייבוא מרובה", f"{saved} מוצרים: {', '.join(p['ISIN'] for p in results)}")
            st.session_state["multi_parsed"] = []
            st.success(f"✓ {saved} מוצרים נשמרו!")
            st.rerun()

        if st.button("🗑️ נקה", key="clear_multi_btn"):
            st.session_state["multi_parsed"] = []
            st.rerun()

st.divider()

# ── Session state init ────────────────────────────────────────────────────────
if "ts_parsed" not in st.session_state:
    st.session_state["ts_parsed"] = {}


# ══════════════════════════════════════════════════════════════════════════════
# Section 1 — Upload Term Sheet
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("### 📎 טעינת Term Sheet")

uploaded = st.file_uploader("בחר קובץ PDF של ה-Term Sheet", type=["pdf"], key="ts_pdf_upload")

if uploaded:
    pdf_bytes = uploaded.read()
    # Save file
    save_path = TS_DIR / uploaded.name
    save_path.write_bytes(pdf_bytes)

    with st.spinner("מחלץ נתונים מה-PDF..."):
        raw_text = _extract_text(pdf_bytes)
        parsed   = _parse_ts(raw_text)

    if parsed.get("ISIN"):
        st.session_state["ts_parsed"] = parsed
        st.success(f"✓ זוהה ISIN: **{parsed['ISIN']}** — הנתונים מולאו אוטומטית למטה. בדוק ולחץ שמור.")
    else:
        st.warning("לא זוהה ISIN. מלא ידנית.")
        st.session_state["ts_parsed"] = parsed

    # Show raw text for reference
    with st.expander("📄 טקסט גולמי מה-PDF (לבדיקה)", expanded=False):
        st.text(raw_text[:3000])

# ── Free-text single-product paste ───────────────────────────────────────────
with st.expander("✍️ הדבק תיאור חופשי — פקדון יחיד", expanded=False):
    st.caption("הדבק כאן פורמט חופשי עם bullet points, tabs, או שורות Key: Value — המערכת תנסה לחלץ את הפרטים אוטומטית")
    free_text = st.text_area(
        "טקסט חופשי",
        height=200,
        key="free_text_single",
        placeholder="• Issuer: BNP\n• ISIN: XS3330669121\n• Size: 500K ILS\nMaturity: 36 Months\nCoupon if called: 7.50% p.a. ILS\nUnderlying's (WO): LUMI - MZTF - Harel\nCallability: Every quarter, first observation in 12 month(s)",
    )
    if st.button("🔍 נתח טקסט", key="parse_free_btn"):
        if free_text.strip():
            parsed_free = _parse_ts(free_text)
            st.session_state["ts_parsed"] = parsed_free
            if parsed_free.get("ISIN"):
                st.success(f"✓ זוהה ISIN: **{parsed_free['ISIN']}** — הטופס מולא אוטומטית למטה")
            else:
                st.warning("לא זוהה ISIN — בדוק את הטקסט או מלא ידנית")
            st.rerun()
        else:
            st.warning("הדבק טקסט תחילה")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# Section 2 — Form (pre-filled from parsed or last saved)
# ══════════════════════════════════════════════════════════════════════════════
col_title, col_clear = st.columns([5, 1])
with col_title:
    st.markdown("### ✏️ פרטי הפקדון")
with col_clear:
    st.markdown("<div style='padding-top:1.2rem'></div>", unsafe_allow_html=True)
    if st.button("🗑️ נקה טופס", use_container_width=True):
        st.session_state["ts_parsed"] = {}
        st.rerun()

p = st.session_state.get("ts_parsed", {})

with st.form("product_form"):
    c1, c2 = st.columns(2)
    with c1:
        issuer   = st.text_input("מנפיק",         value=p.get("מנפיק", ""))
        isin     = st.text_input("ISIN",           value=p.get("ISIN", ""))
        size     = st.text_input("גודל עסקה",     value=p.get("גודל עסקה", ""))
        cur_val  = p.get("מטבע", "ILS")
        currency = st.selectbox("מטבע", CURRENCIES,
                                index=CURRENCIES.index(cur_val) if cur_val in CURRENCIES else 0)
        maturity = st.text_input('מח"מ (חודשים)', value=p.get('מח"מ (חודשים)', "36"))
        barrier  = st.text_input("מחסום",          value=p.get("מחסום", "50%"))
    with c2:
        coupon_a = st.text_input("קופון שנתי",     value=p.get("קופון שנתי", ""))
        coupon_m = st.text_input("קופון חודשי",    value=p.get("קופון חודשי", ""))
        und1     = st.text_input("נכס בסיס 1",     value=p.get("נכס בסיס 1", ""))
        und2     = st.text_input("נכס בסיס 2",     value=p.get("נכס בסיס 2", ""))
        und3     = st.text_input("נכס בסיס 3",     value=p.get("נכס בסיס 3", ""))
        first_ac = st.text_input("תצפית Autocall ראשונה (חודש)",
                                  value=p.get("תצפית Autocall ראשונה (חודש)", "6"))

    c3, c4 = st.columns(2)
    with c3:
        strike_date = st.text_input("תאריך Strike",      value=p.get("תאריך Strike", ""))
    with c4:
        close_date  = st.text_input("תאריך סגירת גיוס", value=p.get("תאריך סגירת גיוס", ""))

    triggers = st.text_area("לוח Autocall Triggers",
                             value=p.get("לוח Autocall Triggers", ""),
                             height=100,
                             placeholder="M6 100% / M7 98.5% / M8 97%...")
    notes    = st.text_area("הערות", value=p.get("הערות", ""))

    save = st.form_submit_button("💾 שמור פקדון למערכת", use_container_width=True, type="primary")

if save:
    # Upsert into Products list
    products_df = read_df("Products")
    if products_df.empty:
        products_df = pd.DataFrame(columns=PRODUCTS_COLS)
    for col in PRODUCTS_COLS:
        if col not in products_df.columns:
            products_df[col] = ""

    underlyings = " / ".join(filter(None, [und1, und2, und3]))
    if isin and not products_df.empty and "ISIN" in products_df.columns and isin in products_df["ISIN"].values:
        idx = products_df[products_df["ISIN"] == isin].index[0]
        products_df.at[idx, "מנפיק"]         = issuer
        products_df.at[idx, "נכסי בסיס"]     = underlyings
        products_df.at[idx, "קופון שנתי"]    = coupon_a
        products_df.at[idx, 'מח"מ (חודשים)'] = maturity
        products_df.at[idx, "מטבע"]           = currency
        products_df.at[idx, "גודל עסקה"]     = size
        products_df.at[idx, "תאריך סגירה"]    = close_date
    else:
        new_row = pd.DataFrame([{
            "ISIN": isin, "מנפיק": issuer, "נכסי בסיס": underlyings,
            "קופון שנתי": coupon_a, 'מח"מ (חודשים)': maturity,
            "מטבע": currency, "גודל עסקה": size,
            "תאריך סגירה": close_date, "סטטוס": "פעיל",
        }])
        products_df = pd.concat([products_df, new_row], ignore_index=True)
    write_df("Products", products_df)

    # Update session state
    st.session_state["ts_parsed"] = {
        "מנפיק": issuer, "ISIN": isin, "גודל עסקה": size, "מטבע": currency,
        'מח"מ (חודשים)': maturity, "מחסום": barrier, "קופון שנתי": coupon_a,
        "קופון חודשי": coupon_m, "נכס בסיס 1": und1, "נכס בסיס 2": und2,
        "נכס בסיס 3": und3, "תצפית Autocall ראשונה (חודש)": first_ac,
        "תאריך Strike": strike_date, "תאריך סגירת גיוס": close_date,
        "לוח Autocall Triggers": triggers, "הערות": notes,
    }

    log_action(current_user(), "שמירת Term Sheet", f"{issuer} | {isin} | {currency}")
    st.success(f"✓ פקדון {isin} נשמר!")
    st.rerun()

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# Section 3 — Active products list
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("### 📋 פקדונות פעילים")

products_df = read_df("Products")
if products_df.empty:
    st.info("אין פקדונות פעילים עדיין.")
else:
    for col in PRODUCTS_COLS:
        if col not in products_df.columns:
            products_df[col] = ""

    def color_status(val):
        if val == "פעיל":  return "background-color:#C6EFCE"
        if val == "סגור":  return "background-color:#FDEBD0"
        return ""

    styled = products_df.style.map(color_status,
                subset=["סטטוס"] if "סטטוס" in products_df.columns else [])
    st.dataframe(styled, use_container_width=True, hide_index=True)

    # Quick status change
    isin_list = [x for x in products_df["ISIN"].dropna().tolist() if x.strip()]
    if isin_list:
        col_sel, col_status, col_btn = st.columns([3, 2, 1])
        with col_sel:
            sel_isin = st.selectbox("בחר פקדון", isin_list, key="status_sel", label_visibility="collapsed")
        with col_status:
            row_idx = products_df[products_df["ISIN"] == sel_isin].index[0]
            cur_st  = products_df.at[row_idx, "סטטוס"] if "סטטוס" in products_df.columns else "פעיל"
            new_st  = st.selectbox("סטטוס", ["פעיל", "סגור", "בהכנה"],
                                   index=["פעיל", "סגור", "בהכנה"].index(cur_st) if cur_st in ["פעיל", "סגור", "בהכנה"] else 0,
                                   key="new_status_sel", label_visibility="collapsed")
        with col_btn:
            if st.button("עדכן", key="update_status_btn"):
                products_df.at[row_idx, "סטטוס"] = new_st
                write_df("Products", products_df)
                log_action(current_user(), "עדכון סטטוס פקדון", f"{sel_isin} → {new_st}")
                st.success(f"✓ {sel_isin} → {new_st}")
                st.rerun()
