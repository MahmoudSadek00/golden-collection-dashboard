"""Reports & Exports: Excel management report generated from the current filters."""
from __future__ import annotations

import re

import streamlit as st

from excel_report import SECTIONS, build
import components as C
from common import header

PRESETS = {
    "Full management report": SECTIONS,
    "Executive summary": ["Executive Summary", "KPI Performance", "Insights & Actions"],
    "Period comparison": ["Executive Summary", "Period Comparison", "Insights & Actions"],
    "Team & agent review": ["KPI Performance", "Team Performance", "Individual Performance", "Detailed Data"],
}


def page() -> None:
    ds, f = header("Reports & Exports", "Report Builder",
                   "Excel report for the current sidebar selection. It uses exactly the same figures and findings as "
                   "the dashboard.")
    c1, c2 = st.columns([1, 1.3], gap="large")
    with c1:
        preset = st.radio("Report type", list(PRESETS), key="rep_preset")
        sections = st.multiselect("Sheets", SECTIONS, default=PRESETS[preset], key=f"rep_sections_{preset}")
        if f.compare is None and "Period Comparison" in sections:
            st.caption("Period Comparison is skipped: no comparison period is selected.")
        agent = None
        if "Individual Performance" in sections:
            pool = f.agents or ds.kpi_agents
            sel = st.selectbox("Add an agent detail block (optional)", ["None"] + list(pool), key="rep_agent")
            agent = None if sel == "None" else sel
    with c2:
        C.section("Report scope")
        for k, v in f.as_dict().items():
            st.markdown(f"- **{k}:** {v}")
        st.caption("Change the period, comparison, group or agents in the sidebar; the report follows them.")
        sig = repr((f.as_dict(), sections, agent))
        if st.session_state.get("rep_sig") != sig:
            st.session_state.pop("rep_bytes", None)
        if st.button("Prepare report", type="primary", use_container_width=True):
            st.session_state["rep_sig"] = sig
            with st.spinner("Preparing the report…"):
                st.session_state["rep_bytes"] = build(ds, f, sections, agent)
                st.session_state["rep_name"] = re.sub(r"[^A-Za-z0-9_-]+", "_",
                                                      f"GC_CS_Performance_{f.period.short()}") + ".xlsx"
        if st.session_state.get("rep_bytes"):
            st.download_button("Download Excel report", st.session_state["rep_bytes"], st.session_state["rep_name"],
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True)
            st.caption("The download matches the scope shown above.")
