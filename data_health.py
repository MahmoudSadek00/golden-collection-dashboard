"""Data Health: source coverage, data issues and reconciliation with the sheet's own scorecard."""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

import analytics as an
import periods as P
from kpi_engine import compute
from state import ctx, refresh
import components as C

RECON = {"Working Days": "working_days", "Chats Closed (unique customers)": "chats_closed", "Inbound Calls": "inbound_calls",
         "FCR Chats Checked": "fcr_checked", "Absent Days (sick + casual)": "absent_days", "Delivered Sales USD": "sales_usd",
         "Quality %": "quality", "FCR %": "fcr", "Chats per Day": "chats", "Calls per Day": "calls",
         "Sales Contribution": "sales", "First Reply (min)": "reply", "Absence (days/month)": "absence", "KPI Score": "score"}


def _d(x):
    return "—" if pd.isna(x) else f"{x:%d %b %Y}"


def page() -> None:
    ds, f = ctx()
    C.page_header("Reports & Exports", "Data Health",
                  "Where the numbers come from, how current they are, and checks that the dashboard reproduces the "
                  "sheet's scorecard exactly.", f"Source: {C.esc(ds.source)}<br>Refreshed {ds.loaded_at}")
    if st.button("Refresh data now"):
        refresh()
        st.rerun()

    cv = ds.coverage
    rows = [("CS_Chats", "Chats (first reply, FCR, customers closed)", _d(cv["chats_from"]), _d(cv["chats_to"]), f"{len(ds.chats):,}"),
            ("CS_Agent_Daily", "Schedule, working days, adherence", _d(cv["daily_from"]), _d(cv["schedule_to"]), f"{len(ds.daily):,}"),
            ("CS_Calls", "Inbound calls", _d(cv["calls_from"]), _d(cv["calls_to"]), f"{len(ds.calls):,}"),
            ("Agent_Orders", "Delivered sales by agent", _d(cv["orders_from"]), _d(cv["orders_to"]), f"{len(ds.orders):,}"),
            ("Logistics_Daily", "Orders, shipping and delivery by day and market (Orders sheet)", _d(cv.get("logi_from")),
             _d(cv.get("logi_to")), f"{len(ds.logi):,}"),
            ("QA_Input", "Monthly quality scores", (cv["qa_months"] or ["—"])[0], (cv["qa_months"] or ["—"])[-1],
             f"{len(ds.qa):,}")]
    C.section("Source coverage")
    st.dataframe(pd.DataFrame(rows, columns=["Tab", "Used for", "From", "To", "Rows"]), hide_index=True,
                 use_container_width=True)

    C.section("Data issues")
    if ds.issues:
        for i in ds.issues:
            (st.error if i.level == "critical" else st.warning if i.level == "warning" else st.info)(f"**{i.area}** — {i.message}")
    else:
        st.success("No data issues detected.")
    f_from, f_to = an.data_range(ds)
    miss_qa = [p.label for p in P.available("Month", f_from, f_to) if p.label not in cv["qa_months"] and an.coverage(ds, p)["complete"]]
    if miss_qa:
        st.warning(f"**QA_Input** — no QA scores for complete month(s): {', '.join(miss_qa)}. Quality earns 0 points there.")

    C.section("Reconciliation with LS_Scorecard", "The dashboard engine recalculates every agent and period in "
              "LS_Scorecard and compares the results value by value.")
    ls = ds.ls_scorecard
    if ls is None or ls.empty:
        C.note("LS_Scorecard was not found, so the reconciliation cannot run.")
    else:
        n = bad = 0
        examples = []
        for (pt, p, s, e), g in ls.groupby(["Period Type", "Period", "Period Start", "Period End"]):
            r = compute(ds, s, e).agents
            r = r.set_index("agent") if not r.empty else r
            for _, row in g.iterrows():
                a = str(row["Agent"]).strip()
                for col, k in RECON.items():
                    if col not in row:
                        continue
                    n += 1
                    x = pd.to_numeric(str(row[col]).strip() or np.nan, errors="coerce")
                    y = r.at[a, k] if (not r.empty and a in r.index) else np.nan
                    if (pd.isna(x) and pd.isna(y)) or (not pd.isna(x) and not pd.isna(y) and abs(x - y) <= 1e-6 * max(1, abs(x))):
                        continue
                    bad += 1
                    if len(examples) < 10:
                        examples.append((p, a, col, x, y))
        if bad == 0:
            st.success(f"All {n:,} values match LS_Scorecard exactly.")
        else:
            st.error(f"{bad:,} of {n:,} values differ from LS_Scorecard. LS_Scorecard may not have been rebuilt since "
                     "the last data refresh.")
            st.dataframe(pd.DataFrame(examples, columns=["Period", "Agent", "Column", "LS_Scorecard", "Dashboard"]),
                         hide_index=True, use_container_width=True)
    C.section("Calculation rules in use")
    w = ds.cfg["weights"]
    st.dataframe(pd.DataFrame([{"KPI": k, "Points": v["ptsNoFcr"], "Target": v["target"],
                                "Better when": "Higher" if v["higher"] else "Lower"} for k, v in w.items()] +
                              [{"KPI": "Team score target", "Points": None, "Target": ds.cfg["teamTarget"], "Better when": "Higher"}]),
                 hide_index=True, use_container_width=True)
    st.caption("Targets and points are read from KPI_Targets. Agents in the score are read from KPI_Agents.")
