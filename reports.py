"""Reports & Exports: Excel management report for Customer Support, Logistics or both, from the current filters."""
from __future__ import annotations

import re

import streamlit as st

from excel_report import LOGI_SECTIONS, SECTIONS, build
import components as C
import logi as L
from common import header

TEAMS = ["Customer Support", "Logistics", "Both teams"]
PRESETS = {
    "Full management report": SECTIONS,
    "Executive summary": ["Executive Summary", "KPI Performance", "Insights & Actions"],
    "Period comparison": ["Executive Summary", "Period Comparison", "Insights & Actions"],
    "Team & agent review": ["KPI Performance", "Team Performance", "Individual Performance", "Detailed Data"],
}
LOGI_PRESETS = {
    "Full logistics report": LOGI_SECTIONS,
    "Summary only": ["Logistics Summary", "Logistics Insights"],
    "Markets review": ["Logistics Summary", "Logistics Markets"],
}


def page() -> None:
    ds, f = header("Reports & Exports", "Report Builder",
                   "Excel report for the current sidebar selection. It uses exactly the same figures and findings as "
                   "the dashboard.")
    c1, c2 = st.columns([1, 1.3], gap="large")
    sections, logi_sections, agent = [], [], None
    with c1:
        team = st.radio("Team", TEAMS, key="rep_team", horizontal=True)
        if team in ("Customer Support", "Both teams"):
            C.section("Customer Support sheets")
            preset = st.radio("Report type", list(PRESETS), key="rep_preset")
            sections = st.multiselect("Sheets", SECTIONS, default=PRESETS[preset], key=f"rep_sections_{preset}")
            if f.compare is None and "Period Comparison" in sections:
                st.caption("Period Comparison is skipped: no comparison period is selected.")
            if "Individual Performance" in sections:
                pool = f.agents or ds.kpi_agents
                sel = st.selectbox("Add an agent detail block (optional)", ["None"] + list(pool), key="rep_agent")
                agent = None if sel == "None" else sel
        if team in ("Logistics", "Both teams"):
            C.section("Logistics sheets")
            if not L.has_data(ds):
                st.warning("Logistics data is not available (see Data Health).")
            lp = st.radio("Logistics report type", list(LOGI_PRESETS), key="rep_lpreset")
            logi_sections = st.multiselect("Logistics sheets", LOGI_SECTIONS, default=LOGI_PRESETS[lp],
                                           key=f"rep_lsections_{lp}")
            st.caption("Logistics sheets cover all markets; the score follows the bonus calculator (months and quarters).")
    with c2:
        C.section("Report scope")
        scope = dict(f.as_dict())
        scope["Team"] = team
        if team == "Logistics":
            scope = {k: v for k, v in scope.items() if k not in ("Group", "Agents")}
        for k, v in scope.items():
            st.markdown(f"- **{k}:** {v}")
        st.caption("Change the period and comparison in the sidebar; the report follows them."
                   + (" Group and agent filters apply to the Customer Support sheets." if team != "Logistics" else ""))
        empty = not sections and not logi_sections
        sig = repr((f.as_dict(), team, sections, logi_sections, agent))
        if st.session_state.get("rep_sig") != sig:
            st.session_state.pop("rep_bytes", None)
        if st.button("Prepare report", type="primary", use_container_width=True, disabled=empty):
            st.session_state["rep_sig"] = sig
            with st.spinner("Preparing the report…"):
                st.session_state["rep_bytes"] = build(ds, f, sections, agent, logi_sections)
                tag = {"Customer Support": "CS", "Logistics": "Logistics", "Both teams": "CS_Logistics"}[team]
                st.session_state["rep_name"] = re.sub(r"[^A-Za-z0-9_-]+", "_",
                                                      f"GC_{tag}_Performance_{f.period.short()}") + ".xlsx"
        if empty:
            st.caption("Choose at least one sheet.")
        if st.session_state.get("rep_bytes"):
            st.download_button("Download Excel report", st.session_state["rep_bytes"], st.session_state["rep_name"],
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               use_container_width=True)
            st.caption("The download matches the scope shown above.")
