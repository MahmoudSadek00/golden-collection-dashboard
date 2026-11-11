"""Period-over-period comparison (team, groups and agents), direction-aware."""
from __future__ import annotations

import numpy as np
import pandas as pd

import analytics as an
from kpis import ALL_KPIS, OPS_KPIS, TEAM_ORDER, is_missing, target_met, trend
from periods import Period, comparable
from prepare import Dataset


def targets(ds: Dataset) -> dict:
    t = {k: v["target"] for k, v in ds.cfg["weights"].items()}
    t["score"] = ds.cfg["teamTarget"]
    return t


def _pct(cur, prev):
    if is_missing(cur) or is_missing(prev) or prev == 0:
        return np.nan
    return (cur - prev) / abs(prev)


def kpi_keys_for(cur: Period, prev: Period, team_level: bool = True) -> list:
    keys = [k for k in TEAM_ORDER if k != "sales" or not team_level]
    if not (cur.scored and prev.scored):
        keys = [k for k in keys if k != "score" and not ALL_KPIS[k].monthly_only]
    return keys


def compare_team(ds: Dataset, cur: Period, prev: Period, agents: list | None = None) -> pd.DataFrame:
    tc, tp = an.team(ds, cur, agents), an.team(ds, prev, agents)
    oc, op = an.ops(ds, cur, agents), an.ops(ds, prev, agents)
    T = targets(ds)
    rows = []
    for k in kpi_keys_for(cur, prev):
        rows.append(_row(k, tc.get(k), tp.get(k), T.get(k), "Scorecard"))
    for k in OPS_KPIS:
        rows.append(_row(k, oc.get(k), op.get(k), None, "Operations"))
    return pd.DataFrame(rows)


def _row(k, c, p, tgt, family):
    c = np.nan if c is None else c
    p = np.nan if p is None else p
    return {"key": k, "KPI": ALL_KPIS[k].label, "family": family, "current": c, "previous": p,
            "change": (c - p) if not (is_missing(c) or is_missing(p)) else np.nan, "change_pct": _pct(c, p),
            "target": tgt if tgt is not None else np.nan, "met_current": target_met(k, c, tgt) if tgt is not None else None,
            "met_previous": target_met(k, p, tgt) if tgt is not None else None, "trend": trend(k, c, p),
            "direction": ALL_KPIS[k].direction}


def compare_agents(ds: Dataset, cur: Period, prev: Period, agents: list | None = None) -> pd.DataFrame:
    A, B = an.scorecard(ds, cur), an.scorecard(ds, prev)
    if A.empty:
        return pd.DataFrame()
    keys = kpi_keys_for(cur, prev, team_level=False)
    B = B.set_index("agent") if not B.empty else pd.DataFrame()
    rows = []
    for _, r in A.iterrows():
        a = r["agent"]
        if agents and a not in agents:
            continue
        rec = {"agent": a, "group": r["group"], "comparable_now": bool(r["comparable"]),
               "comparable_before": bool(B.loc[a, "comparable"]) if a in B.index else False,
               "working_days": r["working_days"], "working_days_prev": B.loc[a, "working_days"] if a in B.index else np.nan}
        for k in keys:
            c = r.get(k, np.nan)
            p = B.loc[a, k] if a in B.index and k in B.columns else np.nan
            rec[f"{k}_cur"], rec[f"{k}_prev"] = c, p
            rec[f"{k}_chg"] = (c - p) if not (is_missing(c) or is_missing(p)) else np.nan
            rec[f"{k}_trend"] = trend(k, c, p)
        if cur.scored and prev.scored:
            rec["rank_cur"] = r.get("rank", np.nan)
            rec["rank_prev"] = B.loc[a, "rank"] if a in B.index else np.nan
            rec["rank_chg"] = (rec["rank_prev"] - rec["rank_cur"]) if not (is_missing(rec["rank_cur"]) or
                                                                          is_missing(rec["rank_prev"])) else np.nan
        rows.append(rec)
    return pd.DataFrame(rows)


def compare_groups(ds: Dataset, cur: Period, prev: Period) -> pd.DataFrame:
    """Shift-group KPIs in both periods (groups defined by each period's night-shift rule)."""
    gc, gp = an.agent_groups(ds, cur), an.agent_groups(ds, prev)
    T = targets(ds)
    rows = []
    for g in sorted(set(gc) | set(gp)):
        tc = an.team(ds, cur, gc.get(g)) if g in gc else {}
        tp = an.team(ds, prev, gp.get(g)) if g in gp else {}
        for k in kpi_keys_for(cur, prev):
            r = _row(k, tc.get(k, np.nan), tp.get(k, np.nan), T.get(k), "Scorecard")
            r["group"] = g
            r["agents_now"] = len(gc.get(g, []))
            rows.append(r)
    return pd.DataFrame(rows)


def warnings(ds: Dataset, cur: Period, prev: Period) -> list:
    return comparable(cur, prev, an.coverage(ds, cur), an.coverage(ds, prev))
