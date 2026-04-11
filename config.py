# SP Sales Control — config v2
USERS = ["תום ריכטר", "רון צוברי", "קובי לוין", "תמיר כהן", "מורן גלבר", "אורן שפירא", "הגר שטרקר"]
USER_KEYS = ["תום", "רון", "קובי", "תמיר", "מורן", "אורן", "הגר"]

USER_EMAILS = {
    "תום ריכטר":  "tom@ar-fo.co.il",
    "רון צוברי":  "ron@ar-fo.co.il",
    "קובי לוין":  "kobi@ar-fo.co.il",
    "תמיר כהן":  "tamir@ar-fo.co.il",
    "מורן גלבר":  "moran@ar-fo.co.il",
    "אורן שפירא": "oren@ar-fo.co.il",
    "הגר שטרקר":  "hagar@ar-fo.co.il",
}

CONFIDENCE = ["גבוהה", "בינונית", "נמוכה"]
CURRENCIES = ["ILS", "USD", "EUR"]
TOOLS = ["A", "B"]
PIPELINE_STATUS = ["לא פנו", "בשיחה", "מעוניין", "לא מעוניין"]

SALES_STAGES = [
    "הצעה נשלחה",
    "מעוניין - בבחינה",
    "אישר כניסה",
    "הנחיות נשלחו ללקוח",
    "בנק לקוח מטפל",
    'אושר ע"י בנק מנפיק',
    "נכנס לפקדון",
]

BANKS = ["בנק לאומי", "בנק הפועלים", "בנק דיסקונט", "בנק מזרחי", "בנק הבינלאומי", "IBI", "גלובלנט", "SAFRA", "UBP", "אחר"]

PIPELINE_COLS = ["שם לקוח", "טלפון", "דרך נציג", "כלי", "ISIN פקדון", "סכום משוער", "מטבע", "רמת וודאות", "תאריך פנייה", "סטטוס", "הערות", "עדכון אחרון"]
SALES_COLS    = ["שם לקוח", "בנק", "ISIN פקדון", "סכום", "מטבע", "שלב", "תאריך הצעה", "תאריך אישור", "הנחיות נשלחו", "מסמכים הוכנו", "אישור בנק לקוח", "אישור בנק מנפיק", "הערות"]
PRODUCT_COLS  = ["שדה", "ערך"]
PRODUCTS_COLS = ["ISIN", "מנפיק", "נכסי בסיס", "קופון שנתי", 'מח"מ (חודשים)', "מטבע", "גודל עסקה", "תאריך סגירה", "סטטוס"]
BANKS_COLS    = ["שם הבנק", "איש קשר", "שיטת ביצוע", "שדות SWIFT", "הוראות מיוחדות", "עדכון אחרון"]
REDEMP_COLS   = ["שם לקוח", "ISIN", "בנק מנפיק", "סכום", "מטבע", "תאריך פקיעה", "סכום + קופון", "פנינו לגבי חדש", "רמת עניין", "הערות"]
AUDIT_COLS    = ["תאריך", "משתמש", "פעולה", "פרטים"]

# Maps each tab name → its column list. Used by append_row to preserve headers.
TAB_COLS = {
    "Pipeline":    PIPELINE_COLS,
    "Sales":       SALES_COLS,
    "Product":     PRODUCT_COLS,
    "Products":    PRODUCTS_COLS,
    "Banks":       BANKS_COLS,
    "Redemptions": REDEMP_COLS,
    "AuditLog":    AUDIT_COLS,
}

NAVY  = "#1E2761"
GREEN = "#1A7A4A"

# Tool A/B descriptions (shown in UI)
TOOL_DESCRIPTIONS = {
    "A": "נציג מורשה — רשאי לשווק ולמכור פקדון ספציפי עם כל הפרטים",
    "B": "סוכן ביטוח — הסבר חינוכי בלבד, ללא פרטי מוצר ספציפיים, הפניה לנציג",
}

# Broker: Privatam SAM (Euroclear 44382) — always the seller
PRIVATAM = "Privatam SAM (Euroclear 44382)"

# Bank execution details — Euroclear/Clearstream codes + required attachments per bank
BANK_DETAILS = {
    "לאומי": {
        "name_en":        "Leumi (Tel Aviv)",
        "clearing_code":  "Euroclear 96583",
        "method":         "Euroclear → Leumi",
        "attachments":    [
            "Leumi Ticket.docx (ממולא וחתום)",
            "קובץ אקסל סליקה (אם נדרש)",
            "הוראות ישירות לברוקר — חתומות ע\"י הלקוח (לקוח חדש בלבד)",
        ],
        "notes": "לקוח ראשון → להעביר גם הוראות ישירות לברוקר חתומות. לקוח חוזר → Ticket בלבד.",
    },
    "מזרחי": {
        "name_en":        "Mizrahi Tefahot Bank",
        "clearing_code":  "Euroclear 98075",
        "method":         "Euroclear → מזרחי",
        "attachments":    [
            "Mizrahi Ticket.docx (ממולא)",
            "טופס בקשת סליקה DA (חתום)",
        ],
        "notes": "הגשה ל-DA (Dealing Abroad) של מזרחי. לוודא חתימה על טופס בקשת סליקה.",
    },
    "פועלים": {
        "name_en":        "Bank Hapoalim (Tel Aviv)",
        "clearing_code":  "Euroclear 94241",
        "method":         "Euroclear → פועלים",
        "attachments":    [
            "Bank Hapoalim Ticket.docx (ממולא)",
            "בקשה להעברת הוראה בניע (חתומה)",
        ],
        "notes": "להגיש לסניף הרלוונטי. לוודא חתימה על טופס העברת ני\"ע זרים.",
    },
    "הבינלאומי": {
        "name_en":        "FIBI - TA-Main-Branch",
        "clearing_code":  "Euroclear 93127",
        "method":         "Euroclear → FIBI",
        "attachments":    [
            "FIBI Ticket.docx (ממולא)",
        ],
        "notes": "",
    },
    "SAFRA": {
        "name_en":        "Bank J. Safra Sarasin",
        "clearing_code":  "Clearstream 52193",
        "method":         "Clearstream → SAFRA",
        "attachments":    [
            "SAFRA Ticket.docx (ממולא)",
            "SAFRA Ticket-IDD (אם מגיע מחשבון IDD)",
        ],
        "notes": "SAFRA משתמש ב-Clearstream (לא Euroclear). לוודא שמסלול ה-Clearstream פעיל.",
    },
    "UBP": {
        "name_en":        "UBP (Geneva)",
        "clearing_code":  "Euroclear 91425",
        "method":         "Euroclear → UBP",
        "attachments":    [
            "Ticket to Custodian (PDF ממולא)",
        ],
        "notes": "UBP ג'נבה — לשלוח Ticket to Custodian במייל.",
    },
    "גלובלנט": {
        "name_en":        "Globalnet",
        "clearing_code":  "—",
        "method":         "ישיר",
        "attachments":    ["Ticket (ממולא)"],
        "notes": "",
    },
    "דיסקונט": {
        "name_en":        "Bank Discount",
        "clearing_code":  "Euroclear",
        "method":         "Euroclear → דיסקונט",
        "attachments":    ["Ticket (ממולא)"],
        "notes": "",
    },
}
