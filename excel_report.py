"""Management-ready Excel report built from the current filters, using the same calculations as the dashboard."""
from __future__ import annotations

import io
from datetime import datetime

import numpy as np
import pandas as pd
import xlsxwriter

import analytics as an
import comparison as cmp
import insights as ins
from config import COMPANY
from kpis import ALL_KPIS, OPS_KPIS, achievement, gap, is_missing, target_met, trend
import theme as TH

SECTIONS = ["Executive Summary", "KPI Performance", "Period Comparison", "Team Performance",
            "Individual Performance", "Detailed Data", "Insights & Actions"]
LOGI_SECTIONS = ["Logistics Summary", "Logistics Markets", "Logistics Trend", "Logistics Insights"]

NUMFMT = {"pct": "0.0%", "ratio": "0%", "min": "0.0", "hrs": "0.0", "sec": "#,##0", "days": "0.00", "count": "#,##0",
          "pts": "0.0", "num": "0.0"}


class Book:
    def __init__(self):
        self.buf = io.BytesIO()
        self.wb = xlsxwriter.Workbook(self.buf, {"in_memory": True, "nan_inf_to_errors": True})
        wb = self.wb
        base = {"font_name": "Calibri", "font_size": 10, "valign": "vcenter"}
        self.f = {
            "title": wb.add_format({**base, "font_size": 18, "bold": True, "font_color": TH.NAVY}),
            "subtitle": wb.add_format({**base, "font_size": 11, "font_color": TH.INK_2}),
            "eyebrow": wb.add_format({**base, "font_size": 9, "bold": True, "font_color": TH.GOLD}),
            "band": wb.add_format({**base, "bg_color": TH.NAVY}),
            "section": wb.add_format({**base, "font_size": 12, "bold": True, "font_color": TH.NAVY, "bottom": 2,
                                      "bottom_color": TH.GOLD}),
            "label": wb.add_format({**base, "bold": True, "font_color": TH.INK_2}),
            "text": wb.add_format({**base, "font_color": TH.INK, "text_wrap": True, "valign": "top"}),
            "muted": wb.add_format({**base, "font_color": TH.MUTED, "italic": True, "text_wrap": True, "valign": "top"}),
            "th": wb.add_format({**base, "bold": True, "font_color": "#FFFFFF", "bg_color": TH.NAVY, "border": 1,
                                 "border_color": TH.NAVY, "text_wrap": True, "align": "center"}),
            "th_left": wb.add_format({**base, "bold": True, "font_color": "#FFFFFF", "bg_color": TH.NAVY, "border": 1,
                                      "border_color": TH.NAVY, "text_wrap": True}),
            "cell": wb.add_format({**base, "border": 1, "border_color": TH.LINE}),
            "cell_wrap": wb.add_format({**base, "border": 1, "border_color": TH.LINE, "text_wrap": True, "valign": "top"}),
            "cell_b": wb.add_format({**base, "border": 1, "border_color": TH.LINE, "bold": True}),
            "good": wb.add_format({**base, "border": 1, "border_color": TH.LINE, "font_color": TH.GOOD_TEXT, "bold": True,
                                   "bg_color": "#E8F6E8"}),
            "bad": wb.add_format({**base, "border": 1, "border_color": TH.LINE, "font_color": "#A12B2B", "bold": True,
                                  "bg_color": "#FBEAEA"}),
            "neutral": wb.add_format({**base, "border": 1, "border_color": TH.LINE, "font_color": TH.MUTED}),
            "big": wb.add_format({**base, "font_size": 26, "bold": True, "font_color": TH.NAVY}),
            "big_lbl": wb.add_format({**base, "font_size": 9, "font_color": TH.MUTED}),
        }
        self._num = {}

    def num(self, unit: str, bold=False):
        key = (unit, bold)
        if key not in self._num:
            self._num[key] = self.wb.add_format({"font_name": "Calibri", "font_size": 10, "border": 1,
                                                 "border_color": TH.LINE, "num_format": NUMFMT.get(unit, "0.0"),
                                                 "bold": bold, "valign": "vcenter"})
        return self._num[key]

    def pp(self):
        if "pp" not in self._num:
            self._num["pp"] = self.wb.add_format({"font_name": "Calibri", "font_size": 10, "border": 1,
                                                  "border_color": TH.LINE, "valign": "vcenter",
                                                  "num_format": '+0.0" pp";-0.0" pp";0.0" pp"'})
        return self._num["pp"]

    def sheet(self, name: str, widths: dict, landscape=True):
        ws = self.wb.add_worksheet(name[:31])
        ws.hide_gridlines(2)
        ws.set_zoom(90)
        if landscape:
            ws.set_landscape()
        ws.fit_to_pages(1, 0)
        ws.set_paper(9)
        ws.set_margins(0.4, 0.4, 0.5, 0.5)
        for col, w in widths.items():
            ws.set_column(col, col, w)
        return ws

    def heading(self, ws, title: str, meta: str, cols: int = 10):
        ws.set_row(0, 6)
        for c in range(cols):
            ws.write_blank(0, c, None, self.f["band"])
        ws.write(1, 0, COMPANY.upper() + " · OPERATIONS", self.f["eyebrow"])
        ws.write(2, 0, title, self.f["title"])
        ws.set_row(2, 26)
        ws.write(3, 0, meta, self.f["subtitle"])
        ws.set_header(f"&L&8{COMPANY} – {title}&R&8Confidential – internal use")
        ws.set_footer("&L&8Prepared by Operations&R&8Page &P of &N")
        return 5

    def table(self, ws, row: int, col: int, df: pd.DataFrame, units: dict | None = None, status_cols=(),
              trend_cols=(), wrap_cols=(), first_bold=True, autofilter=False) -> int:
        units = units or {}
        for j, h in enumerate(df.columns):
            ws.write(row, col + j, h, self.f["th_left"] if j == 0 else self.f["th"])
        ws.set_row(row, 30)
        for i, (_, r) in enumerate(df.iterrows()):
            for j, h in enumerate(df.columns):
                v = r[h]
                cell = (row + 1 + i, col + j)
                if h in status_cols or h in trend_cols:
                    s = str(v)
                    fm = self.f["good"] if (s.startswith("On target") or s.startswith("Improved") or s.startswith("Yes")) \
                        else self.f["bad"] if (s.startswith("Below") or s.startswith("Declined") or s == "No") \
                        else self.f["neutral"]
                    ws.write(*cell, s, fm)
                elif h in units and not isinstance(v, str):
                    if is_missing(v):
                        ws.write(*cell, "—", self.f["neutral"])
                    else:
                        ws.write_number(*cell, float(v), self.num(units[h], bold=(j == 0)))
                elif isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool):
                    if is_missing(v):
                        ws.write(*cell, "—", self.f["neutral"])
                    else:
                        ws.write_number(*cell, float(v), self.num("num"))
                else:
                    ws.write(*cell, "" if v is None else str(v),
                             self.f["cell_wrap"] if h in wrap_cols else (self.f["cell_b"] if (j == 0 and first_bold) else self.f["cell"]))
        if autofilter and len(df):
            ws.autofilter(row, col, row + len(df), col + len(df.columns) - 1)
        return row + len(df) + 2

    def close(self) -> bytes:
        self.wb.close()
        return self.buf.getvalue()


def _status(k, v, t, night=False) -> str:
    if night and k == "calls":
        return "Night shift"
    m = target_met(k, v, t)
    return "No data" if m is None else ("On target" if m else "Below target")


def _trend_word(t: str) -> str:
    return {"improved": "Improved", "declined": "Declined", "stable": "Stable", "up": "Higher", "down": "Lower"}.get(t, "–")


def _valid_keys(ds, p):
    cov = an.coverage(ds, p)
    keys = cmp.kpi_keys_for(p, p)
    if not cov.get("schedule_ok", True):
        keys = [k for k in keys if k not in an.SCHEDULE_KPIS]
    return keys


def build(ds, f, sections: list | None = None, agent: str | None = None, logi_sections: list | None = None) -> bytes:
    """CS sheets (sections) and/or Logistics sheets (logi_sections), one workbook."""
    sections = SECTIONS if sections is None else sections
    logi_sections = logi_sections or []
    cur, prev = f.period, f.compare
    if prev is None and "Period Comparison" in sections:
        sections = [s for s in sections if s != "Period Comparison"]
    B = Book()
    T = cmp.targets(ds)
    tc = an.team(ds, cur, f.agents)
    tp = an.team(ds, prev, f.agents) if prev else {}
    cov = an.coverage(ds, cur)
    keys = _valid_keys(ds, cur)
    A = an.scorecard(ds, cur)
    if f.agents and not A.empty:
        A = A[A["agent"].isin(f.agents)]
    items = ins.generate(ds, cur, prev or cur, f.agents)
    scope = "; ".join(f"{k}: {v}" for k, v in f.as_dict().items())
    meta = f"{cur.short() if cur.kind != 'Month' else cur.start.strftime('%B %Y')}" + \
           (f" compared with {prev.short()}" if prev else "") + f"  |  Data to {ds.coverage['chats_to']:%d %b %Y}"
    notes = [cov[k] for k in ("note", "schedule_note") if cov.get(k)]

    # ------------------------------------------------------------------------------------------ Executive summary
    if "Executive Summary" in sections:
        ws = B.sheet("Executive Summary", {0: 30, 1: 14, 2: 14, 3: 14, 4: 14, 5: 14, 6: 16, 7: 16})
        r = B.heading(ws, "Customer Support Performance Report", meta, 8)
        ws.write(r, 0, "Scope", B.f["label"])
        ws.merge_range(r, 1, r, 7, scope, B.f["text"])
        r += 1
        ws.write(r, 0, "Prepared", B.f["label"])
        ws.write(r, 1, datetime.now().strftime("%d %b %Y"), B.f["text"])
        r += 2
        sc = tc.get("score")
        if cur.scored and not is_missing(sc):
            n_ok = int(A["score_target_met"].sum()) if not A.empty else 0
            ws.write(r, 0, "Team KPI score", B.f["big_lbl"])
            ws.write(r, 2, "Target", B.f["big_lbl"])
            ws.write(r, 4, "Agents on target", B.f["big_lbl"])
            if prev and not is_missing(tp.get("score")):
                ws.write(r, 6, f"vs {prev.short()}", B.f["big_lbl"])
            ws.write_number(r + 1, 0, round(sc, 1), B.wb.add_format({"font_size": 26, "bold": True, "num_format": "0.0",
                                                                    "font_color": TH.GOOD_TEXT if sc >= T["score"] else "#A12B2B"}))
            ws.write_number(r + 1, 2, T["score"], B.f["big"])
            ws.write(r + 1, 4, f"{n_ok} / {len(A)}", B.f["big"])
            if prev and not is_missing(tp.get("score")):
                ws.write(r + 1, 6, f"{sc - tp['score']:+.1f}", B.f["big"])
            ws.set_row(r + 1, 34)
            r += 3
        ws.write(r, 0, "Headline KPIs", B.f["section"])
        r += 1
        rows = []
        for k in keys:
            v, p_ = tc.get(k), tp.get(k, np.nan) if prev else np.nan
            rows.append({"KPI": ALL_KPIS[k].label, "Actual": v, "Target": T.get(k), "Achievement": achievement(k, v, T.get(k)),
                         "Previous": p_, "Change": (v - p_) if not (is_missing(v) or is_missing(p_)) else np.nan,
                         "Trend": _trend_word(trend(k, v, p_)), "Status": _status(k, v, T.get(k))})
        df = pd.DataFrame(rows)
        # per-row units: write manually to keep each KPI in its own format
        r = _kpi_rows(B, ws, r, df, keys)
        ws.write(r, 0, "Key findings", B.f["section"])
        r += 1
        top = [i for i in items if i.severity in ("critical", "warning")][:5] + [i for i in items if i.severity == "positive"][:3]
        for i in top:
            fm = B.f["bad"] if i.severity in ("critical", "warning") else B.f["good"]
            ws.write(r, 0, {"critical": "Priority", "warning": "Attention", "positive": "Positive"}.get(i.severity, "Note"), fm)
            ws.merge_range(r, 1, r, 7, f"{i.title}. {i.what}" + (f" Action: {i.action}" if i.action else ""), B.f["cell_wrap"])
            ws.set_row(r, 15 * max(2, min(6, len(i.what + i.action) // 95 + 1)))
            r += 1
        if notes:
            r += 1
            ws.write(r, 0, "Data notes", B.f["section"])
            r += 1
            for n in notes:
                ws.merge_range(r, 0, r, 7, n, B.f["muted"])
                ws.set_row(r, 28)
                r += 1

    # ------------------------------------------------------------------------------------------ KPI performance
    if "KPI Performance" in sections:
        ws = B.sheet("KPI Performance", {0: 26, 1: 12, 2: 12, 3: 12, 4: 12, 5: 12, 6: 12, 7: 13, 8: 70})
        r = B.heading(ws, "KPI Performance", meta, 10)
        ws.write(r, 0, "Scorecard KPIs (team result, approved formulas)", B.f["section"])
        r += 1
        rows = []
        for k in keys:
            v, p_ = tc.get(k), tp.get(k, np.nan) if prev else np.nan
            rows.append({"KPI": ALL_KPIS[k].label, "Actual": v, "Target": T.get(k), "Achievement": achievement(k, v, T.get(k)),
                         "Previous": p_, "Change": (v - p_) if not (is_missing(v) or is_missing(p_)) else np.nan,
                         "Trend": _trend_word(trend(k, v, p_)), "Status": _status(k, v, T.get(k)),
                         "Definition": ALL_KPIS[k].definition})
        start = r
        r = _kpi_rows(B, ws, r, pd.DataFrame(rows), keys, definition=True)
        ach = [(ALL_KPIS[k].label, achievement(k, tc.get(k), T.get(k))) for k in keys if k != "fcr" or True]
        ach = [(l, a) for l, a in ach if not is_missing(a)]
        if ach:
            cs = r + 1
            ws.write(cs - 1, 11, "Chart data", B.f["muted"])
            for i, (l, a) in enumerate(ach):
                ws.write(cs + i, 11, l)
                ws.write_number(cs + i, 12, min(a, 2.0))
                ws.write_number(cs + i, 13, 1.0)
            ch = B.wb.add_chart({"type": "bar"})
            ch.add_series({"name": "Achievement of target", "categories": ["KPI Performance", cs, 11, cs + len(ach) - 1, 11],
                           "values": ["KPI Performance", cs, 12, cs + len(ach) - 1, 12],
                           "fill": {"color": TH.PRIMARY_SERIES}, "gap": 80,
                           "data_labels": {"value": True, "num_format": "0%"}})
            ch.set_title({"name": "Achievement of target by KPI (100% = on target, capped at 200%)", "name_font": {"size": 11}})
            ch.set_x_axis({"num_format": "0%", "major_gridlines": {"visible": True, "line": {"color": "#E2E8F0"}}})
            ch.set_y_axis({"reverse": True})
            ch.set_legend({"none": True})
            ch.set_size({"width": 720, "height": 320})
            ws.insert_chart(r, 0, ch)
            ws.set_column(11, 13, None, None, {"hidden": True})
            r += 18
        ws.write(r, 0, "Operational metrics (CS Pulse definitions, no targets)", B.f["section"])
        r += 1
        oc, op = an.ops(ds, cur, f.agents), an.ops(ds, prev, f.agents) if prev else {}
        orows = [{"KPI": OPS_KPIS[k].label, "Actual": oc.get(k), "Target": np.nan, "Achievement": np.nan,
                  "Previous": op.get(k, np.nan) if prev else np.nan,
                  "Change": (oc.get(k) - op.get(k)) if prev and not (is_missing(oc.get(k)) or is_missing(op.get(k))) else np.nan,
                  "Trend": _trend_word(trend(k, oc.get(k), op.get(k, np.nan) if prev else np.nan)), "Status": "",
                  "Definition": OPS_KPIS[k].definition} for k in OPS_KPIS]
        r = _kpi_rows(B, ws, r, pd.DataFrame(orows), list(OPS_KPIS), definition=True)
        # monthly history
        f_from, f_to = an.data_range(ds)
        import periods as P
        months = [p for p in P.available("Month", f_from, f_to) if p.start <= cur.end][:12][::-1]
        H = an.month_series(ds, months, f.agents)
        if len(H):
            ws.write(r, 0, "Monthly history (team)", B.f["section"])
            r += 1
            hk = ["score", "quality", "chats", "calls", "reply", "absence", "fcr", "answer_rate", "adherence"]
            hdf = pd.DataFrame({"Month": H["period"], **{ALL_KPIS[k].label: H[k] for k in hk}})
            r0 = r
            r = B.table(ws, r, 0, hdf, units={ALL_KPIS[k].label: ALL_KPIS[k].unit for k in hk})
            if H["score"].notna().sum() >= 2:
                ch = B.wb.add_chart({"type": "line"})
                ch.add_series({"name": "Team KPI score", "categories": ["KPI Performance", r0 + 1, 0, r0 + len(hdf), 0],
                               "values": ["KPI Performance", r0 + 1, 1, r0 + len(hdf), 1],
                               "line": {"color": TH.PRIMARY_SERIES, "width": 2.25},
                               "marker": {"type": "circle", "size": 6, "fill": {"color": TH.PRIMARY_SERIES}}})
                ch.set_title({"name": f"Team KPI score by month (target {T['score']:.0f})", "name_font": {"size": 11}})
                ch.set_legend({"none": True})
                ch.set_y_axis({"major_gridlines": {"visible": True, "line": {"color": "#E2E8F0"}}})
                ch.set_size({"width": 720, "height": 280})
                ws.insert_chart(r, 0, ch)
                r += 16
        ws.freeze_panes(6, 1)

    # ------------------------------------------------------------------------------------------ comparison
    if "Period Comparison" in sections and prev:
        ws = B.sheet("Period Comparison", {0: 26, 1: 14, 2: 14, 3: 13, 4: 12, 5: 13, 6: 15, 7: 15, 8: 13})
        r = B.heading(ws, "Period Comparison", f"{cur.short()} compared with {prev.short()}", 9)
        for w in cmp.warnings(ds, cur, prev):
            ws.merge_range(r, 0, r, 8, "Note: " + w, B.f["muted"])
            r += 1
        r += 1
        tcmp = cmp.compare_team(ds, cur, prev, f.agents)
        ws.write(r, 0, "Team KPIs", B.f["section"])
        r += 1
        hdr = ["KPI", cur.short(), prev.short(), "Change", "% change", "Target", f"Status {cur.short()}",
               f"Status {prev.short()}", "Trend"]
        for j, h in enumerate(hdr):
            ws.write(r, j, h, B.f["th_left"] if j == 0 else B.f["th"])
        ws.set_row(r, 30)
        for _, x in tcmp.iterrows():
            r += 1
            u = ALL_KPIS[x["key"]].unit
            ws.write(r, 0, x["KPI"], B.f["cell_b"])
            for j, v in ((1, x["current"]), (2, x["previous"]), (3, x["change"]), (5, x["target"])):
                if is_missing(v):
                    ws.write(r, j, "—", B.f["neutral"])
                elif j == 3 and u in ("pct", "ratio"):
                    ws.write_number(r, j, float(v) * 100, B.pp())
                else:
                    ws.write_number(r, j, float(v), B.num(u))
            ws.write(r, 4, "—" if is_missing(x["change_pct"]) else x["change_pct"], B.num("pct") if not is_missing(x["change_pct"]) else B.f["neutral"])
            for j, m in ((6, x["met_current"]), (7, x["met_previous"])):
                s = "" if m is None else ("On target" if m else "Below target")
                ws.write(r, j, s, B.f["good"] if s == "On target" else B.f["bad"] if s else B.f["neutral"])
            t = _trend_word(x["trend"])
            ws.write(r, 8, t, B.f["good"] if t == "Improved" else B.f["bad"] if t == "Declined" else B.f["neutral"])
        r += 3
        ac = cmp.compare_agents(ds, cur, prev, f.agents)
        if not ac.empty:
            ws.write(r, 0, "Agents", B.f["section"])
            r += 1
            akeys = [k for k in ["score", "chats", "reply", "fcr", "quality", "calls"] if f"{k}_cur" in ac]
            cols = {"Agent": ac["agent"]}
            units = {}
            for k in akeys:
                lab = ALL_KPIS[k].label
                cols[f"{lab} {cur.short()}"] = ac[f"{k}_cur"]
                cols[f"{lab} {prev.short()}"] = ac[f"{k}_prev"]
                cols[f"{lab} trend"] = [_trend_word(t) for t in ac[f"{k}_trend"]]
                units[f"{lab} {cur.short()}"] = units[f"{lab} {prev.short()}"] = ALL_KPIS[k].unit
            if "rank_chg" in ac:
                ok = ac["comparable_now"] & ac["comparable_before"]
                cols["Rank now"] = [x if o else np.nan for x, o in zip(ac["rank_cur"], ok)]
                cols["Rank before"] = [x if o else np.nan for x, o in zip(ac["rank_prev"], ok)]
                units["Rank now"] = units["Rank before"] = "count"
            adf = pd.DataFrame(cols)
            ws.set_column(1, len(adf.columns), 12)
            r = B.table(ws, r, 0, adf, units=units, trend_cols=[c for c in adf.columns if c.endswith("trend")])
        ws.freeze_panes(6, 1)

    # ------------------------------------------------------------------------------------------ team / groups
    if "Team Performance" in sections:
        groups = an.agent_groups(ds, cur)
        if groups:
            ws = B.sheet("Team Performance", {0: 26, 1: 16, 2: 16, 3: 16, 4: 16, 5: 16})
            r = B.heading(ws, "Team Performance by Group", meta, 6)
            ws.merge_range(r, 0, r, 5, "Groups follow the scorecard night-shift rule (at least half of working days on "
                           "the 12 AM – 9 AM shift). Group results use the same team formulas.", B.f["muted"])
            r += 2
            gn = ["All agents"] + sorted(groups)
            hdr = ["KPI", "Target"] + gn
            for j, h in enumerate(hdr):
                ws.write(r, j, h, B.f["th_left"] if j == 0 else B.f["th"])
            for k in keys:
                r += 1
                u = ALL_KPIS[k].unit
                ws.write(r, 0, ALL_KPIS[k].label, B.f["cell_b"])
                ws.write_number(r, 1, T[k], B.num(u)) if k in T else ws.write(r, 1, "—", B.f["neutral"])
                for j, g in enumerate(gn):
                    t = an.team(ds, cur) if g == "All agents" else an.team(ds, cur, groups[g])
                    v = t.get(k)
                    m = target_met(k, v, T.get(k))
                    if is_missing(v):
                        ws.write(r, 2 + j, "—", B.f["neutral"])
                    else:
                        fmt_ = B.wb.add_format({"num_format": NUMFMT.get(u, "0.0"), "border": 1, "border_color": TH.LINE,
                                                "font_color": TH.GOOD_TEXT if m else ("#A12B2B" if m is False else TH.INK),
                                                "font_size": 10})
                        ws.write_number(r, 2 + j, float(v), fmt_)
            r += 3
            Aall = an.scorecard(ds, cur)
            vol = Aall.groupby("group")[["working_days", "chats_closed", "inbound_calls", "sales_usd"]].sum()
            tot = vol.sum()
            vdf = pd.DataFrame({"Group": vol.index, "Working days": vol["working_days"].values,
                                "Customers closed": vol["chats_closed"].values,
                                "Share of customers closed": (vol["chats_closed"] / tot["chats_closed"]).values if tot["chats_closed"] else np.nan,
                                "Inbound calls": vol["inbound_calls"].values,
                                "Delivered sales (USD)": vol["sales_usd"].values})
            ws.write(r, 0, "Contribution to team volume", B.f["section"])
            r += 1
            r = B.table(ws, r, 0, vdf, units={"Working days": "count", "Customers closed": "count",
                                               "Share of customers closed": "pct", "Inbound calls": "count",
                                               "Delivered sales (USD)": "count"})

    # ------------------------------------------------------------------------------------------ individual
    if "Individual Performance" in sections and not A.empty:
        ws = B.sheet("Individual Performance", {0: 22, 1: 12})
        r = B.heading(ws, "Individual Performance", meta, 14)
        ikeys = [k for k in ["score", "quality", "chats", "calls", "sales", "reply", "absence", "fcr"] if k in keys or k == "sales"]
        cols = {"Agent": A["agent"], "Group": A["group"], "Working days": A["working_days"]}
        units = {"Working days": "count"}
        for k in ikeys:
            cols[ALL_KPIS[k].label] = A[k]
            units[ALL_KPIS[k].label] = ALL_KPIS[k].unit
        if "score" in ikeys:
            cols["Rank"] = [x if c else np.nan for x, c in zip(A["rank"], A["comparable"])]
            units["Rank"] = "count"
        cols["Targets hit"] = [f"{int(h)} of {int(c)}" for h, c in zip(A["targets_hit"], A["targets_counted"])]
        cols["Notes"] = [", ".join(x for x, fl in (("Limited working days", l), ("QA not entered", q)) if fl)
                         for l, q in zip(A["limited_data"], A["qa_missing"])]
        idf = pd.DataFrame(cols)
        if "KPI Score" in idf and idf["KPI Score"].notna().any():
            idf = idf.sort_values("KPI Score", ascending=False)
        ws.set_column(1, len(idf.columns), 12)
        ws.set_column(len(idf.columns) - 1, len(idf.columns) - 1, 30)
        r0 = r
        r = B.table(ws, r, 0, idf, units=units, autofilter=True)
        # conditional colouring vs target per KPI column
        for j, k in enumerate(ikeys):
            c = 3 + j
            t = T.get(k)
            if t is None or k == "sales" and False:
                continue
            crit_bad = "<" if ALL_KPIS[k].direction == "higher" else ">"
            ws.conditional_format(r0 + 1, c, r0 + len(idf), c, {"type": "cell", "criteria": crit_bad, "value": t,
                                                               "format": B.wb.add_format({"font_color": "#A12B2B", "bg_color": "#FBEAEA"})})
            ws.conditional_format(r0 + 1, c, r0 + len(idf), c, {"type": "cell",
                                                               "criteria": ">=" if crit_bad == "<" else "<=", "value": t,
                                                               "format": B.wb.add_format({"font_color": TH.GOOD_TEXT})})
        ws.write(r, 0, "Red = below target, green = on target. Rank is shown only for agents with comparable data "
                       "(enough working days and QA entered).", B.f["muted"])
        r += 2
        if agent and agent in set(A["agent"]):
            ar = A[A["agent"] == agent].iloc[0]
            ws.write(r, 0, f"Agent detail: {agent}", B.f["section"])
            r += 1
            Pm = an.scorecard(ds, prev) if prev else pd.DataFrame()
            pr = Pm[Pm["agent"] == agent].iloc[0] if (not Pm.empty and agent in set(Pm["agent"])) else None
            team_all = an.team(ds, cur)
            rows = []
            for k in ikeys:
                v = ar.get(k)
                p_ = pr.get(k) if pr is not None else np.nan
                rows.append({"KPI": ALL_KPIS[k].label, "Actual": v, "Target": T.get(k), "Team": team_all.get(k) if k != "sales" else np.nan,
                             "Previous": p_, "Change": (v - p_) if not (is_missing(v) or is_missing(p_)) else np.nan,
                             "Trend": _trend_word(trend(k, v, p_)), "Status": _status(k, v, T.get(k), bool(ar.get("night")))})
            r = _kpi_rows(B, ws, r, pd.DataFrame(rows), ikeys, team_col=True)
        ws.freeze_panes(r0 + 1, 1)

    # ------------------------------------------------------------------------------------------ detail
    if "Detailed Data" in sections:
        d = ds.daily
        m = (d["date"] >= cur.start) & (d["date"] <= cur.end) & d["agent"].isin(f.agents or ds.kpi_agents)
        dd = d[m].sort_values(["date", "agent"])
        if len(dd):
            ws = B.sheet("Detailed Data", {0: 12, 1: 20, 2: 14, 3: 16, 4: 11, 5: 12, 6: 12, 7: 12, 8: 12})
            r = B.heading(ws, "Detailed Data – agent days", meta, 9)
            ch = ds.chats
            cl = ch[ch["closed_by"].isin(f.agents or ds.kpi_agents) & (ch["resolved"] >= cur.start) &
                    (ch["resolved"] < cur.end + pd.Timedelta(days=1))]
            closed = cl.groupby([cl["closed_by"], cl["resolved"].dt.normalize()])["contact"].nunique()
            k = ds.calls
            kc = k[(k["type"] == "Inbound") & k["agent"].isin(f.agents or ds.kpi_agents) & (k["date"] >= cur.start) & (k["date"] <= cur.end)]
            calls = kc.groupby(["agent", "date"]).size()
            out = pd.DataFrame({
                "Date": dd["date"].dt.strftime("%Y-%m-%d"), "Agent": dd["agent"], "Shift": dd["shift"], "Day status": dd["status"],
                "Working day": dd["working"],
                "Customers closed": [closed.get((a, dt), 0) for a, dt in zip(dd["agent"], dd["date"])],
                "Inbound calls": [calls.get((a, dt), 0) for a, dt in zip(dd["agent"], dd["date"])],
                "Adherence": [n / dn if dn else np.nan for n, dn in zip(dd["Adherence Num"], dd["Adherence Den"])],
                "Occupancy": [n / dn if dn else np.nan for n, dn in zip(dd["Occupancy Num"], dd["Occupancy Den"])],
            })
            ws.write(r, 0, "Customers closed per day are unique customers per day; period totals in the other sheets "
                           "count each customer once per period, so daily values do not add up to them.", B.f["muted"])
            r += 2
            r0 = r
            B.table(ws, r, 0, out, units={"Working day": "count", "Customers closed": "count", "Inbound calls": "count",
                                          "Adherence": "pct", "Occupancy": "pct"}, first_bold=False, autofilter=True)
            ws.freeze_panes(r0 + 1, 2)

    # ------------------------------------------------------------------------------------------ insights
    if "Insights & Actions" in sections and items:
        ws = B.sheet("Insights & Actions", {0: 11, 1: 12, 2: 34, 3: 52, 4: 40, 5: 44, 6: 16})
        r = B.heading(ws, "Key Insights & Recommended Actions", meta, 7)
        idf = pd.DataFrame([i.as_row() for i in items])
        idf["Priority"] = idf["Priority"].replace({"Warning": "Attention", "Info": "Note"})
        r0 = r
        hdr = list(idf.columns)
        for j, h in enumerate(hdr):
            ws.write(r, j, h, B.f["th_left"] if j == 0 else B.f["th"])
        for _, x in idf.iterrows():
            r += 1
            pr = x["Priority"]
            ws.write(r, 0, pr, B.f["bad"] if pr in ("Critical", "Attention") else B.f["good"] if pr == "Positive" else B.f["neutral"])
            for j, h in enumerate(hdr[1:], start=1):
                ws.write(r, j, x[h], B.f["cell_wrap"])
            ws.set_row(r, 15 * max(2, min(8, max(len(str(x["What happened"])) // 60, len(str(x["Recommended action"])) // 50) + 1)))
        ws.freeze_panes(r0 + 1, 0)
        ws.autofilter(r0, 0, r, len(hdr) - 1)
    if logi_sections:
        _logistics(B, ds, f, logi_sections)
    return B.close()


def _kpi_rows(B: Book, ws, r: int, df: pd.DataFrame, keys: list, definition=False, team_col=False) -> int:
    """KPI table where each row uses its own KPI's number format."""
    hdr = list(df.columns)
    for j, h in enumerate(hdr):
        ws.write(r, j, h, B.f["th_left"] if j == 0 else B.f["th"])
    ws.set_row(r, 30)
    for i, (_, x) in enumerate(df.iterrows()):
        rr = r + 1 + i
        k = keys[i]
        u = ALL_KPIS[k].unit
        for j, h in enumerate(hdr):
            v = x[h]
            if j == 0:
                ws.write(rr, j, v, B.f["cell_b"])
            elif h in ("Trend", "Status"):
                s = str(v)
                fm = B.f["good"] if s in ("Improved", "On target") else B.f["bad"] if s in ("Declined", "Below target") else B.f["neutral"]
                ws.write(rr, j, s, fm)
            elif h == "Achievement":
                if is_missing(v):
                    ws.write(rr, j, "—", B.f["neutral"])
                elif v >= 2:
                    ws.write(rr, j, "≥200%", B.num("ratio"))
                else:
                    ws.write_number(rr, j, float(v), B.num("ratio"))
            elif h in ("Change", "Gap") and u in ("pct", "ratio") and not is_missing(v):
                ws.write_number(rr, j, float(v) * 100, B.pp())
            elif h == "Definition":
                ws.write(rr, j, v, B.f["cell_wrap"])
                ws.set_row(rr, 15 * max(2, len(str(v)) // 80 + 1))
            else:
                if is_missing(v):
                    ws.write(rr, j, "—", B.f["neutral"])
                else:
                    ws.write_number(rr, j, float(v), B.num(u))
    return r + len(df) + 2


# ------------------------------------------------------------------------------------------------ Logistics
def _logistics(B: Book, ds, f, sections: list) -> None:
    import logi as L
    import logistics as LP
    if not L.has_data(ds):
        ws = B.sheet("Logistics", {0: 90})
        B.heading(ws, "Logistics", "No logistics data available", 4)
        ws.write(5, 0, "The Logistics_Daily tab of the Orders sheet could not be read.", B.f["muted"])
        return
    cur, prev = f.period, f.compare
    T = L.targets()
    cov = L.coverage(ds, cur)
    _, l_to = L.data_range(ds)
    meta = (f"{cur.short() if cur.kind != 'Month' else cur.start.strftime('%B %Y')}"
            + (f" compared with {prev.short()}" if prev else "") + f"  |  Orders to {l_to:%d %b %Y}  |  All markets")
    cmp_df = LP.compare_table(ds, cur, prev, None)
    items = LP.insights(ds, cur, prev, None)
    notes = [n for n in (cov.get("note"), cov.get("maturity_note")) if n]

    if "Logistics Summary" in sections:
        ws = B.sheet("Logistics Summary", {0: 30, 1: 14, 2: 14, 3: 14, 4: 14, 5: 14, 6: 16, 7: 16})
        r = B.heading(ws, "Logistics Performance Report", meta, 8)
        ws.write(r, 0, "Prepared", B.f["label"])
        ws.write(r, 1, datetime.now().strftime("%d %b %Y"), B.f["text"])
        r += 2
        s = L.scorecard(ds, cur) if cur.scored else {}
        if s and not is_missing(s.get("l_score")):
            sp = L.scorecard(ds, prev) if prev and prev.scored else {}
            ws.write(r, 0, "Logistics KPI score", B.f["big_lbl"])
            ws.write(r, 2, "Target", B.f["big_lbl"])
            ws.write(r, 4, "Targets hit", B.f["big_lbl"])
            if sp and not is_missing(sp.get("l_score")):
                ws.write(r, 6, f"vs {prev.short()}", B.f["big_lbl"])
            ws.write_number(r + 1, 0, round(s["l_score"], 1), B.wb.add_format(
                {"font_size": 26, "bold": True, "num_format": "0.0",
                 "font_color": TH.GOOD_TEXT if s["l_score"] >= s["target"] else "#A12B2B"}))
            ws.write_number(r + 1, 2, s["target"], B.f["big"])
            ws.write(r + 1, 4, f"{sum(s['hit'].values())} / 3", B.f["big"])
            if sp and not is_missing(sp.get("l_score")):
                ws.write(r + 1, 6, f"{s['l_score'] - sp['l_score']:+.1f}", B.f["big"])
            ws.set_row(r + 1, 34)
            r += 3
            ws.write(r, 0, "Score composition", B.f["section"])
            r += 1
            comp = pd.DataFrame([
                {"KPI": "Delivery rate", "Actual": s["l_delivery"], "0 points at": 0.85, "Full points at": 0.95,
                 "Points": s["pts"]["delivery"], "Out of": 40, "Target hit": "Yes" if s["hit"]["delivery"] else "No"},
                {"KPI": "On-time delivery", "Actual": s["l_ontime"], "0 points at": 0.85, "Full points at": 0.95,
                 "Points": s["pts"]["ontime"], "Out of": 40, "Target hit": "Yes" if s["hit"]["ontime"] else "No"},
                {"KPI": "Markets within window", "Actual": s["l_markets"], "0 points at": 0.60, "Full points at": 1.0,
                 "Points": s["pts"]["markets"], "Out of": 20, "Target hit": "Yes" if s["hit"]["markets"] else "No"}])
            r = B.table(ws, r, 0, comp, units={"Actual": "pct", "0 points at": "ratio", "Full points at": "ratio",
                                                "Points": "pts", "Out of": "count"}, status_cols=("Target hit",))
        ws.write(r, 0, "Headline KPIs", B.f["section"])
        r += 1
        keys = list(cmp_df["key"])
        df = pd.DataFrame({"KPI": cmp_df["KPI"], "Actual": cmp_df["current"], "Target": cmp_df["target"],
                           "Previous": cmp_df["previous"], "Change": cmp_df["change"],
                           "Trend": [_trend_word(t) for t in cmp_df["trend"]],
                           "Status": [_status(k, v, t) if not is_missing(t) else "–"
                                      for k, v, t in zip(cmp_df["key"], cmp_df["current"], cmp_df["target"])]})
        r = _kpi_rows(B, ws, r, df, keys)
        ws.write(r, 0, "Key findings", B.f["section"])
        r += 1
        top = [i for i in items if i.severity in ("critical", "warning")][:5] + [i for i in items if i.severity == "positive"][:3]
        for i in top:
            fm = B.f["bad"] if i.severity in ("critical", "warning") else B.f["good"]
            ws.write(r, 0, {"critical": "Priority", "warning": "Attention", "positive": "Positive"}.get(i.severity, "Note"), fm)
            ws.merge_range(r, 1, r, 7, f"{i.title}. {i.what}" + (f" Action: {i.action}" if i.action else ""), B.f["cell_wrap"])
            ws.set_row(r, 15 * max(2, min(6, len(i.what + i.action) // 95 + 1)))
            r += 1
        if notes:
            r += 1
            ws.write(r, 0, "Data notes", B.f["section"])
            r += 1
            for n in notes:
                ws.merge_range(r, 0, r, 7, n + ".", B.f["muted"])
                ws.set_row(r, 28)
                r += 1

    if "Logistics Markets" in sections:
        ws = B.sheet("Logistics Markets", {0: 16, **{c: 12 for c in range(1, 15)}})
        r = B.heading(ws, "Logistics by Market", meta, 15)
        bc = L.by_country(ds, cur)
        bc = bc[bc["l_orders"] > 0]
        m = LP._market_table(bc)
        if not m.empty:
            m["Within window"] = m["Within window"].str.replace("● ", "").str.replace("▲ ", "")
            for c in ("Delivery rate %", "On-time %", "Return rate %", "Cancellation rate %"):
                m[c] = m[c] / 100
            m = m.rename(columns={"Delivery rate %": "Delivery rate", "On-time %": "On-time", "Return rate %": "Return rate",
                                  "Cancellation rate %": "Cancellation rate"})
            r = B.table(ws, r, 0, m, units={"Orders": "count", "Shipped": "count", "Delivered": "count", "Returned": "count",
                                             "In transit": "count", "Delivery rate": "pct", "On-time": "pct",
                                             "Return rate": "pct", "Cancellation rate": "pct", "Avg delivery days": "days",
                                             "Window (days)": "count", "Order to ship days": "days",
                                             "Delivered value USD": "count"}, status_cols=("Within window",))
        ws.write(r, 0, "Iraq has no agreed delivery window, so it is not one of the 5 scored markets.", B.f["muted"])

    if "Logistics Trend" in sections:
        ws = B.sheet("Logistics Trend", {0: 14, **{c: 12 for c in range(1, 12)}})
        r = B.heading(ws, "Logistics Trend", meta, 12)
        f_from, f_to = L.data_range(ds)
        import periods as P
        months = [p for p in P.available("Month", f_from, f_to) if p.start <= cur.end][:12][::-1]
        ms = L.month_scores(ds, months)
        mt = L.series(ds, months[0].start, cur.end, "M") if months else pd.DataFrame()
        if not mt.empty:
            ws.write(r, 0, "Monthly (last 12 months)", B.f["section"])
            r += 1
            d = pd.DataFrame({"Month": mt["period"].dt.strftime("%Y-%m"), "Orders": mt["l_orders"], "Shipped": mt["l_shipped"],
                              "Delivered": mt["l_delivered"], "Delivery rate": mt["l_delivery"], "On-time": mt["l_ontime"],
                              "Return rate": mt["l_return_rate"], "Cancellation rate": mt["l_cancel_rate"],
                              "Avg delivery days": mt["l_dlv_days"], "Order to ship days": mt["l_lead_days"]})
            if not ms.empty:
                d = d.merge(ms[["period", "l_score"]].rename(columns={"period": "Month", "l_score": "KPI score"}), how="left")
            r = B.table(ws, r, 0, d, units={"Orders": "count", "Shipped": "count", "Delivered": "count", "Delivery rate": "pct",
                                             "On-time": "pct", "Return rate": "pct", "Cancellation rate": "pct",
                                             "Avg delivery days": "days", "Order to ship days": "days", "KPI score": "pts"})
        dd = L.series(ds, cur.start, cur.end, "D")
        if not dd.empty:
            ws.write(r, 0, f"Daily ({cur.short()})", B.f["section"])
            r += 1
            d = pd.DataFrame({"Date": dd["period"].dt.strftime("%Y-%m-%d"), "Orders": dd["l_orders"], "Shipped": dd["l_shipped"],
                              "Delivered": dd["l_delivered"], "Returned": dd["l_returned"], "In transit": dd["l_transit"],
                              "Delivery rate": dd["l_delivery"], "On-time": dd["l_ontime"],
                              "Avg delivery days": dd["l_dlv_days"], "Order to ship days": dd["l_lead_days"]})
            B.table(ws, r, 0, d, units={"Orders": "count", "Shipped": "count", "Delivered": "count", "Returned": "count",
                                         "In transit": "count", "Delivery rate": "pct", "On-time": "pct",
                                         "Avg delivery days": "days", "Order to ship days": "days"}, autofilter=True)

    if "Logistics Insights" in sections:
        ws = B.sheet("Logistics Insights", {0: 11, 1: 12, 2: 38, 3: 60, 4: 45, 5: 45, 6: 14})
        r = B.heading(ws, "Logistics Insights & Actions", meta, 7)
        if items:
            d = pd.DataFrame([i.as_row() for i in items])
            B.table(ws, r, 0, d, wrap_cols=("Finding", "What happened", "Why it matters", "Recommended action"))
        else:
            ws.write(r, 0, "No findings for this period.", B.f["muted"])
