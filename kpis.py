"""KPI catalogue: labels, units, direction of improvement, formatting and definitions shown to users.

Two families:
* SCORE KPIs: the approved scorecard (LS_Scorecard / LS_Team logic, see core.kpi_engine).
* OPERATIONAL metrics: the CS Pulse / Looker definitions (adherence, occupancy, call answer rate, ...).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class KPI:
    key: str
    label: str
    unit: str            # "pct" | "num" | "min" | "days" | "pts" | "count" | "sec" | "hrs" | "ratio"
    direction: str       # "higher" | "lower" | "neutral"
    family: str          # "score" | "ops"
    definition: str
    decimals: int = 1
    monthly_only: bool = False


SCORE_KPIS = {
    "score": KPI("score", "KPI Score", "pts", "higher", "score",
                 "Sum of the KPI points (Quality 35, Chats/day 25, Calls/day 5, Sales contribution 10, "
                 "First reply 20, Absence 5). Team score = average of the agents' scores.", 1),
    "quality": KPI("quality", "Quality", "pct", "higher", "score",
                   "Monthly QA score from QA_Input. Team = average of the agents' QA scores.", 1, monthly_only=True),
    "chats": KPI("chats", "Chats per Day", "num", "higher", "score",
                 "Unique customers closed (credited to the agent who closed the chat, by resolved date) "
                 "÷ working days.", 1),
    "calls": KPI("calls", "Calls per Day", "num", "higher", "score",
                 "Inbound calls ÷ working days. Night-shift agents receive the best day-agent points.", 2),
    "sales": KPI("sales", "Sales Contribution", "ratio", "higher", "score",
                 "Share of team delivered sales ÷ share of team sales chats. Agent level only "
                 "(always 100% for the team).", 2),
    "reply": KPI("reply", "First Reply", "min", "lower", "score",
                 "Average minutes from first assignment to first response, chats by start date. "
                 "Team = average of the agents' values.", 1),
    "absence": KPI("absence", "Absence", "days", "lower", "score",
                   "Sick + casual leave days ÷ months in the period. Team = all days ÷ agents ÷ months.", 2,
                   monthly_only=True),
    "fcr": KPI("fcr", "FCR", "pct", "higher", "score",
               "Chats on FCR topics not reopened by the same customer for the same problem within 7 days ÷ chats "
               "checked. Monitored only (no points). The last 7 days of data are not yet checked.", 1),
}
SCORE_ORDER = ["score", "quality", "chats", "calls", "sales", "reply", "absence", "fcr"]
TEAM_ORDER = ["score", "quality", "chats", "calls", "reply", "absence", "fcr"]

OPS_KPIS = {
    "conversations": KPI("conversations", "Conversations", "count", "neutral", "ops",
                         "Chats started in the period (CS team, included agents).", 0),
    "customers": KPI("customers", "Unique Customers", "count", "neutral", "ops",
                     "Distinct contacts with at least one chat started in the period.", 0),
    "frt_median": KPI("frt_median", "First Reply (median)", "min", "lower", "ops",
                      "Median minutes from first assignment to first response.", 1),
    "resolution_median": KPI("resolution_median", "Resolution Time (median)", "hrs", "lower", "ops",
                             "Median hours from chat start to resolution (CS_Chats 'Resolution').", 1),
    "messages_per_chat": KPI("messages_per_chat", "Messages per Chat", "num", "neutral", "ops",
                             "Average messages per conversation.", 1),
    "inbound_calls": KPI("inbound_calls", "Inbound Calls", "count", "neutral", "ops",
                         "Inbound calls in the period (included).", 0),
    "answer_rate": KPI("answer_rate", "Call Answer Rate", "pct", "higher", "ops",
                       "Answered inbound calls ÷ inbound calls.", 1),
    "call_aht": KPI("call_aht", "Call Handling Time (AHT)", "sec", "lower", "ops",
                    "Average handling seconds of answered inbound calls.", 0),
    "call_wait": KPI("call_wait", "Call Waiting Time", "sec", "lower", "ops",
                     "Average waiting seconds of answered inbound calls.", 0),
    "adherence": KPI("adherence", "Schedule Adherence", "pct", "higher", "ops",
                     "Adherent minutes ÷ scheduled minutes (complete working days).", 1),
    "occupancy": KPI("occupancy", "Occupancy", "pct", "neutral", "ops",
                     "Busy + chat minutes while available ÷ online minutes (complete working days).", 1),
    "shrinkage": KPI("shrinkage", "Shrinkage", "pct", "lower", "ops",
                     "Break, coaching, training and technical minutes ÷ planned minutes.", 1),
}
ALL_KPIS = {**SCORE_KPIS, **OPS_KPIS}


def is_missing(v) -> bool:
    return v is None or (isinstance(v, (float, np.floating)) and math.isnan(v))


def fmt(key: str, v, with_unit: bool = True) -> str:
    if is_missing(v):
        return "—"
    k = ALL_KPIS.get(key)
    unit = k.unit if k else "num"
    d = k.decimals if k else 1
    if unit == "pct":
        return f"{v * 100:.{d}f}%"
    if unit == "ratio":
        return f"{v * 100:.0f}%"
    if unit == "min":
        return f"{v:.{d}f} min" if with_unit else f"{v:.{d}f}"
    if unit == "hrs":
        return f"{v:.{d}f} h" if with_unit else f"{v:.{d}f}"
    if unit == "sec":
        return f"{v:,.0f} s" if with_unit else f"{v:,.0f}"
    if unit == "days":
        return f"{v:.{d}f} d" if with_unit else f"{v:.{d}f}"
    if unit == "count":
        return f"{v:,.0f}"
    if unit == "pts":
        return f"{v:.{d}f}"
    return f"{v:,.{d}f}"


def fmt_delta(key: str, d) -> str:
    """Absolute change in the KPI's own unit (percentages as percentage points)."""
    if is_missing(d):
        return "—"
    k = ALL_KPIS.get(key)
    unit = k.unit if k else "num"
    sign = "+" if d > 0 else ("−" if d < 0 else "±")
    a = abs(d)
    if unit == "pct":
        return f"{sign}{a * 100:.1f} pp"
    if unit == "ratio":
        return f"{sign}{a * 100:.0f} pp"
    if unit == "count":
        return f"{sign}{a:,.0f}"
    if unit == "sec":
        return f"{sign}{a:,.1f} s" if a < 10 else f"{sign}{a:,.0f} s"
    if unit == "min":
        return f"{sign}{a:.1f} min"
    if unit == "hrs":
        return f"{sign}{a:.1f} h"
    if unit == "days":
        return f"{sign}{a:.2f} d"
    if unit == "pts":
        return f"{sign}{a:.1f} pts"
    return f"{sign}{a:,.{k.decimals if k else 1}f}"


def target_met(key: str, v, target) -> bool | None:
    if is_missing(v) or is_missing(target):
        return None
    k = ALL_KPIS[key]
    return bool(v >= target) if k.direction == "higher" else bool(v <= target)


def achievement(key: str, v, target):
    """Achievement % of target. For 'lower is better' KPIs it is target ÷ actual (100% = on target)."""
    if is_missing(v) or is_missing(target) or target == 0:
        return np.nan
    k = ALL_KPIS[key]
    if k.direction == "lower":
        return target / v if v > 0 else np.nan
    return v / target


def gap(key: str, v, target):
    """Signed gap to target, positive = better than target (in the KPI's own unit)."""
    if is_missing(v) or is_missing(target):
        return np.nan
    k = ALL_KPIS[key]
    return (v - target) if k.direction == "higher" else (target - v)


STABLE_REL = 0.02   # changes smaller than 2% (relative) are shown as stable; display rule only


def trend(key: str, cur, prev) -> str:
    """'improved' | 'declined' | 'stable' | 'na', aware of each KPI's direction of improvement."""
    if is_missing(cur) or is_missing(prev):
        return "na"
    k = ALL_KPIS[key]
    diff = cur - prev
    base = abs(prev) if prev else abs(cur)
    if base == 0 or abs(diff) / base < STABLE_REL:
        return "stable"
    if k.direction == "neutral":
        return "stable" if diff == 0 else ("up" if diff > 0 else "down")
    better = diff > 0 if k.direction == "higher" else diff < 0
    return "improved" if better else "declined"
