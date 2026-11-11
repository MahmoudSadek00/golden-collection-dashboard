"""Approved CS KPI engine: a line-by-line port of kpiAggregate / kpiCompute / kpiPoints_ from LookerKPI.gs
(the script that writes LS_Scorecard and LS_Team). Nothing here may be changed without business approval.

Which date counts for each KPI (same as the script):
  working days, night shifts, absence -> CS_Agent_Daily date
  chats closed & sales chats          -> chat resolved time, credited to "Closed By Agent" (unique customers)
  first reply & FCR                   -> chat start time, credited to the assigned agent
  inbound calls                       -> call date
  delivered sales USD                 -> order date (Agent_Orders, status Delivered)
  quality                             -> QA months that overlap the period
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from config import KPI_KEYS

TARGET_KEYS = ["quality", "chats", "calls", "sales", "reply", "absence"]
from prepare import Dataset

DAY = pd.Timedelta(days=1)


def _clamp(x: float) -> float:
    return min(max(x, 0.0), 1.0)


def kpi_points(cfg: dict, key: str, v) -> float:
    W = cfg["weights"]
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return 0.0
    if key == "quality":
        q = cfg["quality"]
        if v < q["zero"]:
            return 0.0
        if v < q["goodStart"]:
            return (v - q["zero"]) / (q["goodStart"] - q["zero"]) * q["goodPts"]
        return min(q["goodPts"] + (v - q["goodStart"]) / (q["full"] - q["goodStart"]) * (W["quality"]["pts"] - q["goodPts"]),
                   W["quality"]["pts"])
    if key == "fcr":
        return _clamp((v - cfg["fcr"]["zero"]) / (cfg["fcr"]["full"] - cfg["fcr"]["zero"])) * W["fcr"]["pts"]
    if key == "chats":
        c = cfg["chats"]
        if v <= c["zeroAtOrBelow"]:
            return 0.0
        if v < c["target"]:
            return (v - c["zeroAtOrBelow"]) / (c["target"] - c["zeroAtOrBelow"]) * c["targetPts"]
        return min(c["targetPts"] + (v - c["target"]) / (c["full"] - c["target"]) * (c["fullPts"] - c["targetPts"]),
                   c["fullPts"])
    if key == "calls":
        p = 0.0
        for lo, pts in cfg["calls"]:
            if v >= lo:
                p = pts
        return p
    if key == "sales":
        return _clamp((v - cfg["sales"]["zero"]) / (cfg["sales"]["full"] - cfg["sales"]["zero"])) * W["sales"]["pts"]
    if key == "reply":
        return min(cfg["reply"]["full"] / v, 1) * W["reply"]["pts"] if v > 0 else 0.0
    if key == "absence":
        return W["absence"]["pts"] if v <= cfg["absenceMaxPerMonth"] else 0.0
    return 0.0


def months_in(start: pd.Timestamp, end: pd.Timestamp) -> int:
    days = (end - start) / DAY + 1
    return max(1, int(math.floor(days / 30.4 + 0.5)))     # JS Math.round


@dataclass
class EngineResult:
    start: pd.Timestamp
    end: pd.Timestamp
    agents: pd.DataFrame        # one row per scored agent (agents with at least one working day)
    team: dict                  # team-level results, script definitions
    months: int
    fcr_cutoff: pd.Timestamp


def compute(ds: Dataset, start, end) -> EngineResult:
    """Runs the approved engine for one period [start, end] (dates inclusive) over all KPI agents."""
    cfg = ds.cfg
    W = cfg["weights"]
    start = pd.Timestamp(start).normalize()
    end = pd.Timestamp(end).normalize()
    e_excl = end + DAY
    G = ds.max_started - pd.Timedelta(days=cfg["fcrWindowDays"])
    cut = min(e_excl - pd.Timedelta(seconds=1), G) if pd.notna(G) else e_excl - pd.Timedelta(seconds=1)
    agents = ds.kpi_agents
    is_agent = set(agents)

    # ---- daily: working days, night shifts, absence
    d = ds.daily
    d = d[d["agent"].isin(is_agent) & (d["date"] >= start) & (d["date"] < e_excl)]
    night = (d["shift"] == cfg["nightShiftName"]) & (d["working"] == 1)
    absent = d["status"].isin(["Sick", "Casual Leave"])
    dg = pd.DataFrame({"agent": d["agent"], "w": d["working"], "n": night.astype(int), "a": absent.astype(int)}) \
        .groupby("agent").sum()

    # ---- chats closed (unique customers) and sales chats, by resolved time and closer
    c = ds.chats
    cc = c[c["closed_by"].isin(is_agent) & (c["resolved"] >= start) & (c["resolved"] < e_excl)]
    closed = cc.groupby("closed_by")["contact"].nunique()
    sales_chats = cc[cc["is_sales_topic"]].groupby("closed_by")["contact"].nunique()

    # ---- first reply and FCR, by start time and assigned agent
    cs = c[c["agent"].isin(is_agent) & (c["started"] >= start) & (c["started"] < e_excl)]
    fr = cs[cs["frt_sec"].notna()].groupby("agent")["frt_sec"].agg(["sum", "count"])
    fb = cs[cs["fcr_base"] & (cs["resolved"] <= cut)]
    fcr_checked = fb.groupby("agent").size()
    fcr_not = fb[fb["fcr_back"]].groupby("agent").size()

    # ---- inbound calls
    k = ds.calls
    kc = k[k["agent"].isin(is_agent) & (k["type"] == "Inbound") & (k["date"] >= start) & (k["date"] < e_excl)]
    inbound = kc.groupby("agent").size()

    # ---- delivered sales
    o = ds.orders
    oc = o[o["agent"].isin(is_agent) & (o["status"] == "Delivered") & (o["date"] >= start) & (o["date"] < e_excl)]
    sales_usd = oc.groupby("agent")["usd"].apply(lambda s: s.fillna(0).sum())

    # ---- QA (months overlapping the period)
    sm, em = start.strftime("%Y-%m"), end.strftime("%Y-%m")
    q = ds.qa[ds.qa["agent"].isin(is_agent) & ds.qa["score"].notna() & (ds.qa["month"] >= sm) & (ds.qa["month"] <= em)]
    qa = q.groupby("agent")["score"].agg(["sum", "count"])

    months = months_in(start, end)
    rows = []
    for a in agents:
        wd = float(dg["w"].get(a, 0)) if a in dg.index else 0.0
        if wd <= 0:
            continue
        rows.append({
            "agent": a, "working_days": wd, "night_shifts": int(dg["n"].get(a, 0)), "absent_days": int(dg["a"].get(a, 0)),
            "chats_closed": int(closed.get(a, 0)), "sales_chats": int(sales_chats.get(a, 0)),
            "fr_sum": float(fr["sum"].get(a, 0)) if a in fr.index else 0.0,
            "fr_n": int(fr["count"].get(a, 0)) if a in fr.index else 0,
            "fcr_checked": int(fcr_checked.get(a, 0)), "fcr_not_solved": int(fcr_not.get(a, 0)),
            "inbound_calls": int(inbound.get(a, 0)), "sales_usd": float(sales_usd.get(a, 0.0)),
            "qa_sum": float(qa["sum"].get(a, 0)) if a in qa.index else 0.0,
            "qa_n": int(qa["count"].get(a, 0)) if a in qa.index else 0,
        })
    A = pd.DataFrame(rows)
    team_raw = {k_: (float(A[k_].sum()) if not A.empty else 0.0) for k_ in
                ["working_days", "chats_closed", "inbound_calls", "fcr_checked", "fcr_not_solved", "absent_days",
                 "sales_usd", "sales_chats"]}
    if A.empty:
        return EngineResult(start, end, A, _team(None, team_raw, months, cfg), months, cut)

    A["night"] = A["night_shifts"] / A["working_days"] >= cfg["nightShiftShare"]
    A["quality"] = np.where(A["qa_n"] > 0, A["qa_sum"] / A["qa_n"].replace(0, np.nan), np.nan)
    A["fcr"] = np.where(A["fcr_checked"] > 0,
                        (A["fcr_checked"] - A["fcr_not_solved"]) / A["fcr_checked"].replace(0, np.nan), np.nan)
    A["chats"] = A["chats_closed"] / A["working_days"]
    A["calls"] = A["inbound_calls"] / A["working_days"]
    tsu, tsc = team_raw["sales_usd"], team_raw["sales_chats"]
    A["sales"] = [((u / tsu) / (sc / tsc)) if (tsu and tsc and sc) else 0.0 for u, sc in zip(A["sales_usd"], A["sales_chats"])]
    A["reply"] = np.where(A["fr_n"] > 0, A["fr_sum"] / A["fr_n"].replace(0, np.nan) / 60.0, np.nan)
    A["absence"] = A["absent_days"] / months
    A["share_sales"] = A["sales_usd"] / tsu if tsu else 0.0
    A["share_sales_chats"] = A["sales_chats"] / tsc if tsc else 0.0

    for key in KPI_KEYS:
        A[f"p_{key}"] = [kpi_points(cfg, key, None if pd.isna(v) else float(v)) for v in A[key]]
    day_calls = A.loc[~A["night"], "p_calls"]
    best_day = float(day_calls.max()) if len(day_calls) else 0.0
    A.loc[A["night"], "p_calls"] = best_day

    score = np.zeros(len(A))
    for key in KPI_KEYS:
        w = W[key]
        A[f"pts_{key}"] = A[f"p_{key}"] / w["pts"] * w["ptsNoFcr"] if w["pts"] else 0.0
        score += A[f"pts_{key}"].values
    A["score"] = score

    hits, counted = [], []
    for i, r in A.iterrows():
        h = o_ = 0
        for key in KPI_KEYS:
            if key == "calls" and r["night"]:
                A.at[i, f"met_{key}"] = "Night shift"
                continue
            v = r[key]
            if pd.isna(v):
                A.at[i, f"met_{key}"] = "No data"
                continue
            ok = v >= W[key]["target"] if W[key]["higher"] else v <= W[key]["target"]
            A.at[i, f"met_{key}"] = "Yes" if ok else "No"
            if key in TARGET_KEYS:          # bonus workbook: targets hit out of the 6 scored KPIs (FCR excluded)
                o_ += 1
                h += int(ok)
        hits.append(h)
        counted.append(o_)
    A["targets_hit"], A["targets_counted"] = hits, counted
    A["rank"] = [1 + int((A["score"] > s).sum()) for s in A["score"]]
    A["score_target_met"] = A["score"] >= cfg["teamTarget"]
    return EngineResult(start, end, A, _team(A, team_raw, months, cfg), months, cut)


def _team(A: pd.DataFrame | None, raw: dict, months: int, cfg: dict) -> dict:
    """Team results exactly as LS_Team defines them."""
    n = 0 if A is None else len(A)

    def avg(col):
        if A is None or A.empty:
            return np.nan
        v = A[col].dropna()
        return float(v.mean()) if len(v) else np.nan

    return {
        "quality": avg("quality"),
        "fcr": (raw["fcr_checked"] - raw["fcr_not_solved"]) / raw["fcr_checked"] if raw["fcr_checked"] else np.nan,
        "chats": raw["chats_closed"] / raw["working_days"] if raw["working_days"] else np.nan,
        "calls": raw["inbound_calls"] / raw["working_days"] if raw["working_days"] else np.nan,
        "sales": np.nan,                     # always 100% at team level: not scored for the team
        "reply": avg("reply"),
        "absence": raw["absent_days"] / n / months if n else np.nan,
        "score": avg("score"),
        "agents": n, "raw": raw, "months": months,
    }


def group_kpis(res: EngineResult, agents_subset: list, cfg: dict) -> dict:
    """Team-level KPIs for a subset of agents, using the same team formulas (pooled counts / agent averages).
    Agent values themselves (incl. sales contribution and rank) always come from the full-team run."""
    A = res.agents
    if A.empty:
        return _team(None, {k: 0.0 for k in ["working_days", "chats_closed", "inbound_calls", "fcr_checked",
                                              "fcr_not_solved", "absent_days", "sales_usd", "sales_chats"]},
                     res.months, cfg)
    S = A[A["agent"].isin(agents_subset)]
    raw = {k: float(S[k].sum()) for k in ["working_days", "chats_closed", "inbound_calls", "fcr_checked",
                                          "fcr_not_solved", "absent_days", "sales_usd", "sales_chats"]}
    return _team(S if not S.empty else None, raw, res.months, cfg)
