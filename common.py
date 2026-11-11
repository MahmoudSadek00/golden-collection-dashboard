"""Helpers shared by the pages."""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

import analytics as an
import comparison as cmp
import periods as P
from kpis import ALL_KPIS, achievement, gap, is_missing, target_met, trend
from state import ctx
import components as C


def context():
    return ctx()


def header(eyebrow: str, title: str, sub: str = "") -> tuple:
    ds, f = context()
    meta = f"Data to {ds.coverage['chats_to']:%d %b %Y}<br>Refreshed {ds.loaded_at}"
    C.page_header(eyebrow, title, sub, meta)
    warns = []
    cov = an.coverage(ds, f.period)
    if cov.get("note"):
        warns.append(cov["note"])
    if not cov.get("schedule_ok", True):
        warns.append(f"Schedule missing after {ds.coverage['schedule_to']:%d %b}: score and per-day KPIs withheld")
    if f.compare is not None:
        cc = an.coverage(ds, f.compare)
        if cc.get("note"):
            warns.append(f"Comparison: {cc['note']}")
        elif not cc.get("schedule_ok", True):
            warns.append("Comparison period has no schedule: per-day KPIs not comparable")
    C.chips(f.chips(), warns)
    return ds, f


def history_months(ds, end: pd.Timestamp, n: int = 12) -> list:
    f_from, f_to = an.data_range(ds)
    ms = [p for p in P.available("Month", f_from, f_to) if p.start <= end]
    return list(reversed(ms[:n]))


def team_table(ds, f, keys: list | None = None) -> pd.DataFrame:
    """KPI table: actual, target, achievement, gap, previous, change, trend, status."""
    cur, prev = f.period, f.compare
    tc = an.team(ds, cur, f.agents)
    tp = an.team(ds, prev, f.agents) if prev else {}
    T = cmp.targets(ds)
    keys = keys or cmp.kpi_keys_for(cur, prev or cur)
    rows = []
    for k in keys:
        v, p_ = tc.get(k, np.nan), tp.get(k, np.nan) if prev else np.nan
        t = T.get(k)
        rows.append({"KPI": ALL_KPIS[k].label, "key": k, "Actual": v, "Target": t, "Achievement": achievement(k, v, t),
                     "Gap": gap(k, v, t), "Previous": p_, "Change": (v - p_) if not (is_missing(v) or is_missing(p_)) else np.nan,
                     "Trend": C.trend_text(trend(k, v, p_)),
                     "Status": C.met_text(target_met(k, v, t)),
                     "In score": "Yes" if ds.cfg["weights"].get(k, {}).get("ptsNoFcr", 0) or k == "score" else "Monitor only"})
    return pd.DataFrame(rows)


def show_team_table(df: pd.DataFrame, prev_label: str) -> None:
    from kpis import fmt, fmt_delta
    d = pd.DataFrame({
        "KPI": df["KPI"],
        "Actual": [fmt(k, v) for k, v in zip(df["key"], df["Actual"])],
        "Target": [fmt(k, v) for k, v in zip(df["key"], df["Target"])],
        "Achievement": [C.ach_txt(a) for a in df["Achievement"]],
        "Gap to target": [fmt_delta(k, g) for k, g in zip(df["key"], df["Gap"])],
        f"{prev_label}": [fmt(k, v) for k, v in zip(df["key"], df["Previous"])],
        "Change": [fmt_delta(k, v) for k, v in zip(df["key"], df["Change"])],
        "Trend": df["Trend"], "Status": df["Status"], "In score": df["In score"],
    })
    st.dataframe(C.style_status(d, ["Trend", "Status"]), hide_index=True, use_container_width=True,
                 height=min(420, 38 + 35 * len(d)))
