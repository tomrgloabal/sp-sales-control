"""
Google Sheets backend.
Falls back to local JSON files if GCP credentials are not configured.
"""
import json
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

DATA_DIR = Path(__file__).parent / "local_data"
DATA_DIR.mkdir(exist_ok=True)

# ── helpers ──────────────────────────────────────────────────────────────────

def _use_sheets() -> bool:
    try:
        return "gcp_service_account" in st.secrets and "spreadsheet_id" in st.secrets
    except Exception:
        return False


@st.cache_resource
def _get_client():
    from google.oauth2.service_account import Credentials
    import gspread
    scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=scopes)
    return gspread.authorize(creds)


def _get_worksheet(tab: str):
    client = _get_client()
    sh = client.open_by_key(st.secrets["spreadsheet_id"])
    return sh.worksheet(tab)


# ── public API ────────────────────────────────────────────────────────────────

def read_df(tab: str) -> pd.DataFrame:
    if _use_sheets():
        try:
            ws = _get_worksheet(tab)
            records = ws.get_all_records()
            return pd.DataFrame(records)
        except Exception:
            return pd.DataFrame()
    # local fallback
    path = DATA_DIR / f"{tab}.json"
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not raw:
            # Empty list — return df with proper columns if known
            try:
                from config import TAB_COLS
                cols = TAB_COLS.get(tab)
                if cols:
                    return pd.DataFrame(columns=cols)
            except Exception:
                pass
            return pd.DataFrame()
        return pd.DataFrame(raw)
    return pd.DataFrame()


def write_df(tab: str, df: pd.DataFrame):
    if _use_sheets():
        ws = _get_worksheet(tab)
        ws.clear()
        ws.update([df.columns.tolist()] + df.fillna("").values.tolist())
    else:
        # Ensure columns are always named (never numeric index)
        if df.columns.dtype == object and not df.empty:
            pass  # columns are already named strings
        elif df.empty:
            # Preserve column names even for empty dataframe
            try:
                from config import TAB_COLS
                cols = TAB_COLS.get(tab)
                if cols:
                    df = pd.DataFrame(columns=cols)
            except Exception:
                pass
        path = DATA_DIR / f"{tab}.json"
        path.write_text(df.to_json(orient="records", force_ascii=False), encoding="utf-8")


def append_row(tab: str, row: list):
    if _use_sheets():
        ws = _get_worksheet(tab)
        ws.append_row(row, value_input_option="USER_ENTERED")
    else:
        df = read_df(tab)
        if df.empty:
            # Use proper column names so data is readable on next load
            try:
                from config import TAB_COLS
                cols = TAB_COLS.get(tab)
            except Exception:
                cols = None
            if cols:
                new_df = pd.DataFrame([dict(zip(cols, row + [""] * max(0, len(cols) - len(row))))])
            else:
                new_df = pd.DataFrame([row])
        else:
            new_row = pd.DataFrame([dict(zip(df.columns, row + [""] * max(0, len(df.columns) - len(row))))])
            new_df = pd.concat([df, new_row], ignore_index=True)
        write_df(tab, new_df)


def update_row(tab: str, row_idx: int, updated: dict):
    df = read_df(tab)
    for col, val in updated.items():
        if col in df.columns:
            df.at[row_idx, col] = val
    write_df(tab, df)


def log_action(user: str, action: str, details: str = ""):
    row = [datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user, action, details]
    append_row("AuditLog", row)
