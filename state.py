"""Cached data access for the Streamlit app."""
from __future__ import annotations

import os

import streamlit as st

from data_loader import load_raw
from prepare import Dataset, prepare

CACHE_TTL = 60 * 60       # the sheets refresh hourly


@st.cache_resource(ttl=CACHE_TTL, show_spinner="Loading the latest data…")
def _load() -> Dataset:
    if os.environ.get("GC_DATA_DIR"):
        return prepare(load_raw({}))
    try:
        secrets = st.secrets.to_dict()
    except Exception:  # noqa: BLE001 - no secrets configured
        secrets = {}
    return prepare(load_raw(secrets))


def get_dataset() -> Dataset | None:
    try:
        return _load()
    except Exception as e:  # noqa: BLE001
        st.error("The data could not be loaded.")
        st.caption(f"{type(e).__name__}: {e}")
        st.info("Check that the service account has viewer access to both spreadsheets and that the app secrets "
                "contain the service account key and the spreadsheet IDs (see README).")
        return None


def refresh() -> None:
    _load.clear()


def ctx():
    return st.session_state["_ctx"]
