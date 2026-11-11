"""Customer Support - Period Comparison (any two periods: month, quarter, year, week or custom ranges)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

import analytics as an
import comparison as cmp
import insights as ins
from kpis import ALL_KPIS, fmt, fmt_delta, is_missing
import charts as CH
import components as C
from common import header


def page() -> None:
    ds, f = header("Customer Support", "Period Comparison",
                   "Choose the two periods with 'Period' and 'Compare with' in the sidebar (previous period, same period "
                   "last year, any chosen period or custom date ranges).")
    cur, prev = f.period, f.compare
    if prev is None:
        C.note("Select a comparison in the sidebar ('Compare with') to use this page.")
        return
    for w in cmp.warnings(ds, cur, prev):
        st.warning(w, icon="⚠️")
    st.caption("Improvement is judged by each KPI's direction (e.g. lower first reply or absence is better). Changes "
               "under 2% are shown as stable. Volume metrics are workload, not performance, so they are not rated.")

    tcmp = cmp.compare_team(ds, cur, prev, f.agents)
    rated = tcmp[tcmp["trend"].isin(["improved", "declined", "stable"])]
    n_up, n_dn, n_st = (rated["trend"] == "improved").sum(), (rated["trend"] == "declined").sum(), (rated["trend"] == "stable").sum()
    c = st.columns(4, gap="small")
    for col, (lab, val, colr) in zip(c, [("Periods", f"{cur.short()} vs {prev.short()}", None),
                                         ("KPIs improved", n_up, "#0B7A0B"), ("KPIs declined", n_dn, "#A12B2B"),
                                         ("Stable", n_st, None)]):
        with col:
            st.markdown(f'<div class="gc-card"><div class="gc-kpi-label"><span>{lab}</span></div>'
                        f'<div class="gc-kpi-value" style="font-size:{"1.05rem" if lab == "Periods" else "1.75rem"};'
                        f'{f"color:{colr}" if colr else ""}">{val}</div></div>', unsafe_allow_html=True)

    st.plotly_chart(CH.change_bars(tcmp[tcmp["direction"] != "neutral"], "Change by KPI (direction-aware)"),
                    use_container_width=True, config={"displayModeBar": False})
    if True:
        C.section("KPI by KPI")
        d = pd.DataFrame({
            "KPI": tcmp["KPI"], cur.short(): [fmt(k, v) for k, v in zip(tcmp["key"], tcmp["current"])],
            prev.short(): [fmt(k, v) for k, v in zip(tcmp["key"], tcmp["previous"])],
            "Change": [fmt_delta(k, v) for k, v in zip(tcmp["key"], tcmp["change"])],
            "% change": [f"{v * 100:+.1f}%" if not is_missing(v) else "—" for v in tcmp["change_pct"]],
            "Target": [fmt(k, v) for k, v in zip(tcmp["key"], tcmp["target"])],
            f"Status {cur.short()}": [C.met_text(m) if m is not None else "" for m in tcmp["met_current"]],
            f"Status {prev.short()}": [C.met_text(m) if m is not None else "" for m in tcmp["met_previous"]],
            "Trend": [C.trend_text(t) for t in tcmp["trend"]]})
        st.dataframe(C.style_status(d, ["Trend", f"Status {cur.short()}", f"Status {prev.short()}"]),
                     hide_index=True, use_container_width=True, height=min(640, 40 + 35 * len(d)))

    # ---------------------------------------------------------------- groups
    C.section("Group changes")
    gc = cmp.compare_groups(ds, cur, prev)
    if not gc.empty:
        piv = gc.assign(txt=[f"{fmt(k, c_)} ({fmt_delta(k, ch)})" if not is_missing(ch) else fmt(k, c_)
                             for k, c_, ch in zip(gc["key"], gc["current"], gc["change"])],
                        trend_txt=[C.trend_text(t) for t in gc["trend"]])
        order = list(dict.fromkeys(gc["KPI"]))
        tbl = piv.pivot_table(index="KPI", columns="group", values="txt", aggfunc="first").reindex(order).reset_index()
        st.dataframe(tbl, hide_index=True, use_container_width=True)

    # ---------------------------------------------------------------- agents
    C.section("Agent changes", "Rank changes are shown only when both periods have a valid score and the agent's data "
              "is comparable in both.")
    ac = cmp.compare_agents(ds, cur, prev, f.agents)
    if ac.empty:
        C.note("No agent data for the selected period.")
        return
    keys = [k for k in cmp.kpi_keys_for(cur, prev, team_level=False) if f"{k}_cur" in ac]
    k = st.selectbox("KPI", keys, format_func=lambda x: ALL_KPIS[x].label, key="cmp_agent_kpi")
    c1, c2 = st.columns([1.1, 1], gap="medium")
    with c1:
        st.plotly_chart(CH.two_period_bars(ac.sort_values(f"{k}_cur", ascending=ALL_KPIS[k].direction == "lower"),
                                           "agent", f"{k}_cur", f"{k}_prev", k, cur.short(), prev.short(),
                                           f"{ALL_KPIS[k].label} by agent"),
                        use_container_width=True, config={"displayModeBar": False})
    with c2:
        t = pd.DataFrame({"Agent": ac["agent"],
                          cur.short(): [fmt(k, v) for v in ac[f"{k}_cur"]],
                          prev.short(): [fmt(k, v) for v in ac[f"{k}_prev"]],
                          "Change": [fmt_delta(k, v) for v in ac[f"{k}_chg"]],
                          "Trend": [C.trend_text(x) for x in ac[f"{k}_trend"]]})
        if "rank_chg" in ac:
            ok = ac["comparable_now"] & ac["comparable_before"]
            t["Rank now"] = [f"{int(x)}" if (o and not is_missing(x)) else "—" for x, o in zip(ac["rank_cur"], ok)]
            t["Rank before"] = [f"{int(x)}" if (o and not is_missing(x)) else "—" for x, o in zip(ac["rank_prev"], ok)]
            t["Rank change"] = [(f"▲ {int(x)}" if x > 0 else (f"▼ {int(-x)}" if x < 0 else "■ 0")) if (o and not is_missing(x))
                                else "—" for x, o in zip(ac["rank_chg"], ok)]
        st.dataframe(C.style_status(t, ["Trend"]), hide_index=True, use_container_width=True,
                     height=min(520, 40 + 35 * len(t)))

    C.section("What changed and why it matters")
    items = ins.generate(ds, cur, prev, f.agents)
    C.insight_cards([i for i in items if i.area in ("KPI", "Operations", "Agent", "Team")], limit=8)
