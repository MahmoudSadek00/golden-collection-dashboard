"""Turns raw text tabs into typed, validated tables (the single data model used by every page and export).

Rules:
* Blank or invalid values become missing (NaN / NaT). They are never turned into zero, except where the approved
  LookerKPI script itself does so (e.g. a blank "Working Day" counts as 0 working days).
* Agent names are mapped to the official name through CS_NameMap, as the script does.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from config import KPI_DEFAULTS, KPI_SHEET_NAMES, REQUIRED_COLUMNS
from data_loader import RawData

_DT_RE = r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?"


def parse_dt(s: pd.Series) -> pd.Series:
    """Parses 'yyyy-mm-dd[ hh:mm[:ss]]' text (the sheets' display format). Anything else becomes NaT."""
    if s is None or len(s) == 0:
        return pd.Series(pd.NaT, index=getattr(s, "index", None), dtype="datetime64[ns]")
    p = s.astype(str).str.extract(_DT_RE)
    p = p.apply(pd.to_numeric, errors="coerce")
    out = pd.to_datetime(dict(year=p[0], month=p[1], day=p[2], hour=p[3].fillna(0), minute=p[4].fillna(0),
                              second=p[5].fillna(0)), errors="coerce")
    return out


def num(s: pd.Series) -> pd.Series:
    t = s.astype(str).str.replace(",", "", regex=False).str.strip()
    pct = t.str.endswith("%")
    v = pd.to_numeric(t.str.rstrip("%"), errors="coerce")
    return v.where(~pct, v / 100.0)


def clean(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip()


def yes(s: pd.Series) -> pd.Series:
    return clean(s).str.lower().isin(["yes", "y", "true", "1"])


@dataclass
class Issue:
    level: str        # "critical" | "warning" | "info"
    area: str
    message: str


@dataclass
class Dataset:
    chats: pd.DataFrame
    daily: pd.DataFrame
    calls: pd.DataFrame
    orders: pd.DataFrame
    qa: pd.DataFrame
    kpi_agents: list
    agent_team: dict
    cfg: dict
    fcr_topics: pd.DataFrame
    sales_topics: set
    frozen_agents: pd.DataFrame
    frozen_team: pd.DataFrame
    ls_scorecard: pd.DataFrame
    ls_team: pd.DataFrame
    max_started: pd.Timestamp
    coverage: dict
    issues: list = field(default_factory=list)
    source: str = ""
    loaded_at: str = ""


def _check(frames: dict, key: str, issues: list) -> pd.DataFrame | None:
    df = frames.get(key)
    if df is None or df.empty:
        return None
    miss = [c for c in REQUIRED_COLUMNS.get(key, []) if c not in df.columns]
    if miss:
        issues.append(Issue("critical", key, f"Missing columns: {', '.join(miss)}"))
    return df


def _col(df: pd.DataFrame, name: str, default="") -> pd.Series:
    return df[name] if name in df.columns else pd.Series(default, index=df.index, dtype=object)


def _config(targets: pd.DataFrame | None) -> dict:
    cfg = copy.deepcopy(KPI_DEFAULTS)
    if targets is None or targets.empty:
        return cfg
    key = {v: k for k, v in KPI_SHEET_NAMES.items()}
    for _, r in targets.iterrows():
        name = str(r.get("KPI", "")).strip()
        pts = pd.to_numeric(str(r.get("Points in score", "")).strip() or np.nan, errors="coerce")
        tgt = pd.to_numeric(str(r.get("Target", "")).strip() or np.nan, errors="coerce")
        if name == "Team score target":
            if pd.notna(tgt) and tgt:
                cfg["teamTarget"] = float(tgt)
            continue
        k = key.get(name)
        if not k:
            continue
        if pd.notna(pts):
            cfg["weights"][k]["ptsNoFcr"] = float(pts)
        if pd.notna(tgt):
            cfg["weights"][k]["target"] = float(tgt)
    return cfg


def _split_frozen(df: pd.DataFrame | None):
    """KPI_Frozen_Q3 holds the LS_Scorecard Q3 rows, a blank row, a caption and then the LS_Team Q3 rows."""
    if df is None or df.empty:
        return pd.DataFrame(), pd.DataFrame()
    first = df.iloc[:, 0].astype(str)
    hdr = first[first == "Period Type"].index
    agents = df[first.isin(["Month", "Quarter"])].copy()
    team = pd.DataFrame()
    if len(hdr):
        h = hdr[0]
        cols = [str(c) for c in df.loc[h].tolist()]
        body = df.loc[h + 1:].copy()
        body.columns = cols
        body = body[body["Period Type"].astype(str).isin(["Month", "Quarter"])]
        team = body.loc[:, [c for c in cols if c]]
        agents = df.loc[:h - 1]
        agents = agents[agents.iloc[:, 0].astype(str).isin(["Month", "Quarter"])].copy()
        agents = agents[agents["Agent"].astype(str).str.strip() != ""]
    return agents.reset_index(drop=True), team.reset_index(drop=True)


def prepare(raw: RawData) -> Dataset:
    issues: list = []
    F = raw.frames
    for t in raw.missing:
        issues.append(Issue("critical" if t in ("CS_Chats", "CS_Agent_Daily") else "warning", t, "Tab not found"))

    # ---- name mapping (CS_NameMap: written name -> official name)
    nm = F.get("name_map")
    name_map = {}
    if nm is not None and not nm.empty:
        for a, b in zip(clean(nm.iloc[:, 0]), clean(nm.iloc[:, 1])):
            if a:
                name_map[a] = b

    def canon(s: pd.Series) -> pd.Series:
        s = clean(s)
        return s.map(lambda x: name_map.get(x, x))

    # ---- agents / teams
    ag = F.get("agents")
    agent_team = {}
    if ag is not None and not ag.empty and "Agent" in ag.columns:
        for a, t in zip(canon(ag["Agent"]), clean(_col(ag, "Team"))):
            if a:
                agent_team[a] = t or "Unassigned"

    ka = _check(F, "kpi_agents", issues)
    kpi_agents = []
    if ka is not None:
        sel = ka[yes(ka["In KPI score"]) & (clean(ka["Agent"]) != "")]
        kpi_agents = list(dict.fromkeys(canon(sel["Agent"]).tolist()))
    if not kpi_agents:
        issues.append(Issue("critical", "KPI_Agents", "No agent is marked 'Yes' for the KPI score"))

    cfg = _config(F.get("kpi_targets"))

    # ---- topic tables
    ft = F.get("fcr_topics")
    fcr_topics = pd.DataFrame(columns=["topic", "group", "used"])
    if ft is not None and not ft.empty:
        fcr_topics = pd.DataFrame({"topic": clean(ft.iloc[:, 0]), "group": clean(ft.iloc[:, 1]),
                                   "used": yes(ft.iloc[:, 3]) if ft.shape[1] > 3 else False})
        fcr_topics = fcr_topics[fcr_topics["topic"] != ""].drop_duplicates("topic", keep="last")
    st_ = F.get("sales_topics")
    sales_topics = set()
    if st_ is not None and not st_.empty:
        sales_topics = set(clean(st_.iloc[:, 0])[yes(st_.iloc[:, 1])])

    # ---- chats
    c = _check(F, "chats", issues)
    if c is None:
        c = pd.DataFrame(columns=REQUIRED_COLUMNS["chats"])
    chats = pd.DataFrame({
        "id": clean(_col(c, "Conversation ID")),
        "contact": clean(_col(c, "Contact ID")),
        "started": parse_dt(_col(c, "Started")),
        "resolved": parse_dt(_col(c, "Resolved")),
        "agent": canon(_col(c, "Agent")),
        "team": clean(_col(c, "Team")),
        "include": clean(_col(c, "Include")) == "Yes",
        "market": clean(_col(c, "Market")),
        "topic": clean(_col(c, "Topic")),
        "opened_by": clean(_col(c, "Opened By")),
        "frt_sec": num(_col(c, "First Assignment to First Response (sec)")),
        "resolution_sec": num(_col(c, "Resolution (sec)")),
        "messages": num(_col(c, "Messages")),
        "closed_by_raw": clean(_col(c, "Closed By Agent")),
    })
    chats = chats[chats["id"] != ""].reset_index(drop=True)
    cb = chats["closed_by_raw"]
    bad = (cb == "") | cb.str.startswith("(") | cb.str.startswith("Unknown ID")
    chats["closed_by"] = canon(cb).where(~bad, "")
    chats["date"] = chats["started"].dt.normalize()
    bad_dates = int(chats["started"].isna().sum())
    if bad_dates:
        issues.append(Issue("warning", "CS_Chats", f"{bad_dates:,} chats have no valid start date and are excluded"))
    grp = dict(zip(fcr_topics["topic"], fcr_topics["group"]))
    used = dict(zip(fcr_topics["topic"], fcr_topics["used"]))
    chats["fcr_group"] = chats["topic"].map(grp).fillna("")
    chats["fcr_base"] = ((chats["opened_by"] == "Customer") & chats["topic"].map(used).astype("boolean").fillna(False).astype(bool)
                         & chats["resolved"].notna())
    chats["is_sales_topic"] = chats["topic"].isin(sales_topics)
    chats["fcr_back"] = _fcr_back(chats, cfg["fcrWindowDays"])
    max_started = chats["started"].max()

    # ---- daily
    d = _check(F, "daily", issues)
    if d is None:
        d = pd.DataFrame(columns=REQUIRED_COLUMNS["daily"])
    daily = pd.DataFrame({"agent": canon(_col(d, "Agent")), "team": clean(_col(d, "Team")),
                          "include": clean(_col(d, "Include")) == "Yes", "date": parse_dt(_col(d, "Date")),
                          "shift": clean(_col(d, "Shift")), "status": clean(_col(d, "Day Status"))})
    daily["working"] = num(_col(d, "Working Day")).fillna(0)           # script: Number(x) || 0
    for col in ["Adherence Num", "Adherence Den", "Occupancy Num", "Occupancy Den", "Shrinkage Num", "Shrinkage Den",
                "Planned Min", "Scheduled Min", "Late Min", "Online Min", "Busy Min", "Break Min", "Chats Assigned",
                "Calls Answered", "WFH"]:
        daily[col] = num(_col(d, col)) if col in d.columns else np.nan
    daily = daily[daily["date"].notna() & (daily["agent"] != "")].reset_index(drop=True)

    # ---- calls
    k = _check(F, "calls", issues)
    if k is None:
        k = pd.DataFrame(columns=REQUIRED_COLUMNS["calls"])
    calls = pd.DataFrame({"id": clean(_col(k, "Call ID")), "date": parse_dt(_col(k, "Date")),
                          "hour": num(_col(k, "Hour")), "type": clean(_col(k, "Type")), "agent": canon(_col(k, "Agent")),
                          "include": clean(_col(k, "Include")) == "Yes", "answered": num(_col(k, "Answered")),
                          "inbound": num(_col(k, "Inbound")), "handling_sec": num(_col(k, "Handling (sec)")),
                          "waiting_sec": num(_col(k, "Waiting (sec)")), "sentiment": clean(_col(k, "Sentiment"))})
    calls = calls[calls["date"].notna()].reset_index(drop=True)

    # ---- orders (Orders - Clean Data / Agent_Orders)
    o = _check(F, "orders", issues)
    if o is None:
        o = pd.DataFrame(columns=REQUIRED_COLUMNS["orders"])
    orders = pd.DataFrame({"date": parse_dt(_col(o, "Order Date")), "status": clean(_col(o, "Status")),
                           "usd": num(_col(o, "Order Value (USD)")), "agent": canon(_col(o, "Agent")),
                           "country": clean(_col(o, "Country"))})
    orders = orders[orders["date"].notna()].reset_index(drop=True)

    # ---- QA
    q = _check(F, "qa", issues)
    qa = pd.DataFrame(columns=["agent", "month", "score"])
    if q is not None:
        qa = pd.DataFrame({"agent": canon(q.iloc[:, 0]), "month": clean(q.iloc[:, 1]).str.slice(0, 7),
                           "score": num(q.iloc[:, 2])})
        qa = qa[qa["agent"] != ""]

    frozen_agents, frozen_team = _split_frozen(F.get("frozen_q3"))
    if frozen_agents.empty:
        issues.append(Issue("warning", "KPI_Frozen_Q3", "Frozen Q3 results not found; Q3 is shown as recalculated"))

    coverage = {
        "chats_from": chats["started"].min(), "chats_to": chats["started"].max(),
        "daily_from": daily.loc[daily["working"] > 0, "date"].min(), "daily_to": daily.loc[daily["working"] > 0, "date"].max(),
        "calls_from": calls["date"].min(), "calls_to": calls["date"].max(),
        "orders_from": orders["date"].min(), "orders_to": orders["date"].max(),
        "qa_months": sorted(qa.dropna(subset=["score"])["month"].unique().tolist()),
        # last day the schedule (CS_Agent_Daily) has a real status for the KPI agents
        "schedule_to": daily.loc[daily["agent"].isin(kpi_agents) & ~daily["status"].isin(["Not scheduled", ""]), "date"].max(),
    }
    if pd.notna(coverage["schedule_to"]) and pd.notna(coverage["chats_to"]) and \
            coverage["schedule_to"] < coverage["chats_to"].normalize():
        issues.append(Issue("warning", "CS_Agent_Daily",
                            f"Schedule entered only up to {coverage['schedule_to']:%d %b %Y}; chats run to "
                            f"{coverage['chats_to']:%d %b %Y}. Per-working-day KPIs and the KPI score are not shown "
                            "for days without a schedule."))
    return Dataset(chats=chats, daily=daily, calls=calls, orders=orders, qa=qa, kpi_agents=kpi_agents,
                   agent_team=agent_team, cfg=cfg, fcr_topics=fcr_topics, sales_topics=sales_topics,
                   frozen_agents=frozen_agents, frozen_team=frozen_team,
                   ls_scorecard=F.get("ls_scorecard", pd.DataFrame()), ls_team=F.get("ls_team", pd.DataFrame()),
                   max_started=max_started, coverage=coverage, issues=issues, source=raw.source,
                   loaded_at=raw.loaded_at)


def _fcr_back(chats: pd.DataFrame, window_days: int) -> pd.Series:
    """True when the same customer opened another chat of the same problem group within the window after
    this chat was resolved (the script's 'came back' test). Only meaningful where fcr_base is True."""
    out = pd.Series(False, index=chats.index)
    base = chats[chats["fcr_base"]]
    pool = chats[(chats["opened_by"] == "Customer") & (chats["fcr_group"] != "") & chats["started"].notna()]
    if base.empty or pool.empty:
        return out
    left = base[["contact", "fcr_group", "resolved"]].reset_index().rename(columns={"index": "row"})
    right = pool[["contact", "fcr_group", "started"]].rename(columns={"started": "next_start"})
    left = left.sort_values("resolved")
    right = right.sort_values("next_start")
    m = pd.merge_asof(left, right, left_on="resolved", right_on="next_start", by=["contact", "fcr_group"],
                      direction="forward", allow_exact_matches=False)
    win = pd.Timedelta(days=window_days)
    back = m["next_start"].notna() & (m["next_start"] <= m["resolved"] + win)
    out.loc[m["row"].values] = back.values
    return out
