"""Reusable UI blocks: page header, filter chips, KPI cards, hero score, insight cards, tables."""
from __future__ import annotations

import html

import numpy as np
import pandas as pd
import streamlit as st

from kpis import ALL_KPIS, achievement, fmt, fmt_delta, is_missing, target_met, trend
import theme as T


def esc(s) -> str:
    return html.escape(str(s))


def page_header(eyebrow: str, title: str, sub: str = "", meta: str = "") -> None:
    st.markdown(
        f"""<div class="gc-head"><div><p class="gc-eyebrow">{esc(eyebrow)}</p><h1 class="gc-title">{esc(title)}</h1>
        {f'<p class="gc-sub">{esc(sub)}</p>' if sub else ''}</div><div class="gc-meta">{meta}</div></div>""",
        unsafe_allow_html=True)


def chips(items: list, warnings: list | None = None) -> None:
    h = "".join(f'<span class="gc-chip">{esc(k)}: <b>{esc(v)}</b></span>' for k, v in items)
    h += "".join(f'<span class="gc-chip warn">⚠ {esc(w)}</span>' for w in (warnings or []))
    st.markdown(f'<div class="gc-chips">{h}</div>', unsafe_allow_html=True)


def section(title: str, sub: str = "") -> None:
    st.markdown(f'<div class="gc-section">{esc(title)}</div>' + (f'<div class="gc-section-sub">{esc(sub)}</div>' if sub else ""),
                unsafe_allow_html=True)


def note(text: str) -> None:
    st.markdown(f'<div class="gc-note">{text}</div>', unsafe_allow_html=True)


def status_pill(key: str, v, target, night: bool = False) -> str:
    if night and key == "calls":
        s = T.STATUS["night"]
    elif ALL_KPIS[key].key == "fcr" and False:
        s = T.STATUS["monitor"]
    else:
        met = target_met(key, v, target)
        s = T.STATUS["no_data"] if met is None else (T.STATUS["on_target"] if met else T.STATUS["below_target"])
    return (f'<span class="gc-pill" style="background:{s["bg"]};color:{s["text"]}">'
            f'<span style="color:{s["color"]}">{s["icon"]}</span>{s["label"]}</span>')


def trend_html(key: str, cur, prev, prev_label: str = "") -> str:
    t = trend(key, cur, prev)
    if t == "na":
        return f'<span class="gc-delta" style="color:{T.MUTED}">– no comparison</span>'
    d = fmt_delta(key, cur - prev)
    if t in ("up", "down"):
        icon = "▲" if t == "up" else "▼"
        return f'<span class="gc-delta" style="color:{T.INK_2}">{icon} {d}</span>'
    s = T.TREND[t]
    return f'<span class="gc-delta" style="color:{s["text"]}">{s["icon"]} {d}</span>'


def ach_txt(a) -> str:
    if is_missing(a):
        return "—"
    return "≥200%" if a >= 2 else f"{a * 100:.0f}%"


def kpi_card(key: str, value, target=None, prev=None, prev_label: str = "", note_txt: str = "",
             night: bool = False, unavailable: str = "") -> None:
    k = ALL_KPIS[key]
    if unavailable:
        body = (f'<div class="gc-kpi-value" style="font-size:1.05rem;color:{T.MUTED};margin-top:.6rem">Not available</div>'
                f'<div class="gc-kpi-row"><span>{esc(unavailable)}</span></div>')
        st.markdown(f'<div class="gc-card"><div class="gc-kpi-label"><span>{esc(k.label)}</span></div>{body}</div>',
                    unsafe_allow_html=True)
        return
    has_t = target is not None and not is_missing(target)
    pill = status_pill(key, value, target, night) if has_t else ""
    bar = ""
    if has_t and not is_missing(value):
        ach = achievement(key, value, target)
        if not is_missing(ach):
            w = max(2, min(100, ach * 100))
            met = target_met(key, value, target)
            col = T.GOOD if met else T.CRITICAL
            bar = f'<div class="gc-bar" title="Achievement {ach * 100:.0f}% of target"><span style="width:{w}%;background:{col}"></span></div>'
    rows = []
    if has_t:
        rows.append(f'<span>Target <b>{fmt(key, target)}</b></span>')
        if not is_missing(value):
            ach = achievement(key, value, target)
            if not is_missing(ach):
                rows.append(f'<span>Achievement <b>{ach_txt(ach)}</b></span>')
    if prev is not None:
        rows.append(f'<span>{trend_html(key, value, prev)} <span style="color:{T.MUTED}">vs {esc(prev_label)}</span></span>')
    if note_txt:
        rows.append(f'<span>{esc(note_txt)}</span>')
    st.markdown(
        f"""<div class="gc-card" title="{esc(k.definition)}"><div class="gc-kpi-label"><span>{esc(k.label)}</span>{pill}</div>
        <div class="gc-kpi-value">{fmt(key, value)}</div>{bar}<div class="gc-kpi-row">{''.join(rows)}</div></div>""",
        unsafe_allow_html=True)


def kpi_grid(items: list, cols: int = 4) -> None:
    """items: list of dicts with kpi_card kwargs."""
    for i in range(0, len(items), cols):
        cs = st.columns(cols, gap="small")
        for c, it in zip(cs, items[i:i + cols]):
            with c:
                kpi_card(**it)
        st.write("")


def hero_score(value, target, prev, prev_label, agents_met: str, label: str = "Team KPI score", unavailable: str = "") -> None:
    if unavailable or is_missing(value):
        st.markdown(f"""<div class="gc-hero"><div class="lbl">{esc(label)}</div>
        <div class="val" style="font-size:1.4rem;margin-top:1rem">Not available</div>
        <div class="row"><span>{esc(unavailable or 'No data for this period')}</span></div></div>""", unsafe_allow_html=True)
        return
    met = value >= target
    s = T.STATUS["on_target"] if met else T.STATUS["below_target"]
    prev_txt = ""
    if not is_missing(prev):
        t = trend("score", value, prev)
        icon = T.TREND[t]["icon"] if t in T.TREND else ""
        prev_txt = f'<span>{icon} <b>{value - prev:+.1f} pts</b> vs {esc(prev_label)} ({prev:.1f})</span>'
    st.markdown(f"""<div class="gc-hero"><div class="lbl">{esc(label)}</div>
      <div class="val">{value:.1f}<small> / 100</small></div>
      <span class="gc-pill" style="background:{s['bg']};color:{s['text']}">{s['icon']} {s['label']} · target {target:.0f}</span>
      <div class="row">{prev_txt}<span>{esc(agents_met)}</span></div></div>""", unsafe_allow_html=True)


def insight_cards(items: list, limit: int | None = None, empty: str = "No findings for the current selection.") -> None:
    if not items:
        note(empty)
        return
    for i in items[:limit] if limit else items:
        s = T.SEVERITY.get(i.severity, T.SEVERITY["info"])
        body = f"<p>{esc(i.what)}</p>"
        if i.why:
            body += f"<p><b>Why it matters:</b> {esc(i.why)}</p>"
        if i.action:
            body += f"<p><b>Recommended action:</b> {esc(i.action)}</p>"
        kind = f'<span class="kind">{esc(i.basis)}</span>' if i.basis != "Confirmed" else ""
        st.markdown(f"""<div class="gc-insight" style="--sev:{s['color']}"><div class="t"><span class="tag">{s['label']}</span>
            {esc(i.title)} {kind}</div><div class="b">{body}</div></div>""", unsafe_allow_html=True)


# ------------------------------------------------------------------------------------------------ tables
def trend_text(t: str) -> str:
    return {"improved": "▲ Improved", "declined": "▼ Declined", "stable": "■ Stable", "na": "–",
            "up": "▲ Higher", "down": "▼ Lower"}.get(t, "–")


def met_text(m) -> str:
    if m is True or m == "Yes":
        return "● On target"
    if m is False or m == "No":
        return "▲ Below target"
    if m == "Night shift":
        return "◐ Night shift"
    return "○ No data"


def style_status(df: pd.DataFrame, cols: list):
    def color(v):
        v = str(v)
        if v.startswith("●") or v.startswith("▲ Improved"):
            return f"color:{T.GOOD_TEXT};font-weight:600"
        if v.startswith("▲ Below") or v.startswith("▼ Declined"):
            return "color:#A12B2B;font-weight:600"
        return f"color:{T.MUTED}"
    return df.style.map(color, subset=[c for c in cols if c in df.columns])


def kpi_value_col(key: str, label: str | None = None):
    k = ALL_KPIS[key]
    lab = label or k.label
    if k.unit == "pct":
        return st.column_config.NumberColumn(lab, format="%.1f%%", help=k.definition)
    if k.unit == "ratio":
        return st.column_config.NumberColumn(lab, format="%.0f%%", help=k.definition)
    fmt_ = {"min": "%.1f", "hrs": "%.1f", "sec": "%.0f", "days": "%.2f", "count": "%d", "pts": "%.1f"}.get(k.unit, "%.2f")
    return st.column_config.NumberColumn(lab, format=fmt_, help=k.definition)


def pct_for_display(df: pd.DataFrame, keys: list, suffixes=("",)) -> pd.DataFrame:
    """Percent/ratio KPIs are stored as fractions; tables show them ×100."""
    d = df.copy()
    for k in keys:
        if ALL_KPIS[k].unit in ("pct", "ratio"):
            for sfx in suffixes:
                c = f"{k}{sfx}"
                if c in d.columns:
                    d[c] = d[c] * 100
    return d
