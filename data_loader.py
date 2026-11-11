"""Loads the raw tabs from Google Sheets (production) or from a local CSV folder (development / offline checks).

Production (Streamlit Cloud) uses a Google service account stored in st.secrets:

    [gcp_service_account]   # the JSON key of the service account
    [sheets]
    cs_spreadsheet_id     = "..."
    orders_spreadsheet_id = "..."

Large tabs are downloaded as CSV through the authenticated export endpoint (fast, and identical to File >
Download > CSV); small tabs are read in one Sheets API batch call. Every value is kept as text exactly as the
sheet displays it; typing happens in core.prepare.
"""
from __future__ import annotations

import io
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

from config import CS_TABS, LARGE_TABS, LOGI_2025_COLUMNS, LOGI_2025_TAB, LOGI_TAB, ORDERS_TAB, REQUIRED_COLUMNS

DEFAULT_CS_ID = "1d1_4RJtoG8EudFWDrzmS_5oWTUAxzI7aQ5GOX2fGtBo"       # TEST copy until the real sheet is upgraded
DEFAULT_ORDERS_ID = "1dZMqtqvnxe6GspH0C10AvXECB74NP-ZjDG_BihMOkmg"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly",
          "https://www.googleapis.com/auth/drive.readonly"]


@dataclass
class RawData:
    frames: dict = field(default_factory=dict)       # key -> DataFrame (all text)
    missing: list = field(default_factory=list)      # tabs that could not be read
    source: str = ""
    loaded_at: str = ""


def _usecols(key: str):
    """CS_Chats is large: keep only the columns the app uses (saves memory on Streamlit Cloud)."""
    if key == "chats":
        keep = set(REQUIRED_COLUMNS["chats"])
        return lambda c: c in keep
    if key == "logi_2025":
        keep = set(LOGI_2025_COLUMNS)
        return lambda c: c in keep
    return None


def _read_csv_text(text: str, key: str = "") -> pd.DataFrame:
    return pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False, usecols=_usecols(key))


# ------------------------------------------------------------------------------------------------ local folder
def load_local(folder: str) -> RawData:
    out = RawData(source=f"Local files ({folder})")
    wanted = dict(CS_TABS)
    wanted["orders"] = ORDERS_TAB
    wanted["logi"] = LOGI_TAB
    wanted["logi_2025"] = LOGI_2025_TAB
    for key, tab in wanted.items():
        path = os.path.join(folder, tab.replace(" ", "_") + ".csv")
        if os.path.exists(path):
            out.frames[key] = pd.read_csv(path, dtype=str, keep_default_na=False, usecols=_usecols(key))
        else:
            out.missing.append(tab)
    out.loaded_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return out


# ------------------------------------------------------------------------------------------------ Google Sheets
def _session(sa_info: dict):
    from google.auth.transport.requests import AuthorizedSession
    from google.oauth2 import service_account
    creds = service_account.Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    return AuthorizedSession(creds)


def _get(sess, url, params=None, tries=4):
    for i in range(tries):
        r = sess.get(url, params=params, timeout=180)
        if r.status_code in (429, 500, 502, 503):
            time.sleep(2 * (i + 1))
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()
    return r


def _sheet_ids(sess, spreadsheet_id: str) -> dict:
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}"
    meta = _get(sess, url, params={"fields": "sheets.properties(sheetId,title)"}).json()
    return {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta.get("sheets", [])}


def _export_csv(sess, spreadsheet_id: str, gid: int, key: str = "") -> pd.DataFrame:
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export"
    r = _get(sess, url, params={"format": "csv", "gid": gid})
    r.encoding = "utf-8"
    return _read_csv_text(r.text, key)


def _values_batch(sess, spreadsheet_id: str, titles: list) -> dict:
    if not titles:
        return {}
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values:batchGet"
    params = [("ranges", f"'{t}'") for t in titles] + [("valueRenderOption", "FORMATTED_VALUE")]
    data = _get(sess, url, params=params).json()
    out = {}
    for t, vr in zip(titles, data.get("valueRanges", [])):
        rows = vr.get("values", [])
        if not rows:
            out[t] = pd.DataFrame()
            continue
        head = [str(h) for h in rows[0]]
        n = len(head)
        body = [(r + [""] * n)[:n] for r in rows[1:]]
        out[t] = pd.DataFrame(body, columns=head).astype(str)
    return out


def load_google(sa_info: dict, cs_id: str, orders_id: str) -> RawData:
    out = RawData(source="Google Sheets")
    sess = _session(sa_info)
    cs_ids = _sheet_ids(sess, cs_id)
    small = [t for k, t in CS_TABS.items() if k not in LARGE_TABS and t in cs_ids]
    batch = _values_batch(sess, cs_id, small)
    for key, tab in CS_TABS.items():
        if tab not in cs_ids:
            out.missing.append(tab)
            continue
        if key in LARGE_TABS:
            out.frames[key] = _export_csv(sess, cs_id, cs_ids[tab], key)
        else:
            out.frames[key] = batch.get(tab, pd.DataFrame())
    try:
        o_ids = _sheet_ids(sess, orders_id)
        if ORDERS_TAB in o_ids:
            out.frames["orders"] = _export_csv(sess, orders_id, o_ids[ORDERS_TAB])
        else:
            out.missing.append(ORDERS_TAB)
        if LOGI_TAB in o_ids:
            out.frames["logi"] = _values_batch(sess, orders_id, [LOGI_TAB]).get(LOGI_TAB, pd.DataFrame())
        else:
            out.missing.append(LOGI_TAB)
        if LOGI_2025_TAB in o_ids:
            out.frames["logi_2025"] = _export_csv(sess, orders_id, o_ids[LOGI_2025_TAB], "logi_2025")
    except Exception:  # noqa: BLE001 - reported as missing, never silently zero-filled
        out.missing.append(ORDERS_TAB)
    out.loaded_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return out


def load_raw(secrets) -> RawData:
    """Chooses the source: local folder (GC_DATA_DIR env or [local] data_dir) or Google Sheets."""
    folder = os.environ.get("GC_DATA_DIR") or (secrets.get("local", {}).get("data_dir") if secrets else None)
    if folder:
        return load_local(folder)
    sa = None
    if secrets and "gcp_service_account" in secrets:
        sa = dict(secrets["gcp_service_account"])
    elif secrets and "gcp_service_account_json" in secrets:      # same key, pasted as one JSON text
        raw = secrets["gcp_service_account_json"]
        sa = json.loads(raw) if isinstance(raw, str) else dict(raw)
    if not sa:
        raise RuntimeError("No data source configured. Add the service account and sheet IDs to the app secrets.")
    sh = secrets.get("sheets", {}) or {}
    cs_id = sh.get("cs_spreadsheet_id") or secrets.get("cs_spreadsheet_id") or DEFAULT_CS_ID
    orders_id = sh.get("orders_spreadsheet_id") or secrets.get("orders_spreadsheet_id") or DEFAULT_ORDERS_ID
    return load_google(sa, cs_id, orders_id)
