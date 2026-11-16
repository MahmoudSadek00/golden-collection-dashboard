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
from kpis import ALL_KPIS, OPS_KPIS, achievement, gap, is_missing, target_met, trend

SECTIONS = ["Executive Summary", "KPI Performance", "Period Comparison", "Team Performance",
            "Individual Performance", "Detailed Data", "Findings"]
LOGI_SECTIONS = ["Logistics Summary", "Logistics Markets", "Logistics Trend", "Logistics Findings"]
GOOD, BAD = "#00703C", "#C00000"
SEV_LABEL = {"critical": "Issue", "warning": "Issue", "positive": "Positive", "info": "Note"}

NUMFMT = {"pct": "0.0%", "ratio": "0%", "min": "0.0", "hrs": "0.0", "sec": "#,##0", "days": "0.00", "count": "#,##0",
          "pts": "0.0", "num": "0.0"}


class Book:
    """Plain workbook styling: grey header row, thin borders, red/green text for target status only."""

    def __init__(self):
        self.buf = io.BytesIO()
        self.wb = xlsxwriter.Workbook(self.buf, {"in_memory": True, "nan_inf_to_errors": True})
        wb = self.wb
        base = {"font_name": "Calibri", "font_size": 10, "valign": "vcenter"}
        cell = {**base, "border": 1, "border_color": "#BFBFBF"}
        self.f = {
            "title": wb.add_format({**base, "font_size": 14, "bold": True}),
            "subtitle": wb.add_format({**base, "font_color": "#595959"}),
            "section": wb.add_format({**base, "font_size": 11, "bold": True}),
            "label": wb.add_format({**base, "bold": True}),
            "text": wb.add_format({**base, "text_wrap": True, "valign": "top"}),
            "note": wb.add_format({**base, "font_size": 9, "italic": True, "font_color": "#595959", "text_wrap": True,
                                   "valign": "top"}),
            "note_line": wb.add_format({**base, "font_size": 9, "italic": True, "font_color": "#595959"}),
            "th": wb.add_format({**cell, "bold": True, "bg_color": "#F2F2F2", "text_wrap": True, "align": "center"}),
            "th_left": wb.add_format({**cell, "bold": True, "bg_color": "#F2F2F2", "text_wrap": True}),
            "cell": wb.add_format(cell),
            "cell_wrap": wb.add_format({**cell, "text_wrap": True, "valign": "top"}),
            "cell_b": wb.add_format({**cell, "bold": True}),
            "good": wb.add_format({**cell, "font_color": GOOD}),
            "bad": wb.add_format({**cell, "font_color": BAD}),
            "neutral": wb.add_format({**cell, "font_color": "#7F7F7F"}),
            "good_top": wb.add_format({**cell, "font_color": GOOD, "valign": "top"}),
            "bad_top": wb.add_format({**cell, "font_color": BAD, "valign": "top"}),
        }
        self._num = {}

    def num(self, unit: str, bold=False, color=None):
        key = (unit, bold, color)
        if key not in self._num:
            fm = {"font_name": "Calibri", "font_size": 10, "border": 1, "border_color": "#BFBFBF",
                  "num_format": NUMFMT.get(unit, "0.0"), "bold": bold, "valign": "vcenter"}
            if color:
                fm["font_color"] = color
            self._num[key] = self.wb.add_format(fm)
        return self._num[key]

    def pp(self):
        if "pp" not in self._num:
            self._num["pp"] = self.wb.add_format({"font_name": "Calibri", "font_size": 10, "border": 1,
                                                  "border_color": "#BFBFBF", "valign": "vcenter",
                                                  "num_format": '+0.0" pp";-0.0" pp";0.0" pp"'})
        return self._num["pp"]

    def sheet(self, name: str, widths: dict, landscape=True):
        ws = self.wb.add_worksheet(name[:31])
        if landscape:
            ws.set_landscape()
        ws.fit_to_pages(1, 0)
        ws.set_paper(9)
        ws.set_margins(0.4, 0.4, 0.5, 0.5)
        ws.set_footer("&R&8Page &P of &N")
        for col, w in widths.items():
            ws.set_column(col, col, w)
        return ws

    def heading(self, ws, title: str, meta: str, cols: int = 10):
        ws.write(0, 0, title, self.f["title"])
        ws.set_row(0, 20)
        ws.write(1, 0, meta, self.f["subtitle"])
        return 3

    def blank(self, ws, r, c):
        ws.write_blank(r, c, None, self.f["cell"])

    def table(self, ws, row: int, col: int, df: pd.DataFrame, units: dict | None = None, status_cols=(),
              trend_cols=(), wrap_cols=(), first_bold=True, autofilter=False) -> int:
        units = units or {}
        for j, h in enumerate(df.columns):
            ws.write(row, col + j, h, self.f["th_left"] if j == 0 else self.f["th"])
        for i, (_, r) in enumerate(df.iterrows()):
            for j, h in enumerate(df.columns):
                v = r[h]
                cell = (row + 1 + i, col + j)
                if h in status_cols or h in trend_cols:
                    s = str(v)
                    fm = self.f["good"] if (s.startswith("On target") or s.startswith("Improved") or s.startswith("Yes")) \
                        else self.f["bad"] if (s.startswith("Below") or s.startswith("Declined") or s == "No") \
                        else self.f["cell"]
                    ws.write(*cell, s, fm)
                elif h in units and not isinstance(v, str):
                    if is_missing(v):
                        self.blank(ws, *cell)
                    else:
                        ws.write_number(*cell, float(v), self.num(units[h], bold=(j == 0)))
                elif isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool):
                    if is_missing(v):
                        self.blank(ws, *cell)
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
    return {"improved": "Improved", "declined": "Declined", "stable": "Stable", "up": "Higher", "down": "Lower"}.get(t, "")


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
    fd = f.as_dict()
    scope = f"Group: {fd['Group']}. Agents: {fd['Agents']}."
    label = cur.short() if cur.kind != "Month" else cur.start.strftime("%B %Y")
    meta = (f"Compared with {prev.short()}. " if prev else "") + f"Data up to {ds.coverage['chats_to']:%d %b %Y}."
    notes = [cov[k] for k in ("note", "schedule_note") if cov.get(k)]

    # ------------------------------------------------------------------------------------------ Executive summary
    if "Executive Summary" in sections:
        ws = B.sheet("Executive Summary", {0: 28, 1: 14, 2: 14, 3: 14, 4: 14, 5: 14, 6: 14, 7: 14})
        r = B.heading(ws, f"Customer Support Performance, {label}", meta, 8)
        ws.write(r, 0, "Filters", B.f["label"])
        ws.write(r, 1, scope)
        r += 1
        ws.write(r, 0, "Prepared on", B.f["label"])
        ws.write(r, 1, datetime.now().strftime("%d %b %Y"), B.f["text"])
        r += 2
        sc = tc.get("score")
        if cur.scored and not is_missing(sc):
            n_ok = int(A["score_target_met"].sum()) if not A.empty else 0
            ws.write(r, 0, "Team KPI score", B.f["section"])
            r += 1
            rows = [("Score", sc, B.num("pts", color=GOOD if sc >= T["score"] else BAD)),
                    ("Target", T["score"], B.num("pts")),
                    ("Agents on target", f"{n_ok} of {len(A)}", B.f["cell"])]
            if prev and not is_missing(tp.get("score")):
                rows.append((f"Change vs {prev.short()}", sc - tp["score"], B.wb.add_format(
                    {"font_name": "Calibri", "font_size": 10, "border": 1, "border_color": "#BFBFBF",
                     "num_format": "+0.0;-0.0;0.0"})))
            for lbl, v, fm in rows:
                ws.write(r, 0, lbl, B.f["cell_b"])
                ws.write(r, 1, v, fm)
                r += 1
            r += 1
        ws.write(r, 0, "Headline KPIs", B.f["section"])
        r += 1
        rows = []
        for k in keys:
            v, p_ = tc.get(k), tp.get(k, np.nan) if prev else np.nan
            rows.append({"KPI": ALL_KPIS[k].label, "Actual": v, "Target": T.get(k), "Achievement": achievement(k, v, T.get(k)),
                         "Previous": p_, "Change": (v - p_) if not (is_missing(v) or is_missing(p_)) else np.nan,
                         "Trend": _trend_word(trend(k, v, p_)), "Status": _status(k, v, T.get(k))})
        r = _kpi_rows(B, ws, r, pd.DataFrame(rows), keys)
        top = [i for i in items if i.severity in ("critical", "warning")][:5] + [i for i in items if i.severity == "positive"][:3]
        if top:
            ws.write(r, 0, "Main findings", B.f["section"])
            r += 1
            r = _findings(B, ws, r, top)
        if notes:
            ws.write(r, 0, "Data notes", B.f["section"])
            r += 1
            for n in notes:
                ws.merge_range(r, 0, r, 7, n, B.f["note"])
                ws.set_row(r, 26)
                r += 1

    # ------------------------------------------------------------------------------------------ KPI performance
    if "KPI Performance" in sections:
        ws = B.sheet("KPI Performance", {0: 26, 1: 12, 2: 12, 3: 12, 4: 12, 5: 12, 6: 12, 7: 13, 8: 70})
        r = B.heading(ws, f"KPI Performance, {label}", meta, 10)
        ws.write(r, 0, "Scorecard KPIs", B.f["section"])
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
            for i, (l, a) in enumerate(ach):
                ws.write(cs + i, 11, l)
                ws.write_number(cs + i, 12, min(a, 2.0))
                ws.write_number(cs + i, 13, 1.0)
            ch = B.wb.add_chart({"type": "bar"})
            ch.add_series({"name": "Achievement of target", "categories": ["KPI Performance", cs, 11, cs + len(ach) - 1, 11],
                           "values": ["KPI Performance", cs, 12, cs + len(ach) - 1, 12],
                           "fill": {"color": "#4472C4"}, "gap": 80,
                           "data_labels": {"value": True, "num_format": "0%"}})
            ch.set_title({"name": "% of target", "name_font": {"size": 10, "bold": True}})
            ch.set_x_axis({"num_format": "0%", "major_gridlines": {"visible": True, "line": {"color": "#D9D9D9"}}})
            ch.set_y_axis({"reverse": True})
            ch.set_legend({"none": True})
            ch.set_size({"width": 720, "height": 320})
            ch.show_hidden_data()  # the chart data sits in hidden columns; Excel skips hidden cells unless told otherwise
            ws.insert_chart(r, 0, ch)
            ws.set_column(11, 13, None, None, {"hidden": True})
            r += 18
        ws.write(r, 0, "Other metrics (no target)", B.f["section"])
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
            ws.write(r, 0, "Monthly trend", B.f["section"])
            r += 1
            hk = ["score", "quality", "chats", "calls", "reply", "absence", "fcr", "answer_rate", "adherence"]
            hdf = pd.DataFrame({"Month": H["period"], **{ALL_KPIS[k].label: H[k] for k in hk}})
            r0 = r
            r = B.table(ws, r, 0, hdf, units={ALL_KPIS[k].label: ALL_KPIS[k].unit for k in hk})
            if H["score"].notna().sum() >= 2:
                ch = B.wb.add_chart({"type": "line"})
                ch.add_series({"name": "Team KPI score", "categories": ["KPI Performance", r0 + 1, 0, r0 + len(hdf), 0],
                               "values": ["KPI Performance", r0 + 1, 1, r0 + len(hdf), 1],
                               "line": {"color": "#4472C4", "width": 2},
                               "marker": {"type": "circle", "size": 5, "fill": {"color": "#4472C4"}}})
                ch.set_title({"name": "Team KPI score by month", "name_font": {"size": 10, "bold": True}})
                ch.set_legend({"none": True})
                ch.set_y_axis({"major_gridlines": {"visible": True, "line": {"color": "#D9D9D9"}}})
                ch.set_size({"width": 720, "height": 280})
                ws.insert_chart(r, 0, ch)
                r += 16

    # ------------------------------------------------------------------------------------------ comparison
    if "Period Comparison" in sections and prev:
        ws = B.sheet("Period Comparison", {0: 26, 1: 14, 2: 14, 3: 13, 4: 12, 5: 13, 6: 15, 7: 15, 8: 13})
        r = B.heading(ws, f"Period Comparison, {cur.short()} vs {prev.short()}", f"Data up to {ds.coverage['chats_to']:%d %b %Y}.", 9)
        for w in cmp.warnings(ds, cur, prev):
            ws.merge_range(r, 0, r, 8, w, B.f["note"])
            r += 1
        r += 1
        tcmp = cmp.compare_team(ds, cur, prev, f.agents)
        ws.write(r, 0, "Team KPIs", B.f["section"])
        r += 1
        hdr = ["KPI", cur.short(), prev.short(), "Change", "% change", "Target", f"Status {cur.short()}",
               f"Status {prev.short()}", "Trend"]
        for j, h in enumerate(hdr):
            ws.write(r, j, h, B.f["th_left"] if j == 0 else B.f["th"])
        for _, x in tcmp.iterrows():
            r += 1
            u = ALL_KPIS[x["key"]].unit
            ws.write(r, 0, x["KPI"], B.f["cell_b"])
            for j, v in ((1, x["current"]), (2, x["previous"]), (3, x["change"]), (5, x["target"])):
                if is_missing(v):
                    B.blank(ws, r, j)
                elif j == 3 and u in ("pct", "ratio"):
                    ws.write_number(r, j, float(v) * 100, B.pp())
                else:
                    ws.write_number(r, j, float(v), B.num(u))
            if is_missing(x["change_pct"]):
                B.blank(ws, r, 4)
            else:
                ws.write_number(r, 4, float(x["change_pct"]), B.num("pct"))
            for j, m in ((6, x["met_current"]), (7, x["met_previous"])):
                s = "" if m is None else ("On target" if m else "Below target")
                ws.write(r, j, s, B.f["good"] if s == "On target" else B.f["bad"] if s else B.f["cell"])
            t = _trend_word(x["trend"])
            ws.write(r, 8, t, B.f["good"] if t == "Improved" else B.f["bad"] if t == "Declined" else B.f["cell"])
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

    # ------------------------------------------------------------------------------------------ team / groups
    if "Team Performance" in sections:
        groups = an.agent_groups(ds, cur)
        if groups:
            ws = B.sheet("Team Performance", {0: 26, 1: 16, 2: 16, 3: 16, 4: 16, 5: 16})
            r = B.heading(ws, f"Performance by Group, {label}", meta, 6)
            ws.merge_range(r, 0, r, 5, "Night shift = agents with at least half of their working days on the 12 AM to 9 AM shift.",
                           B.f["note"])
            r += 2
            gn = ["All agents"] + sorted(groups)
            hdr = ["KPI", "Target"] + gn
            for j, h in enumerate(hdr):
                ws.write(r, j, h, B.f["th_left"] if j == 0 else B.f["th"])
            for k in keys:
                r += 1
                u = ALL_KPIS[k].unit
                ws.write(r, 0, ALL_KPIS[k].label, B.f["cell_b"])
                ws.write_number(r, 1, T[k], B.num(u)) if k in T else B.blank(ws, r, 1)
                for j, g in enumerate(gn):
                    t = an.team(ds, cur) if g == "All agents" else an.team(ds, cur, groups[g])
                    v = t.get(k)
                    m = target_met(k, v, T.get(k))
                    if is_missing(v):
                        B.blank(ws, r, 2 + j)
                    else:
                        ws.write_number(r, 2 + j, float(v), B.num(u, color=GOOD if m else (BAD if m is False else None)))
            r += 3
            Aall = an.scorecard(ds, cur)
            vol = Aall.groupby("group")[["working_days", "chats_closed", "inbound_calls", "sales_usd"]].sum()
            tot = vol.sum()
            vdf = pd.DataFrame({"Group": vol.index, "Working days": vol["working_days"].values,
                                "Customers closed": vol["chats_closed"].values,
                                "Share of customers closed": (vol["chats_closed"] / tot["chats_closed"]).values if tot["chats_closed"] else np.nan,
                                "Inbound calls": vol["inbound_calls"].values,
                                "Delivered sales (USD)": vol["sales_usd"].values})
            ws.write(r, 0, "Volume by group", B.f["section"])
            r += 1
            r = B.table(ws, r, 0, vdf, units={"Working days": "count", "Customers closed": "count",
                                               "Share of customers closed": "pct", "Inbound calls": "count",
                                               "Delivered sales (USD)": "count"})

    # ------------------------------------------------------------------------------------------ individual
    if "Individual Performance" in sections and not A.empty:
        ws = B.sheet("Individual Performance", {0: 22, 1: 12})
        r = B.heading(ws, f"Individual Performance, {label}", meta, 14)
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
        cols["Notes"] = [", ".join(x for x, fl in (("Few working days", l), ("No QA score", q)) if fl)
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
                                                               "format": B.wb.add_format({"font_color": BAD})})
            ws.conditional_format(r0 + 1, c, r0 + len(idf), c, {"type": "cell",
                                                               "criteria": ">=" if crit_bad == "<" else "<=", "value": t,
                                                               "format": B.wb.add_format({"font_color": GOOD})})
        ws.write(r, 0, "Red = below target, green = on target. Agents with few working days or no QA score are not ranked.",
                 B.f["note_line"])
        r += 2
        if agent and agent in set(A["agent"]):
            ar = A[A["agent"] == agent].iloc[0]
            ws.write(r, 0, agent, B.f["section"])
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

    # ------------------------------------------------------------------------------------------ detail
    if "Detailed Data" in sections:
        d = ds.daily
        m = (d["date"] >= cur.start) & (d["date"] <= cur.end) & d["agent"].isin(f.agents or ds.kpi_agents)
        dd = d[m].sort_values(["date", "agent"])
        if len(dd):
            ws = B.sheet("Detailed Data", {0: 12, 1: 20, 2: 14, 3: 16, 4: 11, 5: 12, 6: 12, 7: 12, 8: 12})
            r = B.heading(ws, f"Daily Detail by Agent, {label}", meta, 9)
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
            ws.write(r, 0, "Customers closed is counted per day, so the daily rows do not add up to the period totals.",
                     B.f["note_line"])
            r += 2
            r0 = r
            B.table(ws, r, 0, out, units={"Working day": "count", "Customers closed": "count", "Inbound calls": "count",
                                          "Adherence": "pct", "Occupancy": "pct"}, first_bold=False, autofilter=True)

    # ------------------------------------------------------------------------------------------ findings
    if "Findings" in sections and items:
        ws = B.sheet("Findings", {0: 10, 1: 12, 2: 40, 3: 70, 4: 50, 5: 14})
        r = B.heading(ws, f"Findings, {label}", meta, 6)
        r = _findings_table(B, ws, r, items)
        ws.autofilter(3, 0, r - 2, 5)
    if logi_sections:
        _logistics(B, ds, f, logi_sections)
    return B.close()


def _kpi_rows(B: Book, ws, r: int, df: pd.DataFrame, keys: list, definition=False, team_col=False) -> int:
    """KPI table where each row uses its own KPI's number format."""
    hdr = list(df.columns)
    for j, h in enumerate(hdr):
        ws.write(r, j, h, B.f["th_left"] if j == 0 else B.f["th"])
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
                fm = B.f["good"] if s in ("Improved", "On target") else B.f["bad"] if s in ("Declined", "Below target") else B.f["cell"]
                ws.write(rr, j, s, fm)
            elif h == "Achievement":
                if is_missing(v):
                    B.blank(ws, rr, j)
                elif v > 2:
                    ws.write(rr, j, "over 200%", B.f["cell"])
                else:
                    ws.write_number(rr, j, float(v), B.num("ratio"))
            elif h in ("Change", "Gap") and u in ("pct", "ratio") and not is_missing(v):
                ws.write_number(rr, j, float(v) * 100, B.pp())
            elif h == "Definition":
                ws.write(rr, j, v, B.f["cell_wrap"])
                ws.set_row(rr, 15 * max(2, len(str(v)) // 80 + 1))
            else:
                if is_missing(v):
                    B.blank(ws, rr, j)
                else:
                    ws.write_number(rr, j, float(v), B.num(u))
    return r + len(df) + 2


def _findings(B: Book, ws, r: int, items: list, width: int = 7) -> int:
    """Short list for the summary sheets: type + one merged text cell."""
    ws.write(r, 0, "Type", B.f["th_left"])
    ws.merge_range(r, 1, r, width, "Finding", B.f["th_left"])
    for i in items:
        r += 1
        lab = SEV_LABEL.get(i.severity, "Note")
        ws.write(r, 0, lab, B.f["bad_top"] if lab == "Issue" else B.f["good_top"] if lab == "Positive" else B.f["cell_wrap"])
        txt = f"{i.title}. {i.what}"
        ws.merge_range(r, 1, r, width, txt, B.f["cell_wrap"])
        ws.set_row(r, 13.5 * max(1, min(6, len(txt) // 135 + 1)))
    return r + 2


def _findings_table(B: Book, ws, r: int, items: list) -> int:
    """Full findings list: one row per finding, no recommended actions."""
    hdr = ["Type", "Area", "Finding", "Details", "Why it matters", "Basis"]
    for j, h in enumerate(hdr):
        ws.write(r, j, h, B.f["th_left"])
    for i in items:
        r += 1
        lab = SEV_LABEL.get(i.severity, "Note")
        ws.write(r, 0, lab, B.f["bad_top"] if lab == "Issue" else B.f["good_top"] if lab == "Positive" else B.f["cell_wrap"])
        for j, v in enumerate([i.area, i.title, i.what, i.why, i.basis], start=1):
            ws.write(r, j, v or "", B.f["cell_wrap"])
        ws.set_row(r, 14 * max(1, min(8, max(len(i.what) // 75, len(i.why) // 55) + 1)))
    return r + 2


# ------------------------------------------------------------------------------------------------ Logistics
def _logistics(B: Book, ds, f, sections: list) -> None:
    import logi as L
    import logistics as LP
    if not L.has_data(ds):
        ws = B.sheet("Logistics", {0: 90})
        B.heading(ws, "Logistics", "No logistics data available", 4)
        ws.write(3, 0, "The Logistics_Daily tab of the Orders sheet could not be read.", B.f["note_line"])
        return
    cur, prev = f.period, f.compare
    T = L.targets()
    cov = L.coverage(ds, cur)
    _, l_to = L.data_range(ds)
    label = cur.short() if cur.kind != "Month" else cur.start.strftime("%B %Y")
    meta = (f"Compared with {prev.short()}. " if prev else "") + f"Orders up to {l_to:%d %b %Y}, all markets."
    cmp_df = LP.compare_table(ds, cur, prev, None)
    items = LP.insights(ds, cur, prev, None)
    notes = [n for n in (cov.get("note"), cov.get("maturity_note")) if n]

    if "Logistics Summary" in sections:
        ws = B.sheet("Logistics Summary", {0: 30, 1: 14, 2: 14, 3: 14, 4: 14, 5: 14, 6: 16, 7: 16})
        r = B.heading(ws, f"Logistics Performance, {label}", meta, 8)
        ws.write(r, 0, "Prepared on", B.f["label"])
        ws.write(r, 1, datetime.now().strftime("%d %b %Y"), B.f["text"])
        r += 2
        s = L.scorecard(ds, cur) if cur.scored else {}
        if s and not is_missing(s.get("l_score")):
            sp = L.scorecard(ds, prev) if prev and prev.scored else {}
            ws.write(r, 0, "Logistics KPI score", B.f["section"])
            r += 1
            rows = [("Score", s["l_score"], B.num("pts", color=GOOD if s["l_score"] >= s["target"] else BAD)),
                    ("Target", s["target"], B.num("pts")),
                    ("Targets hit", f"{sum(s['hit'].values())} of 3", B.f["cell"])]
            if sp and not is_missing(sp.get("l_score")):
                rows.append((f"Change vs {prev.short()}", s["l_score"] - sp["l_score"], B.wb.add_format(
                    {"font_name": "Calibri", "font_size": 10, "border": 1, "border_color": "#BFBFBF",
                     "num_format": "+0.0;-0.0;0.0"})))
            for lbl, v, fm in rows:
                ws.write(r, 0, lbl, B.f["cell_b"])
                ws.write(r, 1, v, fm)
                r += 1
            r += 1
            ws.write(r, 0, "Score breakdown", B.f["section"])
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
                           "Status": [_status(k, v, t) if not is_missing(t) else ""
                                      for k, v, t in zip(cmp_df["key"], cmp_df["current"], cmp_df["target"])]})
        r = _kpi_rows(B, ws, r, df, keys)
        top = [i for i in items if i.severity in ("critical", "warning")][:5] + [i for i in items if i.severity == "positive"][:3]
        if top:
            ws.write(r, 0, "Main findings", B.f["section"])
            r += 1
            r = _findings(B, ws, r, top)
        if notes:
            ws.write(r, 0, "Data notes", B.f["section"])
            r += 1
            for n in notes:
                ws.merge_range(r, 0, r, 7, n + ".", B.f["note"])
                ws.set_row(r, 26)
                r += 1

    if "Logistics Markets" in sections:
        ws = B.sheet("Logistics Markets", {0: 16, **{c: 12 for c in range(1, 15)}})
        r = B.heading(ws, f"Logistics by Market, {label}", meta, 15)
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
        ws.write(r, 0, "Iraq has no agreed delivery window, so it is not one of the 5 scored markets.", B.f["note_line"])

    if "Logistics Trend" in sections:
        ws = B.sheet("Logistics Trend", {0: 14, **{c: 12 for c in range(1, 12)}})
        r = B.heading(ws, f"Logistics Trend, {label}", meta, 12)
        f_from, f_to = L.data_range(ds)
        import periods as P
        months = [p for p in P.available("Month", f_from, f_to) if p.start <= cur.end][:12][::-1]
        ms = L.month_scores(ds, months)
        mt = L.series(ds, months[0].start, cur.end, "M") if months else pd.DataFrame()
        if not mt.empty:
            ws.write(r, 0, "Last 12 months", B.f["section"])
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
            ws.write(r, 0, f"By day, {cur.short()}", B.f["section"])
            r += 1
            d = pd.DataFrame({"Date": dd["period"].dt.strftime("%Y-%m-%d"), "Orders": dd["l_orders"], "Shipped": dd["l_shipped"],
                              "Delivered": dd["l_delivered"], "Returned": dd["l_returned"], "In transit": dd["l_transit"],
                              "Delivery rate": dd["l_delivery"], "On-time": dd["l_ontime"],
                              "Avg delivery days": dd["l_dlv_days"], "Order to ship days": dd["l_lead_days"]})
            B.table(ws, r, 0, d, units={"Orders": "count", "Shipped": "count", "Delivered": "count", "Returned": "count",
                                         "In transit": "count", "Delivery rate": "pct", "On-time": "pct",
                                         "Avg delivery days": "days", "Order to ship days": "days"}, autofilter=True)

    if "Logistics Findings" in sections:
        ws = B.sheet("Logistics Findings", {0: 10, 1: 12, 2: 40, 3: 70, 4: 50, 5: 14})
        r = B.heading(ws, f"Logistics Findings, {label}", meta, 6)
        if items:
            _findings_table(B, ws, r, items)
        else:
            ws.write(r, 0, "No findings for this period.", B.f["note_line"])
