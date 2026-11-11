"""Customer Support - Operations: chat and call demand, service levels, workforce metrics (CS Pulse definitions)."""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

import analytics as an
from kpis import ALL_KPIS, fmt
import charts as CH
import components as C
import theme as TH
from common import header


def page() -> None:
    ds, f = header("Customer Support", "Operations",
                   "Demand, service levels and workforce metrics. The market and topic filters on this page "
                   "apply to the volume views only; the scorecard is not affected by them.")
    cur, prev = f.period, f.compare
    pl = prev.short() if prev else ""
    o = an.ops(ds, cur, f.agents)
    op = an.ops(ds, prev, f.agents) if prev else {}
    tabs = st.tabs(["Service levels", "Chat demand", "Calls", "Workforce"])

    with tabs[0]:
        items = [dict(key=k, value=o.get(k), prev=op.get(k) if prev else None, prev_label=pl)
                 for k in ["conversations", "customers", "frt_median", "resolution_median", "inbound_calls", "answer_rate",
                           "call_aht", "call_wait"]]
        C.kpi_grid(items, cols=4)
        st.caption("No targets are defined for these operational metrics; colour shows direction of change only.")

    b = an.chat_breakdowns(ds, cur, f.agents)
    with tabs[1]:
        c = ds.chats
        m = c["include"] & (c["team"] == "CS") & (c["started"] >= cur.start) & (c["started"] < cur.end + pd.Timedelta(days=1))
        if f.agents:
            m &= c["agent"].isin(f.agents)
        sub = c[m]
        f1, f2 = st.columns(2)
        markets = f1.multiselect("Market", sorted([x for x in sub["market"].unique() if x]), key="ops_market",
                                 placeholder="All markets")
        topics = f2.multiselect("Topic", sorted([x for x in sub["topic"].unique() if x]), key="ops_topic",
                                placeholder="All topics")
        if markets:
            sub = sub[sub["market"].isin(markets)]
        if topics:
            sub = sub[sub["topic"].isin(topics)]
        daily = sub.groupby(sub["started"].dt.normalize()).agg(conversations=("id", "size")).reset_index()
        c1, c2 = st.columns([1.4, 1], gap="medium")
        with c1:
            st.plotly_chart(CH.volume_area(daily, "started", "conversations", "Conversations per day", "Conversations"),
                            use_container_width=True, config={"displayModeBar": False})
        with c2:
            hw = sub.assign(h=sub["started"].dt.hour, d=sub["started"].dt.dayofweek).pivot_table(
                index="d", columns="h", values="id", aggfunc="count").reindex(index=range(7), columns=range(24))
            hw.index = CH.DOW
            st.plotly_chart(CH.heat(hw.fillna(0), "Demand by weekday and hour"), use_container_width=True,
                            config={"displayModeBar": False})
        c1, c2 = st.columns(2, gap="medium")
        with c1:
            t = sub.groupby("topic").size().rename("conversations").sort_values(ascending=False).head(12).reset_index()
            st.plotly_chart(CH.simple_bars(t, "topic", "conversations", "Top topics", "Conversations", horizontal=True),
                            use_container_width=True, config={"displayModeBar": False})
        with c2:
            mk = sub.groupby("market").size().rename("conversations").sort_values(ascending=False).reset_index()
            st.plotly_chart(CH.simple_bars(mk, "market", "conversations", "Conversations by market", "Conversations",
                                           horizontal=True), use_container_width=True, config={"displayModeBar": False})
        fr = sub[sub["frt_sec"].notna()]
        if len(fr):
            g = fr.groupby("topic").agg(chats=("id", "size"), median_min=("frt_sec", lambda s: s.median() / 60),
                                        resolution_h=("resolution_sec", lambda s: s.median() / 3600)) \
                .sort_values("chats", ascending=False).head(15).reset_index()
            C.section("Speed by topic", "Median first reply and median resolution for the 15 largest topics.")
            st.dataframe(g, hide_index=True, use_container_width=True, column_config={
                "topic": "Topic", "chats": st.column_config.NumberColumn("Chats", format="%d"),
                "median_min": st.column_config.NumberColumn("First reply (median, min)", format="%.1f"),
                "resolution_h": st.column_config.NumberColumn("Resolution (median, h)", format="%.1f")})

    with tabs[2]:
        k = b["calls_daily"]
        c1, c2 = st.columns([1.4, 1], gap="medium")
        with c1:
            st.plotly_chart(CH.volume_area(k, "date", "inbound", "Inbound calls per day", "Inbound calls"),
                            use_container_width=True, config={"displayModeBar": False})
        with c2:
            st.plotly_chart(CH.simple_bars(b["calls_hour"], "hour", "calls", "Inbound calls by hour", "Calls"),
                            use_container_width=True, config={"displayModeBar": False})
        if not b["sentiment"].empty:
            s = b["sentiment"].sort_values("calls", ascending=False)
            st.plotly_chart(CH.simple_bars(s, "sentiment", "calls", "Answered calls by sentiment", "Calls", horizontal=True),
                            use_container_width=True, config={"displayModeBar": False})

    with tabs[3]:
        items = [dict(key=k, value=o.get(k), prev=op.get(k) if prev else None, prev_label=pl)
                 for k in ["adherence", "occupancy", "shrinkage"]]
        C.kpi_grid(items, cols=3)
        if not an.coverage(ds, cur).get("schedule_ok", True):
            C.note(f"Workforce metrics cover only the scheduled days (schedule entered up to "
                   f"{ds.coverage['schedule_to']:%d %b %Y}).")
        agents = f.agents or ds.kpi_agents
        oa = an.ops_by_agent(ds, cur, agents)
        disp = oa[["agent", "adherence", "occupancy", "shrinkage", "frt_median", "conversations", "answer_rate", "call_aht"]].copy()
        for kk in ["adherence", "occupancy", "shrinkage", "answer_rate"]:
            disp[kk] = disp[kk] * 100
        cfg = {"agent": "Agent"}
        for kk in disp.columns[1:]:
            cfg[kk] = C.kpi_value_col(kk)
        C.section("By agent")
        st.dataframe(disp, hide_index=True, use_container_width=True, column_config=cfg)
