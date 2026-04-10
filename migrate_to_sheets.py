"""
migrate_to_sheets.py
מעביר את כל הנתונים מ-local_data/ ל-Google Sheets.
מריצים פעם אחת אחרי שמגדירים credentials ב-.streamlit/secrets.toml

שימוש:
    python migrate_to_sheets.py
"""
import json
import sys
from pathlib import Path

import gspread
import toml
from google.oauth2.service_account import Credentials

SECRETS_PATH = Path(__file__).parent / ".streamlit" / "secrets.toml"
LOCAL_DATA   = Path(__file__).parent / "local_data"

TABS = ["Pipeline", "Sales", "Products", "Banks", "Redemptions", "AuditLog"]


def main():
    if not SECRETS_PATH.exists():
        print("ERROR: .streamlit/secrets.toml לא נמצא")
        sys.exit(1)

    secrets = toml.load(SECRETS_PATH)

    if "gcp_service_account" not in secrets or "spreadsheet_id" not in secrets:
        print("ERROR: חסרים gcp_service_account או spreadsheet_id ב-secrets.toml")
        sys.exit(1)

    creds = Credentials.from_service_account_info(
        dict(secrets["gcp_service_account"]),
        scopes=["https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"]
    )
    client = gspread.authorize(creds)
    sh = client.open_by_key(secrets["spreadsheet_id"])

    existing_tabs = {ws.title for ws in sh.worksheets()}

    for tab in TABS:
        path = LOCAL_DATA / f"{tab}.json"
        if not path.exists():
            print(f"  דילוג {tab} — קובץ לא קיים")
            continue

        data = json.loads(path.read_text(encoding="utf-8"))
        if not data:
            print(f"  דילוג {tab} — ריק")
            continue

        if isinstance(data[0], dict):
            headers = list(data[0].keys())
            rows = [list(r.values()) for r in data]
        else:
            headers = ["value"]
            rows = [[r] for r in data]

        if tab in existing_tabs:
            ws = sh.worksheet(tab)
        else:
            ws = sh.add_worksheet(title=tab, rows=max(len(rows)+10, 50), cols=len(headers)+5)

        ws.clear()
        ws.update([headers] + rows)
        print(f"  ✓ {tab}: {len(rows)} שורות")

    print("\nMigration הושלמה. בדוק את ה-Google Sheet.")


if __name__ == "__main__":
    main()
