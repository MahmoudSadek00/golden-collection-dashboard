"""Logistics module contract.

Logistics data is not connected yet. When the daily summary tab is ready (one row per day x market x courier,
like CS_Agent_Daily for Customer Support), set [sheets] logistics_spreadsheet_id and logistics_tab in the secrets
and implement the KPI definitions approved for Logistics in logistics/kpis.py. Until then the Logistics pages show
a 'coming soon' state and no figures are produced.
"""
from __future__ import annotations

# Proposed daily summary contract (to be confirmed with the Logistics data owner before implementation)
PROPOSED_DAILY_COLUMNS = [
    ("Date", "Day the orders are counted for (yyyy-mm-dd)"),
    ("Market", "UAE, KSA, Qatar, Kuwait, Oman, Bahrain, Iraq …"),
    ("Courier", "3PL / courier name"),
    ("Orders Created", "Orders placed that day"),
    ("Orders Shipped", "Orders handed to the courier that day"),
    ("Delivered", "Orders delivered that day"),
    ("Delivered Within SLA", "Delivered orders within the market delivery window"),
    ("Pending", "Open orders at end of day"),
    ("Cancelled", "Orders cancelled that day"),
    ("Returned", "Orders returned that day"),
    ("Failed Delivery (NDR)", "Delivery attempts that failed that day"),
    ("Order Value (USD)", "Value of the orders counted (currency rules as agreed)"),
]

PLANNED_FEATURES = [
    ("Orders Overview", "Created, shipped, delivered and open orders by day, market and courier."),
    ("Delivery Performance", "Delivery rate and on-time delivery against the approved targets."),
    ("3PL / Courier Performance", "Courier comparison on delivery rate, SLA and failed deliveries."),
    ("Pending Orders", "Open orders and their age."),
    ("Delivered Orders", "Delivered volume and value."),
    ("Cancelled Orders", "Cancellations by market and reason."),
    ("Returned Orders", "Returns by market, courier and reason."),
    ("Failed Deliveries / NDR", "Failed attempts and their resolution."),
    ("Delivery Rate", "Delivered ÷ shipped."),
    ("Return Rate", "Returned ÷ delivered."),
    ("Aging Analysis", "Open orders by days since order."),
    ("SLA Performance", "Deliveries within each market's delivery window."),
    ("Market Performance", "All logistics KPIs by market."),
]


def is_connected(secrets) -> bool:
    try:
        sh = secrets.get("sheets", {})
        return bool(sh.get("logistics_spreadsheet_id")) and bool(sh.get("logistics_tab"))
    except Exception:  # noqa: BLE001
        return False
