"""Executive Overview: where we are, where we were, direction of travel, what needs attention."""
from __future__ import annotations

import numpy as np
import streamlit as st

import analytics as an
import comparison as cmp
import insights as ins
import logi as L
from kpis import is_missing
import charts as CH
import components as C
from common import header, history_months, show_team_table, team_table


def page() -> None:
    ds, f = header("Executive Overview", "Customer Support Performance",
                   "Current position against target, change versus the comparison period and the issues that need attention.")
    cur, prev = f.period, f.compare
    tc = an.team(ds, cur, f.agents)
    tp = an.team(ds, prev, f.agents) if prev else {}
    T = cmp.targets(ds)
    cov = an.coverage(ds, cur)
    pl = prev.short() if prev else ""
    oc = an.ops(ds, cur, f.agents)
    op = an.ops(ds, prev, f.agents) if prev else {}
    A = an.scorecard(ds, cur)
    if f.agents and not A.empty:
        A = A[A["agent"].isin(f.agents)]

    # ---------------------------------------------------------------- headline
    left, *rest = st.columns([1.5, 1, 1, 1], gap="small")
    with left:
        if not cur.scored:
            C.hero_score(np.nan, T["score"], None, "", "", unavailable="The KPI score is defined per month and quarter. "
                         "Select a month or quarter to see it.")
        elif not cov.get("schedule_ok", True):
            C.hero_score(np.nan, T["score"], None, "", "", unavailable=cov["schedule_note"])
        else:
            n_ok = int(A["score_target_met"].sum()) if not A.empty else 0
            ttl = "Team KPI score" + (" (frozen)" if tc.get("frozen") else "")
            C.hero_score(tc.get("score"), T["score"], tp.get("score") if prev and prev.scored else None, pl,
                         f"{n_ok} of {len(A)} agents on target", label=ttl)
    sched = "" if cov.get("schedule_ok", True) else "Schedule not entered for this period"
    items = [
        dict(key="quality", value=tc.get("quality"), target=T["quality"], prev=tp.get("quality") if prev else None,
             prev_label=pl, unavailable="" if cur.scored else "Monthly QA only"),
        dict(key="chats", value=tc.get("chats"), target=T["chats"], prev=tp.get("chats") if prev else None,
             prev_label=pl, unavailable=sched),
        dict(key="reply", value=tc.get("reply"), target=T["reply"], prev=tp.get("reply") if prev else None, prev_label=pl),
        dict(key="fcr", value=tc.get("fcr"), target=T["fcr"], prev=tp.get("fcr") if prev else None, prev_label=pl,
             note_txt="Monitor only"),
        dict(key="calls", value=tc.get("calls"), target=T["calls"], prev=tp.get("calls") if prev else None,
             prev_label=pl, unavailable=sched),
        dict(key="absence", value=tc.get("absence"), target=T["absence"], prev=tp.get("absence") if prev else None,
             prev_label=pl, unavailable=sched or ("" if cur.scored else "Per month only")),
        dict(key="answer_rate", value=oc.get("answer_rate"), prev=op.get("answer_rate") if prev else None, prev_label=pl),
        dict(key="customers", value=oc.get("customers"), prev=op.get("customers") if prev else None, prev_label=pl),
    ]
    for col, it in zip(rest, items[:3]):
        with col:
            C.kpi_card(**it)
    st.write("")
    C.kpi_grid(items[3:], cols=5)

    # ---------------------------------------------------------------- attention / positives
    items = ins.generate(ds, cur, prev or cur, f.agents) if prev else ins.generate(ds, cur, cur, f.agents)
    att = [i for i in items if i.severity in ("critical", "warning")]
    pos = [i for i in items if i.severity == "positive"]
    a, b = st.columns([1.6, 1], gap="medium")
    with a:
        C.section("What needs management attention", "Ranked by severity and size of the gap.")
        C.insight_cards(att, limit=5, empty="No KPI is below target for the current selection.")
    with b:
        C.section("Positive developments")
        C.insight_cards(pos, limit=4, empty="No significant improvement in this period.")

    # ---------------------------------------------------------------- trend and change
    C.section("Direction of travel", "Monthly team results; dashed line = target.")
    months = history_months(ds, cur.end, 12)
    hist = an.month_series(ds, months, f.agents)
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        if hist["score"].notna().any():
            st.plotly_chart(CH.trend_line(hist, "period", "score", "Team KPI score by month", T["score"]),
                            use_container_width=True, config={"displayModeBar": False})
        else:
            C.note("No month in range has a complete schedule, so the KPI score trend cannot be drawn.")
    with c2:
        if prev:
            tcmp = cmp.compare_team(ds, cur, prev, f.agents)
            show = tcmp[tcmp["key"].isin(["score", "quality", "chats", "calls", "reply", "absence", "fcr", "answer_rate",
                                          "adherence", "frt_median", "call_aht"])]
            st.plotly_chart(CH.change_bars(show, f"Change vs {pl} (green = better, red = worse)"),
                            use_container_width=True, config={"displayModeBar": False})
        else:
            st.plotly_chart(CH.trend_line(hist, "period", "reply", "First reply (min) by month", T["reply"]),
                            use_container_width=True, config={"displayModeBar": False})

    C.section("KPI summary", "Scorecard KPIs with the approved targets.")
    show_team_table(team_table(ds, f), pl or "Previous")

    # ---------------------------------------------------------------- logistics at a glance
    if L.has_data(ds):
        lt = L.targets()
        ls = L.scorecard(ds, cur) if cur.scored else {}
        lps = L.scorecard(ds, prev) if prev and prev.scored and cur.scored else {}
        tl, tlp = L.totals(ds, cur), (L.totals(ds, prev) if prev else {})
        lcov = L.coverage(ds, cur)
        C.section("Logistics at a glance", "Team scorecard of the bonus calculator (all markets). Details on the "
                  "Logistics pages." + (f" {lcov['maturity_note']}." if lcov.get("maturity_note") else ""))
        C.kpi_grid([
            dict(key="l_score", value=ls.get("l_score"), target=lt["l_score"], prev=lps.get("l_score") if lps else None,
                 prev_label=pl, unavailable="" if cur.scored else "Per month and quarter only"),
            dict(key="l_delivery", value=tl.get("l_delivery"), target=lt["l_delivery"],
                 prev=tlp.get("l_delivery") if prev else None, prev_label=pl),
            dict(key="l_ontime", value=tl.get("l_ontime"), target=lt["l_ontime"],
                 prev=tlp.get("l_ontime") if prev else None, prev_label=pl),
            dict(key="l_orders", value=tl.get("l_orders"), prev=tlp.get("l_orders") if prev else None, prev_label=pl),
        ], cols=4)
