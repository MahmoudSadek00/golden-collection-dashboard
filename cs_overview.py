"""Customer Support - Level 1: overall performance, agent scorecard, KPI breakdown and trends."""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

import analytics as an
import comparison as cmp
import insights as ins
import periods as P
from kpis import ALL_KPIS, SCORE_KPIS, is_missing
import charts as CH
import components as C
from common import header, history_months, show_team_table, team_table


def scorecard_table(A: pd.DataFrame, scored: bool) -> None:
    if A.empty:
        C.note("No agent has a working day in this period.")
        return
    d = A.copy()
    d["Notes"] = [", ".join(x for x, f in (("Limited working days", l), ("QA not entered", q)) if f)
                  for l, q in zip(d["limited_data"], d["qa_missing"])]
    d["Targets"] = [f"{int(h)} / {int(c)}" if not (is_missing(h) or is_missing(c)) else "—"
                    for h, c in zip(d["targets_hit"], d["targets_counted"])]
    cols = ["agent", "group", "working_days"] + (["score", "rank"] if scored else []) + \
           (["quality"] if scored else []) + ["chats", "calls", "sales", "reply"] + (["absence"] if scored else []) + \
           ["fcr", "Targets", "Notes"]
    d = C.pct_for_display(d, ["quality", "sales", "fcr"])
    d = d[cols].sort_values("score" if scored and d["score"].notna().any() else "agent",
                            ascending=not (scored and d["score"].notna().any()))
    cfg = {"agent": st.column_config.TextColumn("Agent", width="medium"), "group": "Group",
           "working_days": st.column_config.NumberColumn("Working days", format="%d"),
           "score": st.column_config.ProgressColumn("KPI score", min_value=0, max_value=100, format="%.1f"),
           "rank": st.column_config.NumberColumn("Rank", format="%d", help="Approved scorecard rank (all KPI agents)."),
           "Targets": st.column_config.TextColumn("Targets hit", help="KPI targets met / KPI targets counted.")}
    for k in ["quality", "chats", "calls", "sales", "reply", "absence", "fcr"]:
        cfg[k] = C.kpi_value_col(k)
    st.dataframe(d, hide_index=True, use_container_width=True, column_config=cfg, height=min(520, 40 + 35 * len(d)))


def page() -> None:
    ds, f = header("Customer Support", "Performance Overview",
                   "Team results on the approved scorecard, agent scorecard and KPI trends.")
    cur, prev = f.period, f.compare
    T = cmp.targets(ds)
    tc = an.team(ds, cur, f.agents)
    tp = an.team(ds, prev, f.agents) if prev else {}
    pl = prev.short() if prev else ""
    cov = an.coverage(ds, cur)
    sched = "" if cov.get("schedule_ok", True) else "Schedule not entered for this period"

    items = []
    for k in ["score", "quality", "chats", "calls", "reply", "absence", "fcr"]:
        un = ""
        if k in an.SCHEDULE_KPIS and sched:
            un = sched
        if SCORE_KPIS[k].monthly_only and not cur.scored:
            un = "Defined per month / quarter"
        if k == "score" and not cur.scored:
            un = "Defined per month / quarter"
        items.append(dict(key=k, value=tc.get(k), target=T.get(k), prev=tp.get(k) if prev else None, prev_label=pl,
                          unavailable=un, note_txt="Monitor only" if k == "fcr" else ""))
    oc = an.ops(ds, cur, f.agents)
    items.append(dict(key="frt_median", value=oc.get("frt_median"), prev=an.ops(ds, prev, f.agents).get("frt_median") if prev else None,
                      prev_label=pl))
    C.kpi_grid(items, cols=4)

    tab1, tab2, tab3, tab4 = st.tabs(["Agent scorecard", "KPI breakdown", "Trends", "Findings"])
    A = an.scorecard(ds, cur)
    if f.agents and not A.empty:
        A = A[A["agent"].isin(f.agents)]
    with tab1:
        C.section("Agent scorecard", "Rank is the approved scorecard rank across all KPI agents. Agents with limited "
                  "working days or without QA are flagged and should not be compared directly.")
        scorecard_table(A, cur.scored and cov.get("schedule_ok", True))
        C.section("KPI summary")
        show_team_table(team_table(ds, f), pl or "Previous")
    with tab2:
        keys = [k for k in ["chats", "calls", "reply", "fcr", "sales", "quality", "absence", "score"]
                if not (k in an.SCHEDULE_KPIS and sched) and not ((SCORE_KPIS[k].monthly_only or k == "score") and not cur.scored)]
        k = st.selectbox("KPI", keys, format_func=lambda x: ALL_KPIS[x].label, key="cs_kpi_breakdown")
        c1, c2 = st.columns([1.2, 1], gap="medium")
        with c1:
            if not A.empty and k in A:
                st.plotly_chart(CH.actual_vs_target_bars(A, "agent", k, f"{ALL_KPIS[k].label} by agent",
                                                         T.get(k) if k != "sales" else T.get("sales"),
                                                         tc.get(k) if k != "sales" else None),
                                use_container_width=True, config={"displayModeBar": False})
        with c2:
            months = history_months(ds, cur.end, 12)
            hist = an.month_series(ds, months, f.agents)
            if k in hist and hist[k].notna().any():
                st.plotly_chart(CH.trend_line(hist, "period", k, f"Team {ALL_KPIS[k].label} by month", T.get(k)),
                                use_container_width=True, config={"displayModeBar": False})
            else:
                C.note("Team-level trend is not defined for this KPI (sales contribution is 100% at team level).")
        st.caption(ALL_KPIS[k].definition)
    with tab3:
        C.section("Weekly trend", "Last 12 weeks to the end of the selected period. Weeks without a schedule show no "
                  "per-day KPIs.")
        f_from, f_to = an.data_range(ds)
        wks = [w for w in P.available("Week", f_from, f_to) if w.end <= cur.end + pd.Timedelta(days=6)][:12]
        rows = []
        for w in reversed(wks):
            t = an.team(ds, w, f.agents)
            o = an.ops(ds, w, f.agents)
            rows.append({"period": w.start.strftime("%d %b"), "reply": t.get("reply"), "fcr": t.get("fcr"),
                         "chats": t.get("chats"), "calls": t.get("calls"), "frt_median": o.get("frt_median"),
                         "answer_rate": o.get("answer_rate")})
        W = pd.DataFrame(rows)
        c1, c2 = st.columns(2, gap="medium")
        with c1:
            st.plotly_chart(CH.trend_line(W, "period", "reply", "First reply (min), weekly", T["reply"]),
                            use_container_width=True, config={"displayModeBar": False})
            st.plotly_chart(CH.trend_line(W, "period", "chats", "Chats per day, weekly", T["chats"]),
                            use_container_width=True, config={"displayModeBar": False})
        with c2:
            st.plotly_chart(CH.trend_line(W, "period", "fcr", "FCR, weekly", T["fcr"]),
                            use_container_width=True, config={"displayModeBar": False})
            st.plotly_chart(CH.trend_line(W, "period", "answer_rate", "Call answer rate, weekly"),
                            use_container_width=True, config={"displayModeBar": False})
    with tab4:
        items = ins.generate(ds, cur, prev or cur, f.agents)
        C.insight_cards([i for i in items if i.area in ("KPI", "Team", "Data")])
