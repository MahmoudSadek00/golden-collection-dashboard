"""Customer Support - Level 2: team / group performance (shift groups per the scorecard night-shift rule)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import analytics as an
import comparison as cmp
from kpis import ALL_KPIS, achievement, fmt, fmt_delta, is_missing, target_met
import charts as CH
import components as C
import theme as TH
from common import header, history_months


def page() -> None:
    ds, f = header("Customer Support", "Teams & Groups",
                   "Day-shift and night-shift groups compared on the same team formulas. A night-shift agent works at "
                   "least half of their days on the 12 AM – 9 AM shift.")
    cur, prev = f.period, f.compare
    T = cmp.targets(ds)
    groups = an.agent_groups(ds, cur)
    if not groups:
        C.note("No agent has a working day in this period.")
        return
    keys = cmp.kpi_keys_for(cur, prev or cur)
    cov = an.coverage(ds, cur)
    if not cov.get("schedule_ok", True):
        keys = [k for k in keys if k not in an.SCHEDULE_KPIS]
        C.note(cov["schedule_note"] + ". Groups are based on the days that were scheduled.")

    # ---------------------------------------------------------------- group cards
    gnames = sorted(groups)
    cols = st.columns(len(gnames) + 1, gap="medium")
    team_all = an.team(ds, cur)
    for col, g in zip(cols, ["All agents"] + gnames):
        with col:
            t = team_all if g == "All agents" else an.team(ds, cur, groups[g])
            n = t.get("agents", 0)
            met = [k for k in keys if k in T and target_met(k, t.get(k), T[k])]
            miss = [k for k in keys if k in T and target_met(k, t.get(k), T[k]) is False]
            ach = {k: achievement(k, t.get(k), T[k]) for k in keys if k in T and not is_missing(t.get(k)) and k != "score"}
            best = max(ach, key=ach.get) if ach else None
            worst = min(ach, key=ach.get) if ach else None
            sc = t.get("score")
            st.markdown(f"""<div class="gc-card"><div class="gc-kpi-label"><span>{C.esc(g)}</span>
                <span style="color:{TH.MUTED}">{n} agents</span></div>
                <div class="gc-kpi-value">{fmt('score', sc) if not is_missing(sc) else '—'}<small>{' score' if not is_missing(sc) else ''}</small></div>
                <div class="gc-kpi-row"><span>On target <b>{len(met)}</b></span><span>Below <b>{len(miss)}</b></span></div>
                <div class="gc-kpi-row"><span>Strongest <b>{ALL_KPIS[best].label if best else '—'}</b></span></div>
                <div class="gc-kpi-row"><span>Weakest <b>{ALL_KPIS[worst].label if worst else '—'}</b></span></div>
                </div>""", unsafe_allow_html=True)

    # ---------------------------------------------------------------- KPI x group table
    C.section("KPI breakdown by group", "Same formulas as the team result, applied to each group's agents.")
    rows = []
    for k in keys:
        rec = {"KPI": ALL_KPIS[k].label, "Target": fmt(k, T.get(k))}
        for g in ["All agents"] + gnames:
            t = team_all if g == "All agents" else an.team(ds, cur, groups[g])
            v = t.get(k)
            m = target_met(k, v, T.get(k))
            rec[g] = fmt(k, v) + ("" if m is None else (" ●" if m else " ▲"))
        rows.append(rec)
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
    st.caption("● on target · ▲ below target")

    # ---------------------------------------------------------------- change vs previous
    if prev:
        C.section(f"Change vs {prev.short()}")
        gc = cmp.compare_groups(ds, cur, prev)
        gc = gc[gc["key"].isin(keys)]
        k = st.selectbox("KPI", keys, format_func=lambda x: ALL_KPIS[x].label, key="grp_kpi")
        sub = gc[gc["key"] == k]
        c1, c2 = st.columns([1, 1], gap="medium")
        with c1:
            st.plotly_chart(CH.two_period_bars(sub, "group", "current", "previous", k, cur.short(), prev.short(),
                                               f"{ALL_KPIS[k].label}: {cur.short()} vs {prev.short()}"),
                            use_container_width=True, config={"displayModeBar": False})
        with c2:
            months = history_months(ds, cur.end, 9)
            fig = go.Figure()
            for i, g in enumerate(gnames):
                vals = []
                for m in months:
                    gm = an.agent_groups(ds, m).get(g)
                    vals.append(an.team(ds, m, gm).get(k, np.nan) if gm else np.nan)
                s = 100 if ALL_KPIS[k].unit in ("pct", "ratio") else 1
                fig.add_trace(go.Scatter(x=[m.label for m in months], y=[v * s if not is_missing(v) else None for v in vals],
                                         name=g, mode="lines+markers", line=dict(color=TH.SERIES[i], width=2.2),
                                         marker=dict(size=8, line=dict(color="#fff", width=2))))
            if k in T:
                fig.add_hline(y=T[k] * (100 if ALL_KPIS[k].unit in ("pct", "ratio") else 1),
                              line=dict(color=TH.TARGET, width=1.2, dash="dash"))
            st.plotly_chart(CH.base(fig, f"{ALL_KPIS[k].label} by month and group", 340, legend=True),
                            use_container_width=True, config={"displayModeBar": False})

    # ---------------------------------------------------------------- contribution (volumes only: additive)
    C.section("Contribution to team volume", "Share of the team's closed customers, inbound calls and delivered "
              "sales by group. Volumes reflect workload and working days, not performance.")
    A = an.scorecard(ds, cur)
    vol = A.groupby("group")[["working_days", "chats_closed", "inbound_calls", "sales_usd"]].sum()
    tot = vol.sum()
    share = (vol / tot.replace(0, np.nan)).reset_index()
    disp = pd.DataFrame({"Group": share["group"],
                         "Working days": vol["working_days"].values, "Share of working days": share["working_days"] * 100,
                         "Customers closed": vol["chats_closed"].values, "Share of customers closed": share["chats_closed"] * 100,
                         "Inbound calls": vol["inbound_calls"].values, "Share of calls": share["inbound_calls"] * 100,
                         "Delivered sales (USD)": vol["sales_usd"].values, "Share of sales": share["sales_usd"] * 100})
    pc = st.column_config.ProgressColumn
    st.dataframe(disp, hide_index=True, use_container_width=True, column_config={
        "Working days": st.column_config.NumberColumn(format="%d"),
        "Customers closed": st.column_config.NumberColumn(format="%d"),
        "Inbound calls": st.column_config.NumberColumn(format="%d"),
        "Delivered sales (USD)": st.column_config.NumberColumn(format="$%.0f"),
        "Share of working days": pc(min_value=0, max_value=100, format="%.0f%%"),
        "Share of customers closed": pc(min_value=0, max_value=100, format="%.0f%%"),
        "Share of calls": pc(min_value=0, max_value=100, format="%.0f%%"),
        "Share of sales": pc(min_value=0, max_value=100, format="%.0f%%")})
    if not an.coverage(ds, cur).get("schedule_ok", True):
        st.caption("Working days cover only the scheduled days of this period.")
