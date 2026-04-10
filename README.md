# SP Sales Control — Arbitrage Global

מערכת ניהול מכירות לפקדונות מובנים. נגישה לשותפי Arbitrage Global בלבד.

## הרצה ראשונה

```bash
cd sp-sales-app
pip install -r requirements.txt
streamlit run app.py --server.address 0.0.0.0 --server.port 8501
```

## גישה מכל מחשב ברשת

```
http://[IP-של-המחשב]:8501
```

לדוגמה: `http://192.168.1.100:8501`

לבדיקת ה-IP של המחשב המריץ:
- Windows: `ipconfig` בשורת פקודה
- Mac/Linux: `ifconfig`

## סיסמאות ברירת מחדל

| שותף | סיסמה |
|------|--------|
| תום  | tom2025 |
| רון  | ron2025 |
| קובי | kobi2025 |
| תמיר | tamir2025 |
| מורן | moran2025 |
| אורן | oren2025 |

## שינוי סיסמה

```python
import hashlib
new_hash = hashlib.sha256("סיסמה_חדשה".encode()).hexdigest()
print(new_hash)
```

הדבק את ה-hash ב-`.streamlit/secrets.toml` תחת `[passwords]`.

## חיבור Google Sheets (אופציונלי)

ללא חיבור Google Sheets — הנתונים נשמרים בתיקיית `local_data/` על המחשב המריץ.

לחיבור Google Sheets:

1. גש ל-[Google Cloud Console](https://console.cloud.google.com/)
2. צור פרויקט חדש
3. הפעל Google Sheets API + Google Drive API
4. צור Service Account → הורד JSON של credentials
5. שתף את ה-Google Sheet עם כתובת האימייל של ה-Service Account (Editor)
6. פתח `.streamlit/secrets.toml` וסמן את השורות:
   - `spreadsheet_id = "ID_של_ה_SHEET"`
   - השלם את כל שדות `[gcp_service_account]` מתוך קובץ ה-JSON

## מבנה ה-App

```
sp-sales-app/
├── app.py               # Main + login
├── auth.py              # אימות משתמשים
├── sheets.py            # Google Sheets / local fallback
├── config.py            # קבועים ורשימות
├── pages/
│   ├── 1_📊_דשבורד.py
│   ├── 2_📋_פייפליין.py
│   ├── 3_💼_מכירות.py
│   ├── 4_📄_פרטי_פקדון.py
│   ├── 5_🏦_הנחיות_בנקים.py
│   └── 6_🔄_פקדונות_פקועים.py
├── .streamlit/
│   ├── config.toml      # עיצוב
│   └── secrets.toml     # סיסמאות + credentials
└── local_data/          # נוצר אוטומטית (backup מקומי)
```
