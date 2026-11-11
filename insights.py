"""Evidence-based management insights. Every finding is computed from the selected period, comparison period
and filters; nothing is hard-coded. Findings are labelled 'Confirmed' (measured) or 'Possible explanation'
(a plausible link between two measured facts, not a proven cause)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

import analytics as an
import comparison as cmp
from kpis import ALL_KPIS, fmt, fmt_delta, is_missing
from periods import Period
from prepare import Dataset

SEV_RANK = {"critical": 0, "warning": 1, "positive": 2, "info": 3}


@dataclass
class Insight:
    severity: str           # critical | warning | positive | info
    area: str               # Team | KPI | Agent | Operations | Data
    title: str
    what: str
    why: str = ""
    action: str = ""
    basis: str = "Confirmed"
    weight: float = 0.0     # impact used for ordering inside a severity

    def as_row(self) -> dict:
        return {"Priority": self.severity.title(), "Area": self.area, "Finding": self.title, "What happened": self.what,
                "Why it matters": self.why, "Recommended action": self.action, "Basis": self.basis}


WHY = {
    "reply": "Slower first replies keep customers waiting and tend to generate follow-up messages and repeat contacts.",
    "chats": "Productivity below target reduces coverage; at 50 chats a day or less the KPI earns no points.",
    "calls": "Fewer inbound calls per working day handled means more pressure on the remaining agents or missed calls.",
    "quality": "QA below target signals handling errors that affect customer experience and FCR.",
    "fcr": "Customers who come back for the same problem add workload and indicate unresolved issues.",
    "absence": "Absence above one day a month reduces capacity and puts pressure on schedule coverage.",
    "score": "The team score is the agreed summary of CS performance against the bonus-calculator rules.",
    "answer_rate": "Unanswered inbound calls are lost contacts and a direct customer-experience risk.",
    "adherence": "Low adherence means agents are not available when they were scheduled, which affects coverage.",
    "shrinkage": "Higher shrinkage reduces productive time available for customers.",
    "frt_median": "The typical customer waits longer for a first answer.",
    "call_aht": "Longer handling time reduces call capacity; it can also reflect more complex enquiries.",
    "call_wait": "Longer waiting time increases the risk of abandoned calls.",
    "resolution_median": "Chats stay open longer before resolution.",
}


def _low(label: str) -> str:
    return " ".join(w if w.isupper() else w.lower() for w in label.split())


def _names(lst, n=4):
    lst = list(lst)
    return ", ".join(lst[:n]) + (f" and {len(lst) - n} more" if len(lst) > n else "")


def generate(ds: Dataset, cur: Period, prev: Period, agents: list | None = None) -> list:
    out: list = []
    T = cmp.targets(ds)
    cov = an.coverage(ds, cur)
    team_cmp = cmp.compare_team(ds, cur, prev, agents)
    tc = team_cmp.set_index("key")
    A = an.scorecard(ds, cur)
    if agents and not A.empty:
        A = A[A["agent"].isin(agents)]
    W = ds.cfg["weights"]

    # ---------------------------------------------------------------- data caveats first (affect everything)
    if cov.get("note"):
        out.append(Insight("info", "Data", f"{cur.short()} is not a complete period",
                           cov["note"] + ". Totals are partial; rates and averages are shown for the days available.",
                           "", "Compare rates rather than totals until the period is complete."))
    if not cov.get("schedule_ok", True):
        out.append(Insight("critical", "Data", "Schedule missing: per-day KPIs and score unavailable",
                           cov["schedule_note"] + ".",
                           "Without working days these KPIs would be overstated, so they are withheld rather than estimated.",
                           "Update the Schedule tab; the KPIs appear automatically after the next data refresh."))
    if cur.scored and not A.empty and A["qa_missing"].any():
        miss = A.loc[A["qa_missing"], "agent"].tolist()
        out.append(Insight("warning", "Data", "QA scores not entered for this period",
                           f"No QA score for {_names(miss)}. Quality earns 0 of {W['quality']['ptsNoFcr']:.0f} points "
                           "for them, so their KPI score is understated and excluded from rankings.",
                           "Scores without QA are not comparable with the rest of the team.",
                           "Enter the QA scores in QA_Input; the scorecard updates on the next refresh."))

    # ---------------------------------------------------------------- overall score
    if cur.scored and "score" in tc.index and not is_missing(tc.loc["score", "current"]):
        s = tc.loc["score"]
        n_ok = int(A["score_target_met"].sum()) if not A.empty else 0
        chg = "" if is_missing(s["previous"]) else f" ({fmt_delta('score', s['change'])} vs {prev.short()}: {s['previous']:.1f})"
        met = s["current"] >= T["score"]
        # points lost per KPI (where the shortfall comes from)
        lost = {}
        if not A.empty:
            for k in ["quality", "chats", "calls", "sales", "reply", "absence"]:
                mx = W[k]["ptsNoFcr"]
                if mx:
                    lost[k] = float(mx - A[f"pts_{k}"].mean())
        top = sorted(lost.items(), key=lambda x: -x[1])[:2]
        drivers = "; ".join(f"{ALL_KPIS[k].label} {v:.1f} of {W[k]['ptsNoFcr']:.0f} pts" for k, v in top if v > 0.05)
        out.append(Insight(
            "positive" if met else ("critical" if s["trend"] == "declined" else "warning"), "Team",
            f"Team KPI score {s['current']:.1f} vs target {T['score']:.0f}",
            f"Average agent score is {s['current']:.1f}{chg}; {n_ok} of {len(A)} agents reach {T['score']:.0f}."
            + (f" Largest average point losses: {drivers}." if drivers else ""),
            WHY["score"],
            "" if met else (f"Prioritise {_low(ALL_KPIS[top[0][0]].label)}: it accounts for the largest share of "
                            f"points lost across the team." if top else ""),
            weight=abs(T["score"] - s["current"])))

    # ---------------------------------------------------------------- KPIs vs target (team level)
    flagged = set()
    for k in ["quality", "chats", "calls", "reply", "absence", "fcr"]:
        if k not in tc.index:
            continue
        r = tc.loc[k]
        if is_missing(r["current"]) or r["met_current"] is None:
            continue
        lbl = ALL_KPIS[k].label
        prev_txt = "" if is_missing(r["previous"]) else f"; {prev.short()}: {fmt(k, r['previous'])} ({fmt_delta(k, r['change'])})"
        if r["met_current"] is False:
            laggards = _laggards(A, k, T[k])
            act = _action(ds, cur, k, laggards, agents)
            g = abs(r["current"] - r["target"]) / abs(r["target"]) if r["target"] else 0
            flagged.add(k)
            out.append(Insight("critical" if (r["trend"] == "declined" or g > 0.15) else "warning", "KPI",
                               f"{lbl} below target: {fmt(k, r['current'])} vs {fmt(k, r['target'])}",
                               f"Team {_low(lbl)} is {fmt(k, r['current'])} against a target of {fmt(k, r['target'])}"
                               f"{prev_txt}." + (f" Agents furthest from target: {_names(laggards)}." if laggards else ""),
                               WHY.get(k, ""), act, weight=g))
        elif r["trend"] in ("improved", "stable"):
            flagged.add(k)
            out.append(Insight("positive", "KPI", f"{lbl} on target: {fmt(k, r['current'])}",
                               f"Team {_low(lbl)} meets the {fmt(k, r['target'])} target{prev_txt}.",
                               "", "", weight=0.01))

    # ---------------------------------------------------------------- biggest movements vs comparison period
    mv = team_cmp[team_cmp["trend"].isin(["improved", "declined"]) & team_cmp["change_pct"].notna()].copy()
    mv["abs"] = mv["change_pct"].abs()
    mv = mv[~(mv["key"].isin(flagged))]
    for _, r in mv.sort_values("abs", ascending=False).head(4).iterrows():
        k = r["key"]
        good = r["trend"] == "improved"
        out.append(Insight("positive" if good else "warning", "Operations" if r["family"] == "Operations" else "KPI",
                           f"{r['KPI']} {'improved' if good else 'deteriorated'} {abs(r['change_pct']) * 100:.0f}% vs {prev.short()}",
                           f"{r['KPI']}: {fmt(k, r['current'])} in {cur.short()} vs {fmt(k, r['previous'])} in "
                           f"{prev.short()} ({fmt_delta(k, r['change'])}).",
                           WHY.get(k, "") if not good else "",
                           "" if good else _action(ds, cur, k, _laggards(A, k, T.get(k)) if k in T else [], agents),
                           weight=float(r["abs"])))

    # ---------------------------------------------------------------- possible explanation: workload vs speed
    if {"conversations", "frt_median"} <= set(tc.index):
        v, f = tc.loc["conversations"], tc.loc["frt_median"]
        wd_c = an.team(ds, cur, agents).get("raw", {}).get("working_days", np.nan)
        wd_p = an.team(ds, prev, agents).get("raw", {}).get("working_days", np.nan)
        if not any(is_missing(x) for x in [v["current"], v["previous"], wd_c, wd_p]) and wd_c and wd_p:
            load_c, load_p = v["current"] / wd_c, v["previous"] / wd_p
            if f["trend"] == "declined" and load_c > load_p * 1.05:
                out.append(Insight("info", "Operations", "Slower first replies coincide with higher workload",
                                   f"Conversations per agent working day rose from {load_p:.0f} to {load_c:.0f} "
                                   f"({(load_c / load_p - 1) * 100:.0f}%) while median first reply moved from "
                                   f"{fmt('frt_median', f['previous'])} to {fmt('frt_median', f['current'])}.",
                                   "Higher volume per agent is a likely contributor, not a proven cause.",
                                   "Check staffing against hourly demand before attributing the change to individual agents.",
                                   basis="Possible explanation", weight=0.05))

    # ---------------------------------------------------------------- agents
    if not A.empty:
        comp = A[A["comparable"]]
        if cur.scored and len(comp):
            below = comp[~comp["score_target_met"]].sort_values("score")
            if len(below):
                lst = [f"{a} ({s:.1f})" for a, s in zip(below["agent"], below["score"])]
                out.append(Insight("warning", "Agent", f"{len(below)} agent(s) below the {T['score']:.0f}-point target",
                                   f"Below target: {_names(lst, 6)}.",
                                   "Individual shortfalls drive the team average below target.",
                                   "Review each agent's weakest KPI in the Agent Profile and agree a specific improvement goal.",
                                   weight=float(len(below)) / max(1, len(comp))))
        many = A[(A["targets_counted"] > 0) & (A["targets_counted"] - A["targets_hit"] >= 3)]
        if len(many):
            out.append(Insight("warning", "Agent", f"{len(many)} agent(s) miss three or more KPI targets",
                               "; ".join(f"{a}: {int(c - h)} of {int(c)} targets missed" for a, h, c in
                                         zip(many["agent"], many["targets_hit"], many["targets_counted"])) + ".",
                               "Gaps across several KPIs usually point to a broader coaching need rather than one skill.",
                               "Plan a structured coaching review for these agents.", weight=0.2))
        ac = cmp.compare_agents(ds, cur, prev, agents)
        if not ac.empty and cur.scored and prev.scored and "score_chg" in ac:
            ok = ac[ac["comparable_now"] & ac["comparable_before"] & ac["score_chg"].notna()]
            up = ok[ok["score_chg"] >= 5].sort_values("score_chg", ascending=False)
            dn = ok[ok["score_chg"] <= -5].sort_values("score_chg")
            if len(up):
                out.append(Insight("positive", "Agent", "Notable individual improvements",
                                   "; ".join(f"{a}: {p:.1f} → {c:.1f} ({d:+.1f} pts)" for a, p, c, d in
                                             zip(up["agent"], up["score_prev"], up["score_cur"], up["score_chg"])) + ".",
                                   "", "Recognise the improvement and identify practices that can be shared.", weight=0.1))
            if len(dn):
                out.append(Insight("warning", "Agent", "Notable individual declines",
                                   "; ".join(f"{a}: {p:.1f} → {c:.1f} ({d:+.1f} pts)" for a, p, c, d in
                                             zip(dn["agent"], dn["score_prev"], dn["score_cur"], dn["score_chg"])) + ".",
                                   "A sudden drop often has a specific cause (schedule, topic mix, absence).",
                                   "Review the KPI breakdown for these agents before the next one-to-one.", weight=0.3))
        lim = A[A["limited_data"]]
        if len(lim):
            out.append(Insight("info", "Data", "Agents with limited working days",
                               f"{_names(lim['agent'])} worked fewer than half of the team's median working days "
                               f"({A['working_days'].median():.0f}). Their figures are shown but excluded from rankings.",
                               "", ""))

    out.sort(key=lambda i: (SEV_RANK.get(i.severity, 9), -i.weight))
    return out


def _laggards(A: pd.DataFrame, k: str, target) -> list:
    if A is None or A.empty or k not in A or is_missing(target):
        return []
    d = A[A[k].notna()].copy()
    if k == "calls":
        d = d[~d["night"].astype(bool)]
    hi = ALL_KPIS[k].direction == "higher"
    miss = d[d[k] < target] if hi else d[d[k] > target]
    miss = miss.sort_values(k, ascending=hi)
    return [f"{a} ({fmt(k, v)})" for a, v in zip(miss["agent"], miss[k])][:4]


def _action(ds: Dataset, p: Period, k: str, laggards: list, agents) -> str:
    if k == "reply":
        b = an.chat_breakdowns(ds, p, agents)
        peak = ""
        if not b["hour"].empty:
            h = int(b["hour"].sort_values("conversations", ascending=False).iloc[0]["hour"])
            peak = f" Chat demand peaks at {h:02d}:00–{(h + 1) % 24:02d}:00; check cover for that window."
        return ("Review first-response handling with the agents furthest from target." + peak)
    if k == "chats":
        return "Review workload distribution and concurrent-chat handling for agents below target; confirm schedules match demand."
    if k == "calls":
        return "Check call routing and availability of day-shift agents for inbound calls."
    if k == "quality":
        return "Use the QA findings for targeted coaching of agents below 85%."
    if k == "fcr":
        t = _fcr_topics(ds, p, agents)
        return ("Review the topics with the most repeat contacts" + (f" ({t})" if t else "") +
                " and the root causes behind them (delivery, product, refund process).")
    if k == "absence":
        return "Follow up absence patterns with the agents concerned in line with HR policy."
    if k == "answer_rate":
        return "Review call coverage by hour against inbound demand."
    if k == "adherence":
        return "Review login and break discipline with the agents with the lowest adherence."
    if k == "shrinkage":
        return "Review break, coaching and technical time against plan."
    return "Investigate the drivers with the team lead."


def _fcr_topics(ds: Dataset, p: Period, agents) -> str:
    c = ds.chats
    m = c["fcr_base"] & (c["started"] >= p.start) & (c["started"] < p.end + pd.Timedelta(days=1))
    if agents:
        m &= c["agent"].isin(agents)
    d = c[m]
    if d.empty:
        return ""
    g = d.groupby("topic")["fcr_back"].agg(["sum", "count"])
    g = g[g["count"] >= 30].sort_values("sum", ascending=False).head(2)
    return ", ".join(f"{t}: {int(s)} repeats of {int(n)}" for t, (s, n) in g.iterrows())
