"""Central configuration: data sources, tab names, column contracts and approved KPI defaults.

Business rules come from the "CS & Logistics Bonus Calculator" (CS KPIs tab), exactly as implemented in the
LookerKPI Apps Script that produces LS_Scorecard / LS_Team. Targets and points are read from the KPI_Targets tab
at runtime; the values below are only the defaults the script itself falls back to.
"""
from __future__ import annotations

APP_NAME = "Golden Collection Dashboard"
COMPANY = "Golden Collection"

# --------------------------------------------------------------------------------------------------------------
# Data source tabs (Customer Support spreadsheet unless stated otherwise)
# --------------------------------------------------------------------------------------------------------------
CS_TABS = {
    "chats": "CS_Chats",
    "daily": "CS_Agent_Daily",
    "calls": "CS_Calls",
    "agents": "CS_Agents",
    "name_map": "CS_NameMap",
    "kpi_agents": "KPI_Agents",
    "kpi_targets": "KPI_Targets",
    "qa": "QA_Input",
    "fcr_topics": "FCR_Topics",
    "sales_topics": "Sales_Topics",
    "frozen_q3": "KPI_Frozen_Q3",
    "ls_scorecard": "LS_Scorecard",   # used only by the data-health check (reconciliation)
    "ls_team": "LS_Team",
}
ORDERS_TAB = "Agent_Orders"           # Orders - Clean Data spreadsheet
LARGE_TABS = {"chats", "daily", "calls", "orders"}

# Columns each tab must provide (the app refuses to calculate a KPI whose inputs are missing)
REQUIRED_COLUMNS = {
    "chats": ["Conversation ID", "Contact ID", "Started", "Date", "Resolved", "Agent", "Team", "Include", "Market",
              "Topic", "Opened By", "First Assignment to First Response (sec)", "Resolution (sec)", "Messages",
              "Closed By Agent"],
    "daily": ["Agent", "Team", "Include", "Date", "Shift", "Day Status", "Working Day", "Adherence Num",
              "Adherence Den", "Occupancy Num", "Occupancy Den", "Shrinkage Num", "Shrinkage Den"],
    "calls": ["Call ID", "Date", "Hour", "Type", "Agent", "Include", "Answered", "Inbound", "Handling (sec)",
              "Waiting (sec)", "Sentiment"],
    "orders": ["Order Date", "Status", "Order Value (USD)", "Agent"],
    "kpi_agents": ["Agent", "In KPI score"],
    "qa": ["Agent", "Month (first day)", "QA score"],
    "kpi_targets": ["KPI", "Points in score", "Target"],
}

# --------------------------------------------------------------------------------------------------------------
# Approved KPI engine defaults (identical to KPI_DEFAULTS in LookerKPI.gs)
# --------------------------------------------------------------------------------------------------------------
KPI_KEYS = ["quality", "fcr", "chats", "calls", "sales", "reply", "absence"]
KPI_SHEET_NAMES = {
    "quality": "Quality %", "fcr": "FCR %", "chats": "Chats per day", "calls": "Calls per day",
    "sales": "Sales contribution", "reply": "First reply (min)", "absence": "Absence (days/month)",
}
KPI_DEFAULTS = {
    "weights": {
        "quality": {"pts": 30, "ptsNoFcr": 35, "target": 0.90, "higher": True},
        "fcr": {"pts": 20, "ptsNoFcr": 0, "target": 0.80, "higher": True},
        "chats": {"pts": 15, "ptsNoFcr": 25, "target": 70, "higher": True},
        "calls": {"pts": 5, "ptsNoFcr": 5, "target": 6, "higher": True},
        "sales": {"pts": 10, "ptsNoFcr": 10, "target": 1.0, "higher": True},
        "reply": {"pts": 15, "ptsNoFcr": 20, "target": 9, "higher": False},
        "absence": {"pts": 5, "ptsNoFcr": 5, "target": 1, "higher": False},
    },
    "quality": {"zero": 0.80, "goodStart": 0.85, "goodPts": 24, "full": 0.90},
    "fcr": {"zero": 0.50, "full": 0.80},
    "chats": {"zeroAtOrBelow": 50, "target": 70, "targetPts": 12, "full": 80, "fullPts": 15},
    "calls": [[0, 1.25], [3, 2.5], [5, 3.75], [6, 5]],
    "sales": {"zero": 0.60, "full": 1.0},
    "reply": {"full": 9},
    "absenceMaxPerMonth": 1,
    "nightShiftShare": 0.5,
    "nightShiftName": "12 AM - 9 AM",
    "fcrWindowDays": 7,
    "teamTarget": 85,
}

FROZEN_PERIODS = {"2026 Q3"}           # scores for these periods come from KPI_Frozen_Q3, never recalculated
