"""Customer Support - Level 3: individual agent profile."""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

import analytics as an
import comparison as cmp
from kpis import ALL_KPIS, OPS_KPIS, achievement, fmt, fmt_delta, gap, is_missing, target_met, trend
import charts as CH
import components as C
import theme as TH
from common import header, history_months

PROFILE_KPIS = ["score", "quality", "chats", "calls", "sales", "reply", "absence", "fcr"]


def observations(r: pd.Series, A: pd.DataFrame, team: dict, prev_r, T: dict, cur_scored: bool) -> list:
    """Agent-specific, evidence-based observations (what differs and the likely 'why' context)."""
    out = []
    med_wd = A["working_days"].median()
    if r["working_days"] < 0.5 * med_wd:
        out.append(("info", f"Worked {r['working_days']:.0f} days against a team median of {med_wd:.0f}; "
                            "results are based on limited data and excluded from rankings."))
    if not is_missing(r.get("chats")) and not is_missing(team.get("chats")):
        d = r["chats"] / team["chats"] - 1
        if abs(d) >= 0.1:
            out.append(("positive" if d > 0 else "warning",
                        f"Closes {r['chats']:.1f} customers per working day, {abs(d) * 100:.0f}% "
                        f"{'above' if d > 0 else 'below'} the team rate of {team['chats']:.1f}."))
    if not is_missing(r.get("reply")) and not is_missing(team.get("reply")):
        d = r["reply"] - team["reply"]
        if abs(d) >= 1:
            out.append(("warning" if d > 0 else "positive",
                        f"First reply averages {r['reply']:.1f} min versus a team average of {team['reply']:.1f} min "
                        f"({'slower' if d > 0 else 'faster'} by {abs(d):.1f} min)."))
    if bool(r.get("night")):
        out.append(("info", f"Night-shift agent ({int(r['night_shifts'])} of {int(r['working_days'])} days on the night "
                            "shift): calls points follow the best day-shift agent, as the scorecard rule defines."))
    if not is_missing(r.get("sales")) and r.get("sales_chats", 0):
        out.append(("info", f"Handled {r['share_sales_chats'] * 100:.1f}% of the team's sales chats and generated "
                            f"{r['share_sales'] * 100:.1f}% of delivered sales (contribution {r['sales'] * 100:.0f}%)."))
    if cur_scored and r.get("qa_missing"):
        out.append(("warning", "No QA score entered for this period: quality earns 0 points, so the KPI score is understated."))
    if prev_r is not None and not is_missing(prev_r.get("score")) and not is_missing(r.get("score")):
        d = r["score"] - prev_r["score"]
        if abs(d) >= 5:
            drivers = []
            for k in ["quality", "chats", "calls", "sales", "reply", "absence"]:
                pk = f"pts_{k}"
                if pk in r and pk in prev_r and not is_missing(r[pk]) and not is_missing(prev_r[pk]):
                    dd = r[pk] - prev_r[pk]
                    if abs(dd) >= 1:
                        drivers.append((k, dd))
            drivers.sort(key=lambda x: -abs(x[1]))
            txt = ", ".join(f"{ALL_KPIS[k].label} {dd:+.1f} pts" for k, dd in drivers[:3])
            out.append(("positive" if d > 0 else "warning",
                        f"Score moved {d:+.1f} points vs the comparison period" + (f", driven by {txt}." if txt else ".")))
    return out


def page() -> None:
    ds, f = header("Customer Support", "Agent Profile",
                   "Individual results against target, team and history, with the drivers of the score.")
    cur, prev = f.period, f.compare
    T = cmp.targets(ds)
    A_all = an.scorecard(ds, cur)
    if A_all.empty:
        C.note("No agent has a working day in this period.")
        return
    pool = [a for a in (f.agents or ds.kpi_agents) if a in set(A_all["agent"])]
    if not pool:
        C.note("None of the selected agents worked in this period.")
        return
    agent = st.selectbox("Agent", pool, key="agent_profile")
    r = A_all[A_all["agent"] == agent].iloc[0]
    B = an.scorecard(ds, prev) if prev else pd.DataFrame()
    prev_r = B[B["agent"] == agent].iloc[0] if (not B.empty and agent in set(B["agent"])) else None
    team = an.team(ds, cur)
    cov = an.coverage(ds, cur)
    scored = cur.scored and cov.get("schedule_ok", True)

    # ---------------------------------------------------------------- identity strip
    rank_txt = "—"
    if scored and not is_missing(r.get("rank")):
        rank_txt = f"{int(r['rank'])} of {len(A_all)}" + ("" if r["comparable"] else " (not comparable)")
    sc = r.get("score") if scored else np.nan
    c1, c2 = st.columns([1.05, 2.6], gap="medium")
    with c1:
        if scored:
            C.hero_score(sc, T["score"], prev_r.get("score") if (prev_r is not None and prev and prev.scored) else None,
                         prev.short() if prev else "", f"Rank {rank_txt}", label=f"{agent} · KPI score")
        else:
            C.hero_score(np.nan, T["score"], None, "", "", label=agent,
                         unavailable=cov.get("schedule_note") or "The KPI score is defined per month and quarter.")
    with c2:
        flags = []
        if r["limited_data"]:
            flags.append("Limited working days")
        if r.get("qa_missing"):
            flags.append("QA not entered")
        st.markdown(f"""<div class="gc-card"><div class="gc-kpi-label"><span>Profile</span></div>
            <div class="gc-kpi-row" style="font-size:.86rem"><span>Team <b>{C.esc(r['team'])}</b></span>
            <span>Group <b>{C.esc(r['group'])}</b></span><span>Working days <b>{r['working_days']:.0f}</b></span>
            <span>Night shifts <b>{int(r['night_shifts'])}</b></span><span>Absent days <b>{int(r['absent_days'])}</b></span>
            <span>Customers closed <b>{int(r['chats_closed']):,}</b></span><span>Inbound calls <b>{int(r['inbound_calls']):,}</b></span>
            <span>Delivered sales <b>${r['sales_usd']:,.0f}</b></span></div>
            <div class="gc-kpi-row">{''.join(f'<span class="gc-chip warn">⚠ {C.esc(x)}</span>' for x in flags)}</div></div>""",
                    unsafe_allow_html=True)
        st.write("")
        obs = observations(r, A_all, team, prev_r, T, cur.scored)
        if obs:
            html = "".join(f'<p style="margin:.2rem 0"><span style="color:{TH.SEVERITY[s]["color"]}">●</span> {C.esc(t)}</p>'
                           for s, t in obs)
            st.markdown(f'<div class="gc-card"><div class="gc-kpi-label"><span>Observations</span></div>'
                        f'<div class="b" style="font-size:.84rem;color:{TH.INK_2};margin-top:.3rem">{html}</div></div>',
                        unsafe_allow_html=True)

    # ---------------------------------------------------------------- KPI matrix
    C.section("KPI detail", "Team = the team result (approved team formula). Agent average = simple average of all "
              "scored agents. Gap: positive = better than target.")
    rows = []
    for k in PROFILE_KPIS:
        if k in an.SCHEDULE_KPIS and not cov.get("schedule_ok", True):
            continue
        if (k == "score" or ALL_KPIS[k].monthly_only) and not cur.scored:
            continue
        v = r.get(k, np.nan)
        p_ = prev_r.get(k, np.nan) if prev_r is not None else np.nan
        t = T.get(k)
        night = k == "calls" and bool(r.get("night"))
        rows.append({"KPI": ALL_KPIS[k].label, "Actual": fmt(k, v), "Target": fmt(k, t),
                     "Gap": fmt_delta(k, gap(k, v, t)),
                     "Team": fmt(k, team.get(k)) if k != "sales" else "—",
                     "Agent average": fmt(k, A_all[k].mean()) if k in A_all else "—",
                     "Previous": fmt(k, p_), "Change": fmt_delta(k, v - p_) if not (is_missing(v) or is_missing(p_)) else "—",
                     "Trend": C.trend_text(trend(k, v, p_)),
                     "Status": "◐ Night shift" if night else C.met_text(target_met(k, v, t)),
                     "Points": f"{r.get('pts_' + k):.1f} / {ds.cfg['weights'][k]['ptsNoFcr']:.0f}"
                     if k in ds.cfg["weights"] and ds.cfg["weights"][k]["ptsNoFcr"] and not is_missing(r.get("pts_" + k)) else "—"})
    st.dataframe(C.style_status(pd.DataFrame(rows), ["Trend", "Status"]), hide_index=True, use_container_width=True)

    # ---------------------------------------------------------------- strongest / weakest
    ach = {}
    for k in ["quality", "chats", "calls", "sales", "reply", "absence", "fcr"]:
        if k == "calls" and bool(r.get("night")):
            continue
        if (k in an.SCHEDULE_KPIS and not cov.get("schedule_ok", True)) or (ALL_KPIS[k].monthly_only and not cur.scored):
            continue
        a = achievement(k, r.get(k), T.get(k))
        if not is_missing(a):
            ach[k] = a
    if ach:
        # strongest = KPIs on target (best first); weakest = KPIs below target (worst first). A KPI is never in both.
        met = {k: target_met(k, r.get(k), T.get(k)) for k in ach}
        strong = sorted([k for k in ach if met[k]], key=lambda k: -ach[k])[:3]
        weak = sorted([k for k in ach if met[k] is False], key=lambda k: ach[k])[:3]

        def line(k):
            return f"- **{ALL_KPIS[k].label}**: {fmt(k, r[k])} ({ach[k] * 100:.0f}% of target {fmt(k, T[k])})"
        c1, c2 = st.columns(2, gap="medium")
        with c1:
            C.section("Strongest areas", "KPIs on target, best first.")
            st.markdown("\n".join(line(k) for k in strong) if strong else "No KPI on target in this period.")
        with c2:
            C.section("Weakest areas", "KPIs below target, furthest from target first.")
            st.markdown("\n".join(line(k) for k in weak) if weak else "All measured KPIs are on target.")
        if r.get("qa_missing") and cur.scored:
            st.caption("Quality is not listed: no QA score was entered for this period.")

    # ---------------------------------------------------------------- charts
    c1, c2 = st.columns(2, gap="medium")
    with c1:
        if scored:
            st.plotly_chart(CH.score_breakdown(r, ds.cfg, "Score composition (points earned of available)"),
                            use_container_width=True, config={"displayModeBar": False})
        else:
            k_ = "reply"
            st.plotly_chart(CH.actual_vs_target_bars(A_all, "agent", k_, "First reply vs peers", T[k_], team.get(k_),
                                                     highlight=agent), use_container_width=True, config={"displayModeBar": False})
    with c2:
        opts = [k for k in PROFILE_KPIS if k != "sales"]
        k = st.selectbox("History of", opts, format_func=lambda x: ALL_KPIS[x].label, key="agent_hist")
        months = history_months(ds, cur.end, 12)
        H = an.agent_month_series(ds, months, agent)
        TM = an.month_series(ds, months)
        st.plotly_chart(CH.trend_line(H, "period", k, f"{ALL_KPIS[k].label}: {agent} vs team", T.get(k), agent, TM),
                        use_container_width=True, config={"displayModeBar": False})

    k2 = st.selectbox("Position among agents", [k for k in ["chats", "reply", "fcr", "calls", "sales", "quality", "score"]
                                                 if not (k in an.SCHEDULE_KPIS and not cov.get("schedule_ok", True))],
                      format_func=lambda x: ALL_KPIS[x].label, key="agent_peer")
    st.plotly_chart(CH.actual_vs_target_bars(A_all, "agent", k2, f"{ALL_KPIS[k2].label}: {agent} among all agents",
                                             T.get(k2), team.get(k2) if k2 != "sales" else None, highlight=agent),
                    use_container_width=True, config={"displayModeBar": False})

    # ---------------------------------------------------------------- operations
    C.section("Operational metrics", "CS Pulse definitions for this agent.")
    o = an.ops(ds, cur, [agent])
    ot = an.ops(ds, cur)
    op = an.ops(ds, prev, [agent]) if prev else {}
    items = [dict(key=k, value=o.get(k), prev=op.get(k) if prev else None, prev_label=prev.short() if prev else "",
                  note_txt=f"Team {fmt(k, ot.get(k))}") for k in ["adherence", "occupancy", "shrinkage", "frt_median",
                                                                  "answer_rate", "call_aht", "conversations", "resolution_median"]]
    C.kpi_grid(items, cols=4)
