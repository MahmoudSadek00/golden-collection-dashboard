"""Logistics engine: operations KPIs, market breakdown and the team scorecard of the bonus calculator.

Source: Logistics_Daily (Orders - Clean Data), one row per order date x country. Every figure is a sum or a ratio of
sums over the selected order dates, exactly like the SUMIFS of the bonus calculator's Logistics KPIs tab:

* Delivery rate   = Shipped Delivered / Shipped                         85% = 0 pts, 95% = 40 pts
* On-time rate    = Delivered Within Target / Target Eligible           85% = 0 pts, 95% = 40 pts
* Markets         = markets whose average delivery days <= window / 5   60% = 0 pts, 100% = 20 pts
  (a market with no delivered orders counts as outside, as in the workbook)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import LOGI_CFG, MARKET_NAMES
from kpis import is_missing
from periods import Period

SUM_COLS = ["orders", "delivered_all", "returned_all", "pending_all", "cancelled", "not_shipped", "shipped", "delivered",
            "returned", "in_transit", "value_usd", "delivered_usd", "returned_usd", "refund_usd", "lead_sum", "lead_n",
            "dlv_sum", "dlv_n", "eligible", "on_time", "new_cust", "ret_cust"]
MARKETS = list(LOGI_CFG["windows"].keys())


def has_data(ds) -> bool:
    return ds.logi is not None and not ds.logi.empty


def data_range(ds):
    if not has_data(ds):
        return pd.NaT, pd.NaT
    return ds.logi["date"].min(), ds.logi["date"].max()


def countries(ds) -> list:
    if not has_data(ds):
        return []
    order = {c: i for i, c in enumerate(MARKETS + ["IQ"])}
    return sorted(ds.logi["country"].unique().tolist(), key=lambda c: (order.get(c, 99), c))


def name(code: str) -> str:
    return MARKET_NAMES.get(code, code)


def _rows(ds, p: Period, ctry: list | None = None) -> pd.DataFrame:
    d = ds.logi
    m = (d["date"] >= p.start) & (d["date"] <= p.end)
    if ctry:
        m &= d["country"].isin(ctry)
    return d[m]


def _ratio(n, d):
    return float(n) / float(d) if d else np.nan


def _metrics(s: pd.Series) -> dict:
    """KPIs from summed columns."""
    out = {k: float(s.get(k, 0.0)) for k in SUM_COLS}
    sh = out["shipped"]
    cancel_after = sh - out["delivered"] - out["returned"] - out["in_transit"]
    out.update({
        "l_orders": out["orders"], "l_shipped": sh, "l_delivered": out["delivered"], "l_returned": out["returned"],
        "l_transit": out["in_transit"], "l_cancel_after": max(cancel_after, 0.0), "l_cancelled": out["cancelled"],
        "l_not_shipped": out["not_shipped"],
        "l_delivery": _ratio(out["delivered"], sh), "l_return_rate": _ratio(out["returned"], sh),
        "l_transit_rate": _ratio(out["in_transit"], sh), "l_cancel_rate": _ratio(out["cancelled"], out["orders"]),
        "l_ontime": _ratio(out["on_time"], out["eligible"]), "l_dlv_days": _ratio(out["dlv_sum"], out["dlv_n"]),
        "l_lead_days": _ratio(out["lead_sum"], out["lead_n"]), "l_value": out["value_usd"],
        "l_delivered_value": out["delivered_usd"], "l_new_share": _ratio(out["new_cust"], out["new_cust"] + out["ret_cust"]),
    })
    return out


def totals(ds, p: Period, ctry: list | None = None) -> dict:
    if not has_data(ds):
        return {}
    return _metrics(_rows(ds, p, ctry)[SUM_COLS].sum())


def by_country(ds, p: Period, ctry: list | None = None) -> pd.DataFrame:
    if not has_data(ds):
        return pd.DataFrame()
    g = _rows(ds, p, ctry).groupby("country")[SUM_COLS].sum()
    rows = []
    for c in countries(ds):
        if ctry and c not in ctry:
            continue
        m = _metrics(g.loc[c]) if c in g.index else _metrics(pd.Series(dtype=float))
        w = LOGI_CFG["windows"].get(c)
        m.update({"country": c, "market": name(c), "window": w if w is not None else np.nan,
                  "within": (None if w is None else (m["dlv_n"] > 0 and m["l_dlv_days"] <= w))})
        rows.append(m)
    return pd.DataFrame(rows)


def _pts(v, zero, full, pts):
    if is_missing(v):
        return 0.0
    return min(max((v - zero) / (full - zero), 0.0), 1.0) * pts


def scorecard(ds, p: Period) -> dict:
    """The team score of the bonus calculator (all countries, order dates in the period)."""
    if not has_data(ds):
        return {}
    t = totals(ds, p)
    bc = by_country(ds, p).set_index("country") if t else pd.DataFrame()
    within = {c: bool(bc.loc[c, "within"]) if c in bc.index else False for c in MARKETS}
    mk = sum(within.values()) / len(MARKETS)
    P, cfg = LOGI_CFG["points"], LOGI_CFG
    pts = {"delivery": _pts(t["l_delivery"], cfg["delivery"]["zero"], cfg["delivery"]["full"], P["delivery"]),
           "ontime": _pts(t["l_ontime"], cfg["ontime"]["zero"], cfg["ontime"]["full"], P["ontime"]),
           "markets": _pts(mk, cfg["markets"]["zero"], cfg["markets"]["full"], P["markets"])}
    score = sum(pts.values()) if t["shipped"] else np.nan
    return {"l_score": score, "l_delivery": t["l_delivery"], "l_ontime": t["l_ontime"], "l_markets": mk,
            "pts": pts, "within": within, "target": cfg["teamTarget"],
            "hit": {"delivery": not is_missing(t["l_delivery"]) and t["l_delivery"] >= cfg["delivery"]["full"],
                    "ontime": not is_missing(t["l_ontime"]) and t["l_ontime"] >= cfg["ontime"]["full"],
                    "markets": mk >= cfg["markets"]["full"]}}


def targets() -> dict:
    return {"l_score": LOGI_CFG["teamTarget"], "l_delivery": LOGI_CFG["delivery"]["full"],
            "l_ontime": LOGI_CFG["ontime"]["full"], "l_markets": LOGI_CFG["markets"]["full"]}


def coverage(ds, p: Period) -> dict:
    """Completeness and maturity of a period (recent orders are often still in transit)."""
    f, t = data_range(ds)
    if pd.isna(t):
        return {"complete": False, "note": "No logistics data", "mature": False}
    note = ""
    complete = p.end <= t and p.start >= f
    if p.end > t:
        note = f"Orders up to {t:%d %b %Y} only"
    elif p.start < f:
        note = f"Orders from {f:%d %b %Y} only"
    cut = t - pd.Timedelta(days=LOGI_CFG["maturityDays"])
    mature = p.end <= cut
    mat_note = "" if mature else (f"Orders after {cut:%d %b} are recent: many are still in transit, so delivery and "
                                  "on-time rates for them are not final")
    return {"complete": complete, "note": note, "mature": mature, "maturity_note": mat_note, "data_to": t}


def series(ds, start, end, freq: str = "D", ctry: list | None = None) -> pd.DataFrame:
    """KPIs per day ('D'), week ('W') or month ('M') between two dates."""
    if not has_data(ds):
        return pd.DataFrame()
    d = ds.logi[(ds.logi["date"] >= start) & (ds.logi["date"] <= end)]
    if ctry:
        d = d[d["country"].isin(ctry)]
    if d.empty:
        return pd.DataFrame()
    key = {"D": d["date"], "W": d["date"] - pd.to_timedelta(d["date"].dt.weekday, unit="D"),
           "M": d["date"].dt.to_period("M").dt.to_timestamp()}[freq]
    g = d.groupby(key)[SUM_COLS].sum()
    rows = [dict(_metrics(r), period=i) for i, r in g.iterrows()]
    return pd.DataFrame(rows)


def month_scores(ds, months: list) -> pd.DataFrame:
    rows = []
    for m in months:
        s = scorecard(ds, m)
        if s:
            rows.append({"period": m.label, "l_score": s["l_score"], "l_delivery": s["l_delivery"],
                         "l_ontime": s["l_ontime"], "l_markets": s["l_markets"]})
    return pd.DataFrame(rows)
