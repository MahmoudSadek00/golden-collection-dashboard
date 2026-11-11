"""Service layer used by every page and by the Excel export (one calculation path, cached per period)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from config import FROZEN_PERIODS, KPI_KEYS
from kpi_engine import TARGET_KEYS, EngineResult, compute, group_kpis
from periods import Period, coverage_status
from prepare import Dataset

FROZEN_COLS = {
    "Working Days": "working_days", "Night Shifts": "night_shifts", "Chats Closed (unique customers)": "chats_closed",
    "Inbound Calls": "inbound_calls", "FCR Chats Checked": "fcr_checked", "First Reply Chats": "fr_n",
    "Absent Days (sick + casual)": "absent_days", "Delivered Sales USD": "sales_usd",
    "Sales Chats (unique customers)": "sales_chats", "Share of Team Sales": "share_sales",
    "Share of Team Sales Chats": "share_sales_chats", "Quality %": "quality", "FCR %": "fcr",
    "Chats per Day": "chats", "Calls per Day": "calls", "Sales Contribution": "sales", "First Reply (min)": "reply",
    "Absence (days/month)": "absence", "Quality Points": "pts_quality", "Chats Points": "pts_chats",
    "Calls Points": "pts_calls", "Sales Points": "pts_sales", "First Reply Points": "pts_reply",
    "Absence Points": "pts_absence", "KPI Score": "score", "Rank": "rank", "Targets Hit": "targets_hit",
    "Targets Counted": "targets_counted",
}
FROZEN_MET = {"Quality Target Met": "met_quality", "FCR Target Met": "met_fcr", "Chats Target Met": "met_chats",
              "Calls Target Met": "met_calls", "Sales Target Met": "met_sales", "First Reply Target Met": "met_reply",
              "Absence Target Met": "met_absence"}
TEAM_KPI_NAMES = {"Quality %": "quality", "FCR %": "fcr", "Chats per day": "chats", "Calls per day": "calls",
                  "First reply (min)": "reply", "Absence (days/month)": "absence", "KPI Score": "score"}


def _num(v):
    try:
        return float(str(v).replace(",", "")) if str(v).strip() != "" else np.nan
    except ValueError:
        return np.nan


def _apply_frozen(ds: Dataset, p: Period, res: EngineResult) -> EngineResult:
    fa = ds.frozen_agents
    if fa.empty or p.kind != "Quarter" or p.label not in FROZEN_PERIODS:
        return res
    rows = fa[(fa["Period Type"] == "Quarter") & (fa["Period"] == p.label)]
    if rows.empty:
        return res
    A = res.agents.copy().set_index("agent") if not res.agents.empty else pd.DataFrame()
    recs = []
    for _, r in rows.iterrows():
        a = str(r["Agent"]).strip()
        base = A.loc[a].to_dict() if a in A.index else {}
        base["agent"] = a
        for src, dst in FROZEN_COLS.items():
            if src in r:
                base[dst] = _num(r[src])
        for src, dst in FROZEN_MET.items():
            if src in r:
                base[dst] = str(r[src])
        base["night"] = str(r.get("Night-shift agent", "")).strip() == "Yes"
        mets = [base.get(f"met_{k}", "") for k in TARGET_KEYS]
        base["targets_hit"] = sum(m == "Yes" for m in mets)
        base["targets_counted"] = sum(m in ("Yes", "No") for m in mets)
        base["score_target_met"] = str(r.get("Score Target Met", "")).strip() == "Yes"
        recs.append(base)
    agents = pd.DataFrame(recs)
    team = dict(res.team)
    ft = ds.frozen_team
    if not ft.empty:
        t = ft[(ft["Period Type"] == "Quarter") & (ft["Period"] == p.label)]
        for _, r in t.iterrows():
            k = TEAM_KPI_NAMES.get(str(r["KPI"]).strip())
            if k:
                team[k] = _num(r["Team Result"])
    team["frozen"] = True
    return EngineResult(res.start, res.end, agents, team, res.months, res.fcr_cutoff)


SCHEDULE_KPIS = ["score", "chats", "calls", "absence"]     # need working days / day statuses


def schedule_ok(ds: Dataset, p: Period) -> bool:
    """True when the schedule covers every day of the period that has chat data."""
    if p.label in FROZEN_PERIODS:
        return True
    st_to = ds.coverage.get("schedule_to")
    c_to = ds.coverage.get("chats_to")
    if pd.isna(st_to):
        return False
    last = min(p.end, c_to.normalize()) if pd.notna(c_to) else p.end
    return st_to >= last


def run_raw(ds: Dataset, p: Period) -> EngineResult:
    """Engine output exactly as LS_Scorecard would hold it (no masking)."""
    cache = ds.__dict__.setdefault("_runs", {})
    key = (p.kind, p.label, p.start, p.end)
    if key not in cache:
        cache[key] = _apply_frozen(ds, p, compute(ds, p.start, p.end))
    return cache[key]


def run(ds: Dataset, p: Period) -> EngineResult:
    """Engine output for display: KPIs that need working days are blanked when the schedule is missing."""
    res = run_raw(ds, p)
    if schedule_ok(ds, p):
        return res
    cache = ds.__dict__.setdefault("_masked", {})
    key = (p.kind, p.label, p.start, p.end)
    if key not in cache:
        A = res.agents.copy()
        if not A.empty:
            for k in SCHEDULE_KPIS:
                A[k] = np.nan
            for k in ["pts_chats", "pts_calls", "pts_absence", "rank"]:
                A[k] = np.nan
            for k in ["chats", "calls", "absence"]:
                A[f"met_{k}"] = "No data"
            mets = A[[f"met_{k}" for k in TARGET_KEYS]]
            A["targets_hit"] = (mets == "Yes").sum(axis=1)
            A["targets_counted"] = mets.isin(["Yes", "No"]).sum(axis=1)
            A["score_target_met"] = False
        T = dict(res.team)
        for k in SCHEDULE_KPIS:
            T[k] = np.nan
        T["schedule_missing"] = True
        cache[key] = EngineResult(res.start, res.end, A, T, res.months, res.fcr_cutoff)
    return cache[key]


def data_range(ds: Dataset):
    return ds.coverage["chats_from"], ds.coverage["chats_to"]


def coverage(ds: Dataset, p: Period) -> dict:
    f, t = data_range(ds)
    c = coverage_status(p, f, t)
    c["schedule_ok"] = schedule_ok(ds, p)
    st_to = ds.coverage.get("schedule_to")
    c["schedule_note"] = "" if c["schedule_ok"] else (
        f"Schedule entered only up to {st_to:%d %b %Y}: Chats per Day, Calls per Day, Absence and the KPI score "
        "cannot be calculated for this period" if pd.notna(st_to) else "No schedule data")
    return c


def scorecard(ds: Dataset, p: Period) -> pd.DataFrame:
    """Agent scorecard for a period with fairness flags used for rankings and insights."""
    res = run(ds, p)
    A = res.agents.copy()
    if A.empty:
        return A
    A["group"] = np.where(A["night"].astype(bool), "Night shift", "Day shift")
    A["team"] = A["agent"].map(ds.agent_team).fillna("CS")
    med = float(A["working_days"].median()) if len(A) else 0
    A["limited_data"] = A["working_days"] < 0.5 * med
    if not schedule_ok(ds, p):
        A["limited_data"] = True
    if p.scored:
        A["qa_missing"] = A["quality"].isna()
    else:
        A["qa_missing"] = False
    A["comparable"] = ~A["limited_data"] & ~A["qa_missing"]
    return A


def agent_groups(ds: Dataset, p: Period) -> dict:
    A = scorecard(ds, p)
    if A.empty:
        return {}
    return {g: sorted(s["agent"].tolist()) for g, s in A.groupby("group")}


def team(ds: Dataset, p: Period, agents: list | None = None) -> dict:
    res = run(ds, p)
    if not agents or res.agents.empty or set(agents) >= set(res.agents["agent"]):
        return res.team
    return group_kpis(res, agents, ds.cfg)


# ------------------------------------------------------------------------------------------------ operations
def _chats_in(ds: Dataset, p: Period, agents: list | None):
    c = ds.chats
    m = c["include"] & (c["team"] == "CS") & (c["started"] >= p.start) & (c["started"] < p.end + pd.Timedelta(days=1))
    if agents:
        m &= c["agent"].isin(agents)
    return c[m]


def _calls_in(ds: Dataset, p: Period, agents: list | None):
    k = ds.calls
    m = (k["type"] == "Inbound") & k["include"] & (k["date"] >= p.start) & (k["date"] <= p.end)
    if agents:
        m &= k["agent"].isin(agents)
    return k[m]


def _daily_in(ds: Dataset, p: Period, agents: list | None):
    d = ds.daily
    m = (d["date"] >= p.start) & (d["date"] <= p.end) & d["include"]
    if agents:
        m &= d["agent"].isin(agents)
    else:
        m &= d["team"] == "CS"
    return d[m]


def _ratio(n, d):
    return float(n) / float(d) if d and not pd.isna(d) and float(d) != 0 else np.nan


def ops(ds: Dataset, p: Period, agents: list | None = None) -> dict:
    """Operational metrics with the CS Pulse definitions."""
    c = _chats_in(ds, p, agents)
    k = _calls_in(ds, p, agents)
    d = _daily_in(ds, p, agents)
    ans = k[k["answered"] == 1]
    out = {
        "conversations": float(len(c)) if len(c) else np.nan,
        "customers": float(c["contact"].nunique()) if len(c) else np.nan,
        "frt_median": float(c["frt_sec"].median() / 60) if c["frt_sec"].notna().any() else np.nan,
        "resolution_median": float(c["resolution_sec"].median() / 3600) if c["resolution_sec"].notna().any() else np.nan,
        "messages_per_chat": float(c["messages"].mean()) if c["messages"].notna().any() else np.nan,
        "inbound_calls": float(k["inbound"].fillna(0).sum()) if len(k) else np.nan,
        "answer_rate": _ratio(k["answered"].fillna(0).sum(), k["inbound"].fillna(0).sum()) if len(k) else np.nan,
        "call_aht": float(ans["handling_sec"].fillna(0).mean()) if len(ans) else np.nan,
        "call_wait": float(ans["waiting_sec"].fillna(0).mean()) if len(ans) else np.nan,
        "adherence": _ratio(d["Adherence Num"].sum(), d["Adherence Den"].sum()) if len(d) else np.nan,
        "occupancy": _ratio(d["Occupancy Num"].sum(), d["Occupancy Den"].sum()) if len(d) else np.nan,
        "shrinkage": _ratio(d["Shrinkage Num"].sum(), d["Shrinkage Den"].sum()) if len(d) else np.nan,
    }
    return out


def ops_by_agent(ds: Dataset, p: Period, agents: list) -> pd.DataFrame:
    rows = []
    for a in agents:
        o = ops(ds, p, [a])
        o["agent"] = a
        rows.append(o)
    return pd.DataFrame(rows)


def chat_breakdowns(ds: Dataset, p: Period, agents: list | None = None) -> dict:
    c = _chats_in(ds, p, agents)
    k = _calls_in(ds, p, agents)
    out = {}
    out["daily"] = c.groupby(c["started"].dt.normalize()).agg(conversations=("id", "size"),
                                                               customers=("contact", "nunique")).reset_index() \
        .rename(columns={"started": "date"})
    out["hour"] = c.groupby(c["started"].dt.hour).size().rename("conversations").reset_index() \
        .rename(columns={"started": "hour"})
    out["weekday"] = c.groupby(c["started"].dt.dayofweek).size().rename("conversations").reset_index() \
        .rename(columns={"started": "dow"})
    out["topic"] = c.groupby("topic").size().rename("conversations").sort_values(ascending=False).reset_index()
    out["market"] = c.groupby("market").size().rename("conversations").sort_values(ascending=False).reset_index()
    out["calls_hour"] = k.groupby("hour").size().rename("calls").reset_index()
    sent = k[k["answered"] == 1]
    out["sentiment"] = sent.groupby(sent["sentiment"].replace("", "Not rated")).size().rename("calls").reset_index()
    out["calls_daily"] = k.groupby("date").agg(inbound=("inbound", "sum"), answered=("answered", "sum")).reset_index()
    return out


# ------------------------------------------------------------------------------------------------ history
def month_series(ds: Dataset, months: list, agents: list | None = None) -> pd.DataFrame:
    """Team KPI + ops values per month (chronological)."""
    recs = []
    for p in sorted(months, key=lambda x: x.start):
        t = team(ds, p, agents)
        o = ops(ds, p, agents)
        rec = {"period": p.label, "start": p.start}
        rec.update({k: t.get(k, np.nan) for k in KPI_KEYS + ["score"]})
        rec.update(o)
        recs.append(rec)
    return pd.DataFrame(recs)


def agent_month_series(ds: Dataset, months: list, agent: str) -> pd.DataFrame:
    recs = []
    for p in sorted(months, key=lambda x: x.start):
        A = run(ds, p).agents
        row = A[A["agent"] == agent] if not A.empty else A
        rec = {"period": p.label, "start": p.start}
        for k in KPI_KEYS + ["score", "rank", "working_days"]:
            rec[k] = float(row[k].iloc[0]) if len(row) and k in row else np.nan
        recs.append(rec)
    return pd.DataFrame(recs)
