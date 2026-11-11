"""Plotly chart builders with one consistent template. Single axis only; thin marks; target lines in ink."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from kpis import ALL_KPIS, fmt, is_missing
import theme as T

DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _scale(key: str):
    u = ALL_KPIS[key].unit
    return 100.0 if u in ("pct", "ratio") else 1.0


def _suffix(key: str) -> str:
    return {"pct": "%", "ratio": "%", "min": " min", "hrs": " h", "sec": " s", "days": " d"}.get(ALL_KPIS[key].unit, "")


def base(fig: go.Figure, title: str = "", height: int = 320, legend: bool = False) -> go.Figure:
    fig.update_layout(
        title=dict(text=f"<b>{title}</b>" if title else "", x=0.01, y=0.97, font=dict(size=14, color=T.INK)),
        height=height, margin=dict(l=8, r=12, t=46 if title else 12, b=8),
        paper_bgcolor=T.SURFACE, plot_bgcolor=T.SURFACE, font=dict(family=T.FONT, size=12, color=T.INK_2),
        showlegend=legend, legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1, font=dict(size=11)),
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor=T.LINE, font=dict(family=T.FONT, color=T.INK, size=12)),
        bargap=0.35,
    )
    fig.update_xaxes(showgrid=False, linecolor=T.LINE, tickfont=dict(color=T.MUTED), ticks="")
    fig.update_yaxes(gridcolor="#EEF1F5", zeroline=False, linecolor=T.LINE, tickfont=dict(color=T.MUTED))
    return fig


def trend_line(df: pd.DataFrame, x: str, key: str, title: str, target=None, series_label: str = "Team",
               compare: pd.DataFrame | None = None, height: int = 300) -> go.Figure:
    s = _scale(key)
    fig = go.Figure()
    if df is None or x not in df or key not in df or df[key].notna().sum() == 0:
        fig.add_annotation(text="No data for this selection", showarrow=False, font=dict(color=T.MUTED, size=12),
                           xref="paper", yref="paper", x=0.5, y=0.5)
        fig.update_xaxes(visible=False)
        fig.update_yaxes(visible=False)
        return base(fig, title, height)
    d = df[df[key].notna()]
    fig.add_trace(go.Scatter(x=d[x], y=d[key] * s, mode="lines+markers", name=series_label,
                             line=dict(color=T.PRIMARY_SERIES, width=2.2), marker=dict(size=8, line=dict(color="#fff", width=2)),
                             hovertemplate=f"%{{x}}<br>{ALL_KPIS[key].label}: %{{y:.2f}}{_suffix(key)}<extra></extra>"))
    if compare is not None and key in compare:
        c = compare[compare[key].notna()]
        fig.add_trace(go.Scatter(x=c[x], y=c[key] * s, mode="lines+markers", name="Team average",
                                 line=dict(color=T.COMPARE_SERIES, width=2, dash="dot"), marker=dict(size=7),
                                 hovertemplate=f"%{{x}}<br>Team: %{{y:.2f}}{_suffix(key)}<extra></extra>"))
    if target is not None and not is_missing(target):
        fig.add_hline(y=target * s, line=dict(color=T.TARGET, width=1.2, dash="dash"),
                      annotation_text=f"Target {fmt(key, target)}", annotation_position="top left",
                      annotation_font=dict(size=11, color=T.INK))
    fig.update_yaxes(ticksuffix=_suffix(key).strip() if _suffix(key) in ("%",) else "")
    fig.update_xaxes(type="category")
    return base(fig, title, height, legend=compare is not None)


def actual_vs_target_bars(df: pd.DataFrame, cat: str, key: str, title: str, target=None, team_value=None,
                          height: int = 340, highlight: str | None = None) -> go.Figure:
    """Horizontal bars per agent/group sorted best → worst for the KPI's direction; target and team lines."""
    s = _scale(key)
    k = ALL_KPIS[key]
    d = df[df[key].notna()].copy()
    asc = k.direction == "lower"
    d = d.sort_values(key, ascending=not asc)
    colors = []
    for v, name in zip(d[key], d[cat]):
        if target is not None and not is_missing(target):
            ok = v >= target if k.direction == "higher" else v <= target
            colors.append(T.PRIMARY_SERIES if ok else T.SERIES[1])
        else:
            colors.append(T.PRIMARY_SERIES)
        if highlight and name != highlight:
            colors[-1] = "#CBD5E1"
    fig = go.Figure(go.Bar(
        x=d[key] * s, y=d[cat], orientation="h", marker=dict(color=colors, cornerradius=4),
        text=[fmt(key, v) for v in d[key]], textposition="outside", cliponaxis=False,
        textfont=dict(size=11, color=T.INK_2),
        hovertemplate="%{y}<br>" + k.label + ": %{text}<extra></extra>"))
    if target is not None and not is_missing(target):
        fig.add_vline(x=target * s, line=dict(color=T.TARGET, width=1.2, dash="dash"),
                      annotation_text=f"Target {fmt(key, target)}", annotation_position="top",
                      annotation_font=dict(size=11, color=T.INK))
    if team_value is not None and not is_missing(team_value):
        fig.add_vline(x=team_value * s, line=dict(color=T.MUTED, width=1, dash="dot"),
                      annotation_text=f"Team {fmt(key, team_value)}", annotation_position="bottom",
                      annotation_font=dict(size=10, color=T.MUTED))
    fig.update_layout(height=max(height, 46 + 30 * len(d)))
    return base(fig, title, max(height, 46 + 30 * len(d)))


def change_bars(df: pd.DataFrame, title: str, height: int = 340) -> go.Figure:
    """Direction-aware % change per KPI: green = improved, red = declined, grey = stable / neutral."""
    d = df[df["change_pct"].notna()].copy()
    d = d.iloc[::-1]
    col = [T.GOOD if t == "improved" else (T.CRITICAL if t == "declined" else T.NEUTRAL) for t in d["trend"]]
    lab = {"improved": "Improved", "declined": "Declined", "stable": "Stable", "up": "Higher (neutral)",
           "down": "Lower (neutral)"}
    fig = go.Figure(go.Bar(
        x=d["change_pct"] * 100, y=d["KPI"], orientation="h", marker=dict(color=col, cornerradius=4),
        text=[f"{v * 100:+.1f}%" for v in d["change_pct"]], textposition="outside", cliponaxis=False,
        customdata=[lab.get(t, t) for t in d["trend"]],
        hovertemplate="%{y}: %{x:+.1f}%<br>%{customdata}<extra></extra>"))
    fig.add_vline(x=0, line=dict(color=T.LINE, width=1))
    lo = min(0.0, float((d["change_pct"] * 100).min())) if len(d) else 0
    hi = max(0.0, float((d["change_pct"] * 100).max())) if len(d) else 0
    span = max(hi - lo, 1)
    fig.update_xaxes(ticksuffix="%", range=[lo - 0.28 * span if lo < 0 else -0.05 * span,
                                            hi + 0.28 * span if hi > 0 else 0.05 * span])
    return base(fig, title, max(height, 40 + 28 * len(d)))


def volume_area(df: pd.DataFrame, x: str, y: str, title: str, label: str, height: int = 280) -> go.Figure:
    fig = go.Figure(go.Scatter(x=df[x], y=df[y], mode="lines", line=dict(color=T.PRIMARY_SERIES, width=2),
                               fill="tozeroy", fillcolor="rgba(42,120,214,0.10)", name=label,
                               hovertemplate="%{x|%a %d %b}<br>" + label + ": %{y:,.0f}<extra></extra>"))
    return base(fig, title, height)


def simple_bars(df: pd.DataFrame, x: str, y: str, title: str, label: str, height: int = 280, horizontal=False,
                color: str | None = None, ticktext=None) -> go.Figure:
    c = color or T.PRIMARY_SERIES
    if horizontal:
        d = df.iloc[::-1]
        fig = go.Figure(go.Bar(x=d[y], y=d[x], orientation="h", marker=dict(color=c, cornerradius=4),
                               text=[f"{v:,.0f}" for v in d[y]], textposition="outside", cliponaxis=False,
                               hovertemplate="%{y}<br>" + label + ": %{x:,.0f}<extra></extra>"))
        return base(fig, title, max(height, 40 + 24 * len(d)))
    fig = go.Figure(go.Bar(x=df[x], y=df[y], marker=dict(color=c, cornerradius=4),
                           hovertemplate="%{x}<br>" + label + ": %{y:,.0f}<extra></extra>"))
    if ticktext is not None:
        fig.update_xaxes(tickmode="array", tickvals=list(df[x]), ticktext=ticktext)
    return base(fig, title, height)


def two_period_bars(df: pd.DataFrame, cat: str, cur_col: str, prev_col: str, key: str, cur_label: str,
                    prev_label: str, title: str, height: int = 340) -> go.Figure:
    s = _scale(key)
    d = df[df[cur_col].notna() | df[prev_col].notna()]
    fig = go.Figure()
    fig.add_trace(go.Bar(y=d[cat], x=d[prev_col] * s, name=prev_label, orientation="h",
                         marker=dict(color=T.COMPARE_SERIES, cornerradius=4),
                         hovertemplate="%{y}<br>" + prev_label + ": %{x:.2f}<extra></extra>"))
    fig.add_trace(go.Bar(y=d[cat], x=d[cur_col] * s, name=cur_label, orientation="h",
                         marker=dict(color=T.PRIMARY_SERIES, cornerradius=4),
                         hovertemplate="%{y}<br>" + cur_label + ": %{x:.2f}<extra></extra>"))
    fig.update_layout(barmode="group", bargap=0.3, bargroupgap=0.08)
    fig.update_yaxes(autorange="reversed")
    return base(fig, title, max(height, 60 + 40 * len(d)), legend=True)


def score_breakdown(row: pd.Series, cfg: dict, title: str = "Score composition", height: int = 300) -> go.Figure:
    """Points earned vs points available per scored KPI for one agent."""
    keys = [k for k in ["quality", "chats", "calls", "sales", "reply", "absence"] if cfg["weights"][k]["ptsNoFcr"]]
    earned = [float(row.get(f"pts_{k}", np.nan)) for k in keys]
    mx = [cfg["weights"][k]["ptsNoFcr"] for k in keys]
    labels = [ALL_KPIS[k].label for k in keys]
    fig = go.Figure()
    fig.add_trace(go.Bar(y=labels, x=mx, orientation="h", name="Available", marker=dict(color="#EEF1F5", cornerradius=4),
                         hovertemplate="%{y}: %{x:.0f} pts available<extra></extra>"))
    fig.add_trace(go.Bar(y=labels, x=earned, orientation="h", name="Earned", marker=dict(color=T.PRIMARY_SERIES, cornerradius=4),
                         text=[f"{e:.1f} / {m:.0f}" if not is_missing(e) else "—" for e, m in zip(earned, mx)],
                         textposition="outside", cliponaxis=False,
                         hovertemplate="%{y}: %{x:.1f} pts earned<extra></extra>"))
    fig.update_layout(barmode="overlay")
    fig.update_yaxes(autorange="reversed")
    return base(fig, title, height, legend=True)


def heat(df: pd.DataFrame, title: str, height: int = 300) -> go.Figure:
    fig = go.Figure(go.Heatmap(z=df.values, x=list(df.columns), y=list(df.index),
                               colorscale=[[0, "#EAF2FC"], [1, "#184f95"]], showscale=False,
                               hovertemplate="%{y} %{x}:00<br>%{z:,.0f} chats<extra></extra>", xgap=2, ygap=2))
    return base(fig, title, height)
