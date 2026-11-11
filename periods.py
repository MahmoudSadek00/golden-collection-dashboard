"""Reporting periods: months, quarters, years, ISO weeks and custom ranges, with completeness checks."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

KINDS = ["Month", "Quarter", "Year", "Week", "Custom"]
SCORED_KINDS = {"Month", "Quarter"}          # the approved score is defined per month and quarter


@dataclass(frozen=True)
class Period:
    kind: str
    label: str
    start: pd.Timestamp
    end: pd.Timestamp

    @property
    def days(self) -> int:
        return int((self.end - self.start).days) + 1

    @property
    def scored(self) -> bool:
        return self.kind in SCORED_KINDS

    @property
    def engine_label(self) -> str:
        """Label used by LS_Scorecard / KPI_Frozen_Q3 ('2026-07', '2026 Q3')."""
        return self.label

    def short(self) -> str:
        if self.kind in ("Custom", "Week"):
            return f"{self.start:%d %b} – {self.end:%d %b %Y}"
        return self.label


def month(y: int, m: int) -> Period:
    s = pd.Timestamp(year=y, month=m, day=1)
    return Period("Month", f"{y}-{m:02d}", s, s + pd.offsets.MonthEnd(0))


def quarter(y: int, q: int) -> Period:
    s = pd.Timestamp(year=y, month=3 * (q - 1) + 1, day=1)
    return Period("Quarter", f"{y} Q{q}", s, s + pd.offsets.QuarterEnd(0))


def year(y: int) -> Period:
    return Period("Year", str(y), pd.Timestamp(year=y, month=1, day=1), pd.Timestamp(year=y, month=12, day=31))


def week(start: pd.Timestamp) -> Period:
    s = pd.Timestamp(start).normalize()
    s = s - pd.Timedelta(days=s.weekday())
    iso = s.isocalendar()
    return Period("Week", f"{iso[0]} W{iso[1]:02d}", s, s + pd.Timedelta(days=6))


def custom(start, end) -> Period:
    s, e = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize()
    if e < s:
        s, e = e, s
    return Period("Custom", f"{s:%Y-%m-%d} – {e:%Y-%m-%d}", s, e)


def month_label_long(p: Period) -> str:
    if p.kind == "Month":
        return p.start.strftime("%B %Y")
    return p.short()


def available(kind: str, data_from: pd.Timestamp, data_to: pd.Timestamp) -> list:
    """Periods of a kind that overlap the data range, newest first."""
    if pd.isna(data_from) or pd.isna(data_to):
        return []
    out = []
    if kind == "Month":
        cur = pd.Timestamp(year=data_from.year, month=data_from.month, day=1)
        while cur <= data_to:
            out.append(month(cur.year, cur.month))
            cur = cur + pd.offsets.MonthBegin(1)
    elif kind == "Quarter":
        cur = pd.Timestamp(year=data_from.year, month=3 * ((data_from.month - 1) // 3) + 1, day=1)
        while cur <= data_to:
            out.append(quarter(cur.year, (cur.month - 1) // 3 + 1))
            cur = cur + pd.offsets.QuarterBegin(1, startingMonth=1)
    elif kind == "Year":
        out = [year(y) for y in range(data_from.year, data_to.year + 1)]
    elif kind == "Week":
        cur = data_from - pd.Timedelta(days=data_from.weekday())
        while cur <= data_to:
            out.append(week(cur))
            cur = cur + pd.Timedelta(days=7)
    return list(reversed(out))


def previous(p: Period) -> Period:
    if p.kind == "Month":
        s = p.start - pd.offsets.MonthBegin(1)
        return month(s.year, s.month)
    if p.kind == "Quarter":
        s = p.start - pd.offsets.QuarterBegin(1, startingMonth=1)
        return quarter(s.year, (s.month - 1) // 3 + 1)
    if p.kind == "Year":
        return year(p.start.year - 1)
    if p.kind == "Week":
        return week(p.start - pd.Timedelta(days=7))
    length = p.days
    e = p.start - pd.Timedelta(days=1)
    return custom(e - pd.Timedelta(days=length - 1), e)


def coverage_status(p: Period, data_from: pd.Timestamp, data_to: pd.Timestamp) -> dict:
    """How much of the period is covered by the chat data (the scorecard's main source)."""
    if pd.isna(data_from) or pd.isna(data_to):
        return {"complete": False, "covered_days": 0, "note": "No data"}
    s = max(p.start, data_from.normalize())
    e = min(p.end, data_to.normalize())
    covered = max(0, int((e - s).days) + 1) if e >= s else 0
    complete = covered == p.days
    note = ""
    if covered == 0:
        note = "No data for this period"
    elif not complete:
        if p.end > data_to:
            note = f"Incomplete: data up to {data_to:%d %b %Y} ({covered} of {p.days} days)"
        else:
            note = f"Partial: data starts {data_from:%d %b %Y} ({covered} of {p.days} days)"
    return {"complete": complete, "covered_days": covered, "note": note}


def comparable(a: Period, b: Period, ca: dict, cb: dict) -> list:
    """Warnings that make a comparison less reliable (never blocks it, always shown)."""
    w = []
    if abs(a.days - b.days) > max(2, 0.1 * max(a.days, b.days)):
        w.append(f"Different lengths ({a.days} vs {b.days} days): totals are not comparable, rates are.")
    for p, c in ((a, ca), (b, cb)):
        if c.get("note"):
            w.append(f"{p.short()}: {c['note']}.")
    return w
