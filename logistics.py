"""Logistics section: architecture in place, no figures until the approved daily data is connected."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from schema import PLANNED_FEATURES, PROPOSED_DAILY_COLUMNS
import components as C


def page() -> None:
    C.page_header("Logistics", "Logistics Performance",
                  "Orders, delivery and courier performance across markets.")
    grid = "".join(f"<div><b>{C.esc(t)}</b>{C.esc(d)}</div>" for t, d in PLANNED_FEATURES)
    st.markdown(f"""<div class="gc-soon">
        <span class="gc-pill" style="background:#FFF6E0;color:#8A5A00">◇ Coming soon</span>
        <h3 style="margin-top:.6rem">Logistics data is being prepared</h3>
        <p style="color:#475569;font-size:.9rem;max-width:760px">This section will be activated once the daily
        Logistics summary is available and its KPI definitions are approved. No logistics figures are shown until then.</p>
        <div class="gc-grid">{grid}</div></div>""", unsafe_allow_html=True)
    C.section("Proposed daily data structure", "One row per day × market × courier, the same approach as the "
              "Customer Support daily agent summary. To be confirmed with the Logistics data owner.")
    st.dataframe(pd.DataFrame(PROPOSED_DAILY_COLUMNS, columns=["Column", "Content"]), hide_index=True,
                 use_container_width=True)
