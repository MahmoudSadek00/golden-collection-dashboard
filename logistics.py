"""Logistics pages: Performance (team scorecard + operations), Markets, Trends."""
from __future__ import annotations

import io

import numpy as np
import pandas as pd
import streamlit as st

import charts as CH
import components as C
import logi as L
import periods as P
from config import LOGI_CFG
from insights import Insight, SEV_RANK
from kpis import ALL_KPIS, fmt, fmt_delta, is_missing, target_met, trend
from state import ctx

OPS_KEYS = ["l_orders", "l_shipped", "l_delivered", "l_returned", "l_return_rate", "l_transit", "l_cancel_rate",
            "l_dlv_days", "l_lead_days", "l_delivered_value"]
CMP_KEYS = ["l_score", "l_delivery", "l_ontime", "l_markets", "l_return_rate", "l_cancel_rate", "l_dlv_days",
            "l_lead_days", "l_orders", "l_shipped", "l_delivered_value"]
PLOT_CFG = {"displayModeBar": False}


# ------------------------------------------------------------------------------------------------ shared
def _header(title: str, sub: str):
    ds, f = ctx()
    _, t = L.data_range(ds)
    meta = (f"Orders to {t:%d %b %Y}<br>Refreshed {ds.loaded_at}" if not pd.isna(t) else f"Refreshed {ds.loaded_at}")
    C.page_header("Logistics", title, sub, meta)
    if not L.has_data(ds):
        st.warning("The Logistics_Daily tab of the Orders sheet could not be read, so no logistics figures are shown. "
                   "See Data Health.")
        return ds, f, None
    opts = L.countries(ds)
    st.session_state["l_ctry"] = [c for c in st.session_state.get("l_ctry", []) if c in opts]
    ctry = st.multiselect("Markets", opts, key="l_ctry", format_func=L.name, placeholder="All markets")
    warns = []
    cov = L.coverage(ds, f.period)
    if cov.get("note"):
        warns.append(cov["note"])
    if cov.get("maturity_note"):
        warns.append(cov["maturity_note"])
    if f.compare is not None:
        cc = L.coverage(ds, f.compare)
        if cc.get("note"):
            warns.append(f"Comparison: {cc['note']}")
    chips = [("Period", f.period.short() if f.period.kind != "Month" else P.month_label_long(f.period)),
             ("Compared with", f.compare.short() if f.compare else "None"),
             ("Markets", ", ".join(L.name(c) for c in ctry) if ctry else "All")]
    C.chips(chips, warns)
    return ds, f, (ctry or None)


def _row(k, c, p, tgt=None):
    c = np.nan if c is None else c
    p = np.nan if p is None else p
    pct = (c - p) / abs(p) if not (is_missing(c) or is_missing(p)) and p != 0 else np.nan
    return {"key": k, "KPI": ALL_KPIS[k].label, "current": c, "previous": p,
            "change": (c - p) if not (is_missing(c) or is_missing(p)) else np.nan, "change_pct": pct,
            "target": np.nan if tgt is None else tgt, "trend": trend(k, c, p)}


def compare_table(ds, cur, prev, ctry) -> pd.DataFrame:
    tc, tp = L.totals(ds, cur, ctry), (L.totals(ds, prev, ctry) if prev else {})
    sc = L.scorecard(ds, cur) if not ctry else {}
    sp = L.scorecard(ds, prev) if (prev and not ctry) else {}
    T = L.targets()
    rows = []
    for k in CMP_KEYS:
        if k in ("l_score", "l_markets"):
            if ctry or not (cur.scored and (prev is None or prev.scored)):
                continue
            rows.append(_row(k, sc.get(k), sp.get(k) if prev else np.nan, T.get(k)))
        else:
            rows.append(_row(k, tc.get(k), tp.get(k) if prev else np.nan, T.get(k)))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------------ insights
def insights(ds, cur, prev, ctry) -> list:
    out = []
    tc = L.totals(ds, cur, ctry)
    if not tc or not tc["shipped"]:
        return out
    tp = L.totals(ds, prev, ctry) if prev else {}
    pl = prev.short() if prev else ""
    bc = L.by_country(ds, cur, ctry)
    bc = bc[bc["shipped"] > 0]
    bp = L.by_country(ds, prev, ctry).set_index("country") if prev else pd.DataFrame()
    cov = L.coverage(ds, cur)
    basis = "Confirmed" if cov["mature"] else "Not final"

    if cur.scored and not ctry:
        s = L.scorecard(ds, cur)
        sp = L.scorecard(ds, prev) if (prev and prev.scored) else {}
        if not is_missing(s.get("l_score")):
            lost = {"Delivery rate": LOGI_CFG["points"]["delivery"] - s["pts"]["delivery"],
                    "On-time delivery": LOGI_CFG["points"]["ontime"] - s["pts"]["ontime"],
                    "Markets within window": LOGI_CFG["points"]["markets"] - s["pts"]["markets"]}
            worst = max(lost, key=lost.get)
            prev_txt = f" ({sp['l_score']:.1f} in {pl})" if sp and not is_missing(sp.get("l_score")) else ""
            if s["l_score"] < s["target"]:
                out.append(Insight("critical" if s["l_score"] < 80 else "warning", "Team",
                                   f"Logistics score {s['l_score']:.1f} vs target {s['target']:.0f}",
                                   f"Score {s['l_score']:.1f}{prev_txt}. Points lost: " +
                                   "; ".join(f"{k} {v:.1f}" for k, v in lost.items() if v > 0.05) + ".",
                                   "The logistics score is the agreed team measure in the bonus calculator (target 90, "
                                   "no bonus below 80).", f"Focus on {worst.lower()}: it loses the most points.",
                                   basis, 100 - s["l_score"]))
            else:
                out.append(Insight("positive", "Team", f"Logistics score on target: {s['l_score']:.1f}",
                                   f"Score {s['l_score']:.1f} against a target of {s['target']:.0f}{prev_txt}.",
                                   basis=basis, weight=s["l_score"]))

    for k, label in (("l_delivery", "Delivery rate"), ("l_ontime", "On-time delivery")):
        v, t = tc.get(k), L.targets()[k]
        if is_missing(v):
            continue
        col = "l_delivery" if k == "l_delivery" else "l_ontime"
        low = bc[bc[col].notna()].sort_values(col).head(3)
        low_txt = ", ".join(f"{L.name(r.country)} {fmt(k, r[col])}" for _, r in low.iterrows())
        prev_txt = f"; {pl}: {fmt(k, tp.get(k))} ({fmt_delta(k, v - tp.get(k))})" if tp and not is_missing(tp.get(k)) else ""
        if v < t:
            out.append(Insight("critical" if v < LOGI_CFG["delivery"]["zero"] else "warning", "KPI",
                               f"{label} below target: {fmt(k, v)} vs {fmt(k, t)}",
                               f"{label} {fmt(k, v)}{prev_txt}. Lowest markets: {low_txt}.",
                               "Every point below 95% costs logistics score points; at 85% or less the KPI earns nothing."
                               if k == "l_delivery" else
                               "Late deliveries hurt customer experience and cost score points (85% or less = 0).",
                               f"Review shipments in {L.name(low.iloc[0].country)} first." if len(low) else "",
                               basis, (t - v) * 100))
        elif tp and not is_missing(tp.get(k)) and trend(k, v, tp[k]) == "improved":
            out.append(Insight("positive", "KPI", f"{label} improved to {fmt(k, v)}", f"{label} {fmt(k, v)}{prev_txt}.",
                               basis=basis, weight=(v - tp[k]) * 100))

    outside = bc[bc["within"] == False]  # noqa: E712 - None = market without a window
    if len(outside):
        out.append(Insight("warning", "Markets", f"{len(outside)} market(s) outside the delivery window",
                           "; ".join(f"{L.name(r.country)}: {r.l_dlv_days:.1f} days vs window {r.window:.0f}"
                                     if not is_missing(r.l_dlv_days) else f"{L.name(r.country)}: no delivered orders"
                                     for _, r in outside.iterrows()) + ".",
                           "Each market outside its window reduces the markets score (60% or less = 0 points).",
                           "Check courier transit times for these markets.", basis, 10 * len(outside)))

    if tp:
        for k, sev_up in (("l_return_rate", 0.01), ("l_cancel_rate", 0.02)):
            v, p_ = tc.get(k), tp.get(k)
            if is_missing(v) or is_missing(p_):
                continue
            if v - p_ >= sev_up:
                out.append(Insight("warning", "Operations", f"{ALL_KPIS[k].label} up {fmt_delta(k, v - p_)} vs {pl}",
                                   f"{ALL_KPIS[k].label} {fmt(k, v)} vs {fmt(k, p_)} in {pl}.",
                                   "Returned and cancelled orders are lost sales and wasted shipping cost.",
                                   "Break the change down by market on the Markets page.", basis, (v - p_) * 100))
        if not bp.empty:
            slower = []
            for _, r in bc.iterrows():
                if r.country in bp.index and not is_missing(r.l_dlv_days) and not is_missing(bp.loc[r.country, "l_dlv_days"]):
                    d = r.l_dlv_days - bp.loc[r.country, "l_dlv_days"]
                    if d >= 0.5:
                        slower.append((r.country, r.l_dlv_days, d))
            if slower:
                out.append(Insight("warning", "Markets", "Delivery time slower in " +
                                   ", ".join(L.name(c) for c, _, _ in slower),
                                   "; ".join(f"{L.name(c)} {v:.1f} days ({d:+.1f} vs {pl})" for c, v, d in slower) + ".",
                                   "Slower deliveries put the on-time rate and the market window at risk.",
                                   "Follow up with the courier for these markets.", basis, 5 * len(slower)))
    if not cov["mature"]:
        out.append(Insight("info", "Data", "Recent orders still in transit", cov["maturity_note"] + ".",
                           basis="Data note"))
    out.sort(key=lambda i: (SEV_RANK.get(i.severity, 9), -i.weight))
    return out


# ------------------------------------------------------------------------------------------------ Excel
def _excel(ds, f, ctry, cmp_df: pd.DataFrame, bc: pd.DataFrame, items: list) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        info = pd.DataFrame([("Report", "Logistics Performance"), ("Period", f.period.short()),
                             ("Compared with", f.compare.short() if f.compare else "None"),
                             ("Markets", ", ".join(L.name(c) for c in ctry) if ctry else "All"),
                             ("Data refreshed", ds.loaded_at)], columns=["Item", "Value"])
        info.to_excel(xw, sheet_name="Summary", index=False)
        d = cmp_df.copy()
        d = pd.DataFrame({"KPI": d["KPI"], "Current": [fmt(k, v) for k, v in zip(d["key"], d["current"])],
                          "Target": [fmt(k, v) for k, v in zip(d["key"], d["target"])],
                          "Previous": [fmt(k, v) for k, v in zip(d["key"], d["previous"])],
                          "Change": [fmt_delta(k, v) for k, v in zip(d["key"], d["change"])],
                          "Definition": [ALL_KPIS[k].definition for k in d["key"]]})
        d.to_excel(xw, sheet_name="Summary", index=False, startrow=len(info) + 2)
        m = _market_table(bc)
        m.to_excel(xw, sheet_name="Markets", index=False)
        pd.DataFrame([i.as_row() for i in items]).to_excel(xw, sheet_name="Insights", index=False)
        days = L.series(ds, f.period.start, f.period.end, "D", ctry)
        if not days.empty:
            out = pd.DataFrame({"Date": days["period"].dt.date, "Orders": days["l_orders"], "Shipped": days["l_shipped"],
                                "Delivered": days["l_delivered"], "Returned": days["l_returned"],
                                "In transit": days["l_transit"], "Cancelled": days["l_cancelled"],
                                "Delivery rate %": days["l_delivery"] * 100, "On-time %": days["l_ontime"] * 100,
                                "Avg delivery days": days["l_dlv_days"], "Order to ship days": days["l_lead_days"]})
            out.to_excel(xw, sheet_name="Daily", index=False)
        for ws in xw.sheets.values():
            ws.set_column(0, 0, 26)
            ws.set_column(1, 12, 16)
    return buf.getvalue()


def _market_table(bc: pd.DataFrame) -> pd.DataFrame:
    if bc.empty:
        return pd.DataFrame()
    return pd.DataFrame({
        "Market": bc["market"], "Orders": bc["l_orders"], "Shipped": bc["l_shipped"], "Delivered": bc["l_delivered"],
        "Returned": bc["l_returned"], "In transit": bc["l_transit"],
        "Delivery rate %": bc["l_delivery"] * 100, "On-time %": bc["l_ontime"] * 100,
        "Return rate %": bc["l_return_rate"] * 100, "Cancellation rate %": bc["l_cancel_rate"] * 100,
        "Avg delivery days": bc["l_dlv_days"], "Window (days)": bc["window"],
        "Within window": bc["within"].map({True: "● Yes", False: "▲ No"}).fillna("–"),
        "Order to ship days": bc["l_lead_days"], "Delivered value USD": bc["l_delivered_value"]})


# ------------------------------------------------------------------------------------------------ pages
def performance() -> None:
    ds, f, ctry = _header("Logistics Performance", "Team score of the bonus calculator, delivery operations and the "
                                                   "issues that need attention.")
    if not L.has_data(ds):
        return
    cur, prev = f.period, f.compare
    pl = prev.short() if prev else ""
    T = L.targets()
    tc = L.totals(ds, cur, ctry)
    tp = L.totals(ds, prev, ctry) if prev else {}
    if not tc or not tc["orders"]:
        C.note("No orders in the selected period.")
        return

    # ---- scorecard
    left, *rest = st.columns([1.5, 1, 1, 1], gap="small")
    s = L.scorecard(ds, cur)
    sp = L.scorecard(ds, prev) if prev and prev.scored else {}
    with left:
        if not cur.scored:
            C.hero_score(np.nan, T["l_score"], None, "", "", label="Logistics KPI score",
                         unavailable="The score is defined per month and quarter. Select a month or quarter to see it.")
        else:
            hit = sum(s["hit"].values())
            C.hero_score(s["l_score"], T["l_score"], sp.get("l_score") if sp else None, pl,
                         f"{hit} of 3 targets hit" + (" · all markets" if ctry else ""), label="Logistics KPI score")
    src = s if not ctry else tc
    cards = [dict(key="l_delivery", value=src.get("l_delivery"), target=T["l_delivery"],
                  prev=(sp if not ctry and sp else tp).get("l_delivery") if prev else None, prev_label=pl,
                  note_txt=f"{s['pts']['delivery']:.1f} of 40 pts" if cur.scored and not ctry else ""),
             dict(key="l_ontime", value=src.get("l_ontime"), target=T["l_ontime"],
                  prev=(sp if not ctry and sp else tp).get("l_ontime") if prev else None, prev_label=pl,
                  note_txt=f"{s['pts']['ontime']:.1f} of 40 pts" if cur.scored and not ctry else ""),
             dict(key="l_markets", value=s.get("l_markets"), target=T["l_markets"],
                  prev=sp.get("l_markets") if sp else None, prev_label=pl,
                  note_txt=f"{s['pts']['markets']:.1f} of 20 pts" if cur.scored else "",
                  unavailable="" if not ctry else "Team measure over all 5 markets")]
    for col, it in zip(rest, cards):
        with col:
            C.kpi_card(**it)
    if ctry and cur.scored:
        st.caption("The KPI score is a team measure over all markets (as in the bonus calculator); the market filter "
                   "applies to the other figures on this page.")
    st.write("")
    C.kpi_grid([dict(key=k, value=tc.get(k), prev=tp.get(k) if prev else None, prev_label=pl) for k in OPS_KEYS], cols=5)

    # ---- insights
    items = insights(ds, cur, prev, ctry)
    a, b = st.columns([1.6, 1], gap="medium")
    with a:
        C.section("What needs management attention", "Ranked by severity and size of the gap.")
        C.insight_cards([i for i in items if i.severity in ("critical", "warning")], limit=5,
                        empty="No logistics KPI is below target for the current selection.")
    with b:
        C.section("Positive developments")
        C.insight_cards([i for i in items if i.severity == "positive"], limit=4,
                        empty="No significant improvement in this period.")
        info = [i for i in items if i.severity == "info"]
        if info:
            C.insight_cards(info)

    # ---- direction of travel
    C.section("Direction of travel", "Monthly results; dashed line = target.")
    f_from, f_to = L.data_range(ds)
    months = [p for p in P.available("Month", f_from, f_to) if p.start <= cur.end][:12][::-1]
    hist = L.month_scores(ds, months)
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        if not hist.empty:
            st.plotly_chart(CH.trend_line(hist, "period", "l_score", "Logistics KPI score by month", T["l_score"]),
                            use_container_width=True, config=PLOT_CFG)
    with c2:
        cmp_df = compare_table(ds, cur, prev, ctry)
        if prev:
            st.plotly_chart(CH.change_bars(cmp_df[cmp_df["key"] != "l_markets"], f"Change vs {pl} (green = better, red = worse)"),
                            use_container_width=True, config=PLOT_CFG)
        elif not hist.empty:
            st.plotly_chart(CH.trend_line(hist, "period", "l_delivery", "Delivery rate by month", T["l_delivery"]),
                            use_container_width=True, config=PLOT_CFG)

    # ---- score composition and KPI table
    if cur.scored and not ctry:
        C.section("Score composition", "Points earned against the bonus-calculator scale.")
        comp = pd.DataFrame([
            {"KPI": "Delivery rate", "Actual": fmt("l_delivery", s["l_delivery"]), "0 points at": "85%",
             "Full points at": "95%", "Points": f"{s['pts']['delivery']:.1f} / 40", "Target hit": "● Yes" if s["hit"]["delivery"] else "▲ No"},
            {"KPI": "On-time delivery", "Actual": fmt("l_ontime", s["l_ontime"]), "0 points at": "85%",
             "Full points at": "95%", "Points": f"{s['pts']['ontime']:.1f} / 40", "Target hit": "● Yes" if s["hit"]["ontime"] else "▲ No"},
            {"KPI": "Markets within window", "Actual": f"{int(round(s['l_markets'] * 5))} of 5", "0 points at": "60%",
             "Full points at": "100%", "Points": f"{s['pts']['markets']:.1f} / 20", "Target hit": "● Yes" if s["hit"]["markets"] else "▲ No"},
            {"KPI": "CSAT", "Actual": "Not measured", "0 points at": "–", "Full points at": "–", "Points": "0 / 0",
             "Target hit": "–"},
            {"KPI": "Packaging quality & time", "Actual": "Not measured", "0 points at": "–", "Full points at": "–",
             "Points": "0 / 0", "Target hit": "–"},
            {"KPI": "Total", "Actual": "", "0 points at": "", "Full points at": "", "Points": f"{s['l_score']:.1f} / 100",
             "Target hit": "● Yes" if s["l_score"] >= s["target"] else "▲ No"}])
        st.dataframe(C.style_status(comp, ["Target hit"]), hide_index=True, use_container_width=True)

    C.section("KPI summary")
    show = pd.DataFrame({"KPI": cmp_df["KPI"],
                         "Actual": [fmt(k, v) for k, v in zip(cmp_df["key"], cmp_df["current"])],
                         "Target": [fmt(k, v) for k, v in zip(cmp_df["key"], cmp_df["target"])],
                         "Status": [C.met_text(target_met(k, v, t)) if not is_missing(t) else "–"
                                    for k, v, t in zip(cmp_df["key"], cmp_df["current"], cmp_df["target"])],
                         (pl or "Previous"): [fmt(k, v) for k, v in zip(cmp_df["key"], cmp_df["previous"])],
                         "Change": [fmt_delta(k, v) for k, v in zip(cmp_df["key"], cmp_df["change"])],
                         "Trend": [C.trend_text(t) for t in cmp_df["trend"]]})
    st.dataframe(C.style_status(show, ["Status", "Trend"]), hide_index=True, use_container_width=True)

    bc = L.by_country(ds, cur, ctry)
    st.download_button("Download this report as Excel", _excel(ds, f, ctry or [], cmp_df, bc, items),
                       file_name=f"Logistics_{cur.label.replace(' ', '_')}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def markets() -> None:
    ds, f, ctry = _header("Markets", "Delivery performance by market against the delivery windows.")
    if not L.has_data(ds):
        return
    cur, prev = f.period, f.compare
    T = L.targets()
    bc = L.by_country(ds, cur, ctry)
    bc = bc[bc["l_orders"] > 0]
    if bc.empty:
        C.note("No orders in the selected period.")
        return
    tc = L.totals(ds, cur, ctry)
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.plotly_chart(CH.actual_vs_target_bars(bc[bc["shipped"] > 0], "market", "l_delivery", "Delivery rate by market",
                                                 T["l_delivery"], tc.get("l_delivery")), use_container_width=True, config=PLOT_CFG)
    with c2:
        st.plotly_chart(CH.actual_vs_target_bars(bc[bc["eligible"] > 0], "market", "l_ontime", "On-time delivery by market",
                                                 T["l_ontime"], tc.get("l_ontime")), use_container_width=True, config=PLOT_CFG)
    C.section("Delivery time against the market window", "Average days from shipping to delivery; ● within window, "
              "▲ outside. Iraq has no agreed window.")
    win = bc[bc["window"].notna()]
    if not win.empty:
        import plotly.graph_objects as go
        import theme as TH
        fig = go.Figure()
        fig.add_trace(go.Bar(x=win["market"], y=win["window"], name="Window (days)",
                             marker=dict(color="#EEF1F5", cornerradius=4)))
        fig.add_trace(go.Bar(x=win["market"], y=win["l_dlv_days"], name="Average delivery days",
                             marker=dict(color=[TH.PRIMARY_SERIES if w else TH.SERIES[1] for w in win["within"]], cornerradius=4),
                             text=[f"{v:.1f} d" if not is_missing(v) else "—" for v in win["l_dlv_days"]],
                             textposition="outside", cliponaxis=False))
        fig.update_layout(barmode="overlay")
        st.plotly_chart(CH.base(fig, "Average delivery days vs window", 320, legend=True), use_container_width=True,
                        config=PLOT_CFG)
    C.section("Market table")
    st.dataframe(C.style_status(_market_table(bc), ["Within window"]), hide_index=True, use_container_width=True,
                 column_config={c: st.column_config.NumberColumn(c, format="%.1f") for c in
                                ["Delivery rate %", "On-time %", "Return rate %", "Cancellation rate %"]} |
                               {"Avg delivery days": st.column_config.NumberColumn(format="%.2f"),
                                "Order to ship days": st.column_config.NumberColumn(format="%.2f"),
                                "Delivered value USD": st.column_config.NumberColumn(format="%,.0f")})
    if prev:
        bp = L.by_country(ds, prev, ctry)
        m = bc[["market", "l_delivery", "l_ontime", "l_dlv_days"]].merge(
            bp[["market", "l_delivery", "l_ontime", "l_dlv_days"]], on="market", how="left", suffixes=("_cur", "_prev"))
        C.section(f"Change vs {prev.short()}")
        c1, c2 = st.columns(2, gap="medium")
        with c1:
            st.plotly_chart(CH.two_period_bars(m, "market", "l_delivery_cur", "l_delivery_prev", "l_delivery",
                                               f.period.short(), prev.short(), "Delivery rate (%)"),
                            use_container_width=True, config=PLOT_CFG)
        with c2:
            st.plotly_chart(CH.two_period_bars(m, "market", "l_ontime_cur", "l_ontime_prev", "l_ontime",
                                               f.period.short(), prev.short(), "On-time delivery (%)"),
                            use_container_width=True, config=PLOT_CFG)


def trends() -> None:
    ds, f, ctry = _header("Trends", "Daily, weekly or monthly evolution of volumes, rates and delivery times.")
    if not L.has_data(ds):
        return
    T = L.targets()
    cur = f.period
    grain = st.radio("Show by", ["Day", "Week", "Month"], horizontal=True, key="l_grain",
                     index=0 if cur.days <= 45 else (1 if cur.days <= 190 else 2))
    freq = {"Day": "D", "Week": "W", "Month": "M"}[grain]
    start = cur.start if grain == "Day" else (cur.start - pd.Timedelta(days=cur.start.weekday()) if grain == "Week"
                                              else cur.start.replace(day=1))
    d = L.series(ds, start, cur.end, freq, ctry)
    if d.empty:
        C.note("No orders in the selected period.")
        return
    d["label"] = d["period"].dt.strftime({"D": "%d %b", "W": "W/c %d %b", "M": "%b %Y"}[freq])
    cov = L.coverage(ds, cur)
    if not cov["mature"]:
        C.note(f"{C.esc(cov['maturity_note'])}. The latest points will rise as deliveries are confirmed.")
    st.plotly_chart(CH.simple_bars(d, "label", "l_orders", f"Orders per {grain.lower()}", "Orders"),
                    use_container_width=True, config=PLOT_CFG)
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        st.plotly_chart(CH.trend_line(d, "label", "l_delivery", "Delivery rate", T["l_delivery"]),
                        use_container_width=True, config=PLOT_CFG)
        st.plotly_chart(CH.trend_line(d, "label", "l_return_rate", "Return rate"), use_container_width=True,
                        config=PLOT_CFG)
        st.plotly_chart(CH.trend_line(d, "label", "l_lead_days", "Order to ship time (days)"), use_container_width=True,
                        config=PLOT_CFG)
    with c2:
        st.plotly_chart(CH.trend_line(d, "label", "l_ontime", "On-time delivery", T["l_ontime"]),
                        use_container_width=True, config=PLOT_CFG)
        st.plotly_chart(CH.trend_line(d, "label", "l_cancel_rate", "Cancellation rate"), use_container_width=True,
                        config=PLOT_CFG)
        st.plotly_chart(CH.trend_line(d, "label", "l_dlv_days", "Average delivery time (days)"), use_container_width=True,
                        config=PLOT_CFG)


def page() -> None:          # kept for backward compatibility
    performance()
