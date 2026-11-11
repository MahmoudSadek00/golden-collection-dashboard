"""Design tokens and global styling. One place for every colour, so pages, charts and the Excel report agree."""
from __future__ import annotations

import streamlit as st

# Brand / chrome
NAVY = "#14213D"
NAVY_2 = "#1F2E52"
GOLD = "#B88A2E"            # Golden Collection accent, used sparingly
INK = "#0F172A"
INK_2 = "#475569"
MUTED = "#64748B"
LINE = "#E2E8F0"
SURFACE = "#FFFFFF"
CANVAS = "#F5F6F8"

# Data series (validated categorical order: blue, orange, aqua)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
PRIMARY_SERIES = SERIES[0]
COMPARE_SERIES = "#94A3B8"     # the comparison / previous period, recessive grey

# Status (reserved: never used as a series colour; always shown with an icon + label)
GOOD = "#0ca30c"
GOOD_TEXT = "#0B7A0B"
WARNING = "#fab219"
WARNING_TEXT = "#8A5A00"
SERIOUS = "#ec835a"
CRITICAL = "#d03b3b"
NEUTRAL = "#94A3B8"
TARGET = INK

STATUS = {
    "on_target": {"label": "On target", "color": GOOD, "text": GOOD_TEXT, "bg": "#E8F6E8", "icon": "●"},
    "below_target": {"label": "Below target", "color": CRITICAL, "text": "#A12B2B", "bg": "#FBEAEA", "icon": "▲"},
    "no_data": {"label": "No data", "color": NEUTRAL, "text": MUTED, "bg": "#F1F5F9", "icon": "○"},
    "monitor": {"label": "Monitor only", "color": NEUTRAL, "text": INK_2, "bg": "#F1F5F9", "icon": "◇"},
    "night": {"label": "Night shift", "color": NEUTRAL, "text": INK_2, "bg": "#F1F5F9", "icon": "◐"},
}
TREND = {
    "improved": {"label": "Improved", "color": GOOD, "text": GOOD_TEXT, "icon": "▲"},
    "declined": {"label": "Declined", "color": CRITICAL, "text": "#A12B2B", "icon": "▼"},
    "stable": {"label": "Stable", "color": NEUTRAL, "text": MUTED, "icon": "■"},
    "na": {"label": "Not comparable", "color": NEUTRAL, "text": MUTED, "icon": "–"},
}
SEVERITY = {
    "critical": {"label": "Critical", "color": CRITICAL, "bg": "#FBEAEA"},
    "warning": {"label": "Attention", "color": "#C98500", "bg": "#FFF6E0"},
    "positive": {"label": "Positive", "color": GOOD, "bg": "#E8F6E8"},
    "info": {"label": "Note", "color": "#2a78d6", "bg": "#EAF2FC"},
}

FONT = "Inter, 'Segoe UI', system-ui, -apple-system, sans-serif"


def inject_css() -> None:
    st.markdown(
        f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, .stText, button, input, select, textarea {{ font-family: {FONT}; }}
.stApp {{ background: {CANVAS}; }}
header[data-testid="stHeader"] {{ background: transparent; height: 0; }}
#MainMenu, footer, [data-testid="stDecoration"] {{ visibility: hidden; height: 0; }}
.block-container {{ padding-top: 1.4rem; padding-bottom: 3rem; max-width: 1480px; }}

/* Sidebar */
section[data-testid="stSidebar"] {{ background: {NAVY}; border-right: 0; }}
section[data-testid="stSidebar"] * {{ color: #E5E9F2; }}
section[data-testid="stSidebar"] [data-testid="stSidebarNavSeparator"] {{ border-color: rgba(255,255,255,.12); }}
section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"] {{ border-radius: 8px; margin: 1px 0; }}
section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"]:hover {{ background: rgba(255,255,255,.08); }}
section[data-testid="stSidebar"] a[aria-current="page"] {{ background: rgba(184,138,46,.22) !important; }}
section[data-testid="stSidebar"] a[aria-current="page"] span {{ color: #FFFFFF !important; font-weight: 600; }}
section[data-testid="stSidebar"] header, section[data-testid="stSidebar"] [data-testid="stSidebarNavItems"] li header span
  {{ color: #8C9AB8 !important; text-transform: uppercase; font-size: .70rem; letter-spacing: .08em; }}
section[data-testid="stSidebar"] .stSelectbox div[data-baseweb="select"] > div,
section[data-testid="stSidebar"] .stMultiSelect div[data-baseweb="select"] > div,
section[data-testid="stSidebar"] .stDateInput input {{ background: {NAVY_2}; border-color: rgba(255,255,255,.15); color: #fff; }}
section[data-testid="stSidebar"] [data-baseweb="tag"] {{ background: rgba(184,138,46,.35); }}
section[data-testid="stSidebar"] .stButton button {{ background: transparent; border: 1px solid rgba(255,255,255,.25); }}
section[data-testid="stSidebar"] .stButton button:hover {{ border-color: {GOLD}; color: #fff; }}
section[data-testid="stSidebar"] label p {{ font-size: .78rem; font-weight: 500; color: #AEB9D1 !important; }}

.gc-nav-h {{ color:#8C9AB8; text-transform:uppercase; font-size:.66rem; letter-spacing:.09em; margin:.9rem 0 .35rem .35rem; font-weight:600; line-height:1; }}
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] {{ border-radius:8px; padding:.15rem .5rem; }}
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover {{ background: rgba(255,255,255,.08); }}
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"],
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][data-active="true"] {{ background: rgba(184,138,46,.22); }}
section[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"] p {{ font-size:.9rem; }}
section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {{ gap: .35rem; }}

/* Page header */
.gc-head {{ display:flex; justify-content:space-between; align-items:flex-end; gap:16px; margin-bottom: .6rem; flex-wrap: wrap; }}
.gc-eyebrow {{ font-size:.72rem; letter-spacing:.09em; text-transform:uppercase; color:{GOLD}; font-weight:600; margin:0; }}
.gc-title {{ font-size:1.65rem; font-weight:700; color:{INK}; margin:.1rem 0 0 0; line-height:1.2; }}
.gc-sub {{ color:{INK_2}; font-size:.9rem; margin:.25rem 0 0 0; }}
.gc-head > div:first-child {{ flex: 1 1 520px; }}
.gc-meta {{ color:{MUTED}; font-size:.78rem; text-align:right; margin-left:auto; }}

/* Filter chips */
.gc-chips {{ display:flex; flex-wrap:wrap; gap:6px; margin:.2rem 0 1rem 0; }}
.gc-chip {{ background:{SURFACE}; border:1px solid {LINE}; border-radius:999px; padding:3px 10px; font-size:.76rem; color:{INK_2}; }}
.gc-chip b {{ color:{INK}; font-weight:600; }}
.gc-chip.warn {{ border-color:#F3D28A; background:#FFF8E6; color:{WARNING_TEXT}; }}

/* Cards */
.gc-card {{ background:{SURFACE}; border:1px solid {LINE}; border-radius:12px; padding:16px 18px; height:100%;
           box-shadow: 0 1px 2px rgba(15,23,42,.04); }}
.gc-kpi-label {{ font-size:.78rem; color:{INK_2}; font-weight:500; display:flex; justify-content:space-between; align-items:center; gap:6px; }}
.gc-kpi-label > span:first-child {{ line-height:1.25; }}
.gc-kpi-value {{ font-size:1.75rem; font-weight:700; color:{INK}; margin:.35rem 0 .1rem 0; line-height:1.1; font-variant-numeric: tabular-nums; }}
.gc-kpi-value small {{ font-size:.9rem; font-weight:500; color:{MUTED}; margin-left:3px; }}
.gc-kpi-row {{ display:flex; justify-content:space-between; font-size:.76rem; color:{MUTED}; margin-top:.35rem; gap:8px; flex-wrap:wrap; }}
.gc-kpi-row b {{ color:{INK_2}; font-weight:600; }}
.gc-bar {{ height:5px; background:#EEF1F5; border-radius:3px; margin-top:.55rem; position:relative; overflow:hidden; }}
.gc-bar > span {{ position:absolute; left:0; top:0; bottom:0; border-radius:3px; }}
.gc-pill {{ display:inline-flex; align-items:center; gap:4px; border-radius:999px; padding:1px 7px; font-size:.66rem; font-weight:600; white-space:nowrap; flex-shrink:0; }}
.gc-delta {{ font-size:.76rem; font-weight:600; white-space:nowrap; }}

/* Hero score */
.gc-hero {{ background: linear-gradient(135deg, {NAVY} 0%, {NAVY_2} 100%); color:#fff; border-radius:14px; padding:20px 22px; height:100%; }}
.gc-hero .lbl {{ font-size:.75rem; letter-spacing:.08em; text-transform:uppercase; color:#C9D2E6; }}
.gc-hero .val {{ font-size:3rem; font-weight:700; line-height:1; margin:.5rem 0 .2rem 0; font-variant-numeric: tabular-nums; }}
.gc-hero .val small {{ font-size:1.05rem; color:#C9D2E6; font-weight:500; }}
.gc-hero .row {{ display:flex; gap:18px; flex-wrap:wrap; font-size:.8rem; color:#DCE3F1; margin-top:.6rem; }}
.gc-hero .row b {{ color:#fff; }}

/* Section */
.gc-section {{ font-size:1.02rem; font-weight:650; color:{INK}; margin:1.4rem 0 .15rem 0; }}
.gc-section-sub {{ font-size:.82rem; color:{MUTED}; margin:0 0 .7rem 0; }}

/* Insights */
.gc-insight {{ background:{SURFACE}; border:1px solid {LINE}; border-left:4px solid var(--sev); border-radius:10px; padding:12px 14px; margin-bottom:10px; }}
.gc-insight .t {{ font-weight:650; color:{INK}; font-size:.92rem; margin-bottom:4px; display:flex; gap:8px; align-items:center; flex-wrap:wrap; }}
.gc-insight .b {{ color:{INK_2}; font-size:.84rem; line-height:1.5; }}
.gc-insight .b p {{ margin:.15rem 0; }}
.gc-insight .tag {{ font-size:.66rem; text-transform:uppercase; letter-spacing:.06em; font-weight:700; color:var(--sev); }}
.gc-insight .kind {{ font-size:.66rem; color:{MUTED}; border:1px solid {LINE}; border-radius:999px; padding:0 7px; }}

/* Notes */
.gc-note {{ background:#F8FAFC; border:1px dashed #CBD5E1; border-radius:10px; padding:10px 12px; color:{INK_2}; font-size:.8rem; }}
.gc-soon {{ background:{SURFACE}; border:1px solid {LINE}; border-radius:14px; padding:28px; }}
.gc-soon h3 {{ margin:0 0 .3rem 0; color:{INK}; }}
.gc-grid {{ display:grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap:10px; margin-top:14px; }}
.gc-grid div {{ border:1px solid {LINE}; border-radius:10px; padding:10px 12px; font-size:.84rem; color:{INK_2}; background:#FBFCFD; }}
.gc-grid div b {{ display:block; color:{INK}; font-size:.88rem; margin-bottom:2px; }}

/* Tabs & tables */
.stTabs [data-baseweb="tab-list"] {{ gap: 2px; border-bottom: 1px solid {LINE}; }}
.stTabs [data-baseweb="tab"] {{ padding: 8px 14px; font-weight: 500; color:{INK_2}; }}
.stTabs [aria-selected="true"] {{ color:{INK}; }}
[data-testid="stDataFrame"] {{ border:1px solid {LINE}; border-radius:10px; overflow:hidden; background:{SURFACE}; }}
div[data-testid="stPlotlyChart"] {{ background:{SURFACE}; border:1px solid {LINE}; border-radius:12px; padding:6px 4px 0 4px; }}
.stDownloadButton button, .stButton button[kind="primary"] {{ background:{NAVY}; color:#fff; border:0; border-radius:8px; }}
.stDownloadButton button:hover {{ background:{NAVY_2}; color:#fff; }}
@media (max-width: 760px) {{ .gc-kpi-value {{ font-size:1.4rem; }} .gc-hero .val {{ font-size:2.3rem; }} .gc-title {{ font-size:1.3rem; }} }}
</style>
""",
        unsafe_allow_html=True,
    )
