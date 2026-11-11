"""Golden Collection Dashboard - entry point (Streamlit multipage via st.navigation)."""
from __future__ import annotations

import streamlit as st

from config import APP_NAME
import theme

st.set_page_config(page_title=APP_NAME, page_icon="◆", layout="wide", initial_sidebar_state="expanded")
theme.inject_css()

from state import get_dataset  # noqa: E402  (after page config)
import filters  # noqa: E402
import cs_agent, cs_comparison, cs_groups, cs_operations, cs_overview, data_health, executive, logistics, reports  # noqa: E402


def main() -> None:
    st.sidebar.markdown(
        f"""<div style="padding:.2rem 0 .8rem 0;border-bottom:1px solid rgba(255,255,255,.12);margin-bottom:.4rem">
        <div style="font-size:1.05rem;font-weight:700;color:#fff;letter-spacing:.01em">◆ Golden Collection</div>
        <div style="font-size:.72rem;color:#8C9AB8;letter-spacing:.06em;text-transform:uppercase">Operations Intelligence</div>
        </div>""", unsafe_allow_html=True)
    ds = get_dataset()
    if ds is None:
        return
    nav_slot = st.sidebar.container()
    f = filters.sidebar(ds)
    st.session_state["_ctx"] = (ds, f)

    pages = {
        "Overview": [st.Page(executive.page, title="Executive Overview", icon=":material/dashboard:", url_path="overview",
                             default=True)],
        "Customer Support": [
            st.Page(cs_overview.page, title="Performance", icon=":material/monitoring:", url_path="cs-performance"),
            st.Page(cs_groups.page, title="Teams & Groups", icon=":material/groups:", url_path="cs-groups"),
            st.Page(cs_agent.page, title="Agent Profile", icon=":material/person:", url_path="cs-agent"),
            st.Page(cs_comparison.page, title="Period Comparison", icon=":material/compare_arrows:", url_path="cs-compare"),
            st.Page(cs_operations.page, title="Operations", icon=":material/support_agent:", url_path="cs-operations"),
        ],
        "Logistics": [
            st.Page(logistics.performance, title="Performance", icon=":material/local_shipping:", url_path="logistics"),
            st.Page(logistics.markets, title="Markets", icon=":material/public:", url_path="logistics-markets"),
            st.Page(logistics.trends, title="Trends", icon=":material/timeline:", url_path="logistics-trends"),
        ],
        "Reports & Exports": [
            st.Page(reports.page, title="Report Builder", icon=":material/description:", url_path="reports"),
            st.Page(data_health.page, title="Data Health", icon=":material/fact_check:", url_path="data-health"),
        ],
    }
    nav = st.navigation(pages, position="hidden")
    with nav_slot:
        for section, items in pages.items():
            st.markdown(f'<div class="gc-nav-h">{section}</div>', unsafe_allow_html=True)
            for pg in items:
                st.page_link(pg, label=pg.title, icon=pg.icon)
    st.sidebar.markdown(
        f"""<div style="margin-top:1rem;font-size:.7rem;color:#8C9AB8">Data refreshed {ds.loaded_at}<br>
        Chats to {ds.coverage['chats_to']:%d %b %Y}</div>""", unsafe_allow_html=True)
    nav.run()


main()
