"""Global filters (sidebar). One state, used by every page, table, insight and export."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

import analytics as an
import periods as P
from prepare import Dataset

DEFAULTS = {"f_kind": "Month", "f_cmp": "Previous period", "f_group": "All agents", "f_agents": []}


@dataclass
class Filters:
    period: P.Period
    compare: P.Period | None
    group: str
    agents: list | None          # None = whole team
    agent_choice: list
    cmp_mode: str

    def chips(self) -> list:
        out = [("Period", self.period.short() if self.period.kind != "Month" else P.month_label_long(self.period))]
        out.append(("Compared with", self.compare.short() if self.compare else "None"))
        out.append(("Group", self.group))
        out.append(("Agents", ", ".join(self.agent_choice) if self.agent_choice else "All"))
        return out

    def as_dict(self) -> dict:
        return {"Period": self.period.short(), "Period type": self.period.kind,
                "Compared with": self.compare.short() if self.compare else "None",
                "Group": self.group, "Agents": ", ".join(self.agent_choice) if self.agent_choice else "All agents"}


def _default_period(ds: Dataset, kind: str, options: list):
    f, t = an.data_range(ds)
    for p in options:
        c = an.coverage(ds, p)
        if c["complete"] and c["schedule_ok"]:
            return p
    for p in options:
        if an.coverage(ds, p)["complete"]:
            return p
    return options[0] if options else None


def reset() -> None:
    for k in list(st.session_state.keys()):
        if k.startswith("f_"):
            del st.session_state[k]


def sidebar(ds: Dataset) -> Filters:
    for k, v in DEFAULTS.items():
        st.session_state.setdefault(k, v)
    f_from, f_to = an.data_range(ds)
    st.sidebar.markdown('<div style="font-size:.7rem;letter-spacing:.08em;text-transform:uppercase;color:#8C9AB8;'
                        'margin:.4rem 0 .2rem 0">Filters</div>', unsafe_allow_html=True)
    kind = st.sidebar.selectbox("Period type", P.KINDS, key="f_kind")
    if kind == "Custom":
        default = (max(f_from.date(), (f_to - pd.Timedelta(days=13)).date()), f_to.date())
        rng = st.sidebar.date_input("Date range", value=st.session_state.get("f_range", default),
                                    min_value=f_from.date(), max_value=f_to.date(), key="f_range")
        if isinstance(rng, (list, tuple)) and len(rng) == 2:
            period = P.custom(rng[0], rng[1])
        else:
            period = P.custom(default[0], default[1])
    else:
        opts = P.available(kind, f_from, f_to)
        labels = [p.label for p in opts]
        dflt = _default_period(ds, kind, opts)
        sk = f"f_period_{kind}"
        if sk not in st.session_state or st.session_state[sk] not in labels:
            st.session_state[sk] = dflt.label if dflt else (labels[0] if labels else None)
        lab = st.sidebar.selectbox(kind, labels, key=sk,
                                   format_func=lambda l: _nice(opts[labels.index(l)], ds))
        period = opts[labels.index(lab)]

    cmp_opts = ["Previous period", "Same period last year", "Choose period", "No comparison"]
    if kind in ("Year",):
        cmp_opts = ["Previous period", "Choose period", "No comparison"]
    if st.session_state.get("f_cmp") not in cmp_opts:
        st.session_state["f_cmp"] = cmp_opts[0]
    mode = st.sidebar.selectbox("Compare with", cmp_opts, key="f_cmp")
    compare = None
    if mode == "Previous period":
        compare = P.previous(period)
    elif mode == "Same period last year":
        if period.kind == "Custom":
            compare = P.custom(period.start - pd.DateOffset(years=1), period.end - pd.DateOffset(years=1))
        elif period.kind == "Week":
            compare = P.week(period.start - pd.DateOffset(weeks=52))
        elif period.kind == "Month":
            compare = P.month(period.start.year - 1, period.start.month)
        elif period.kind == "Quarter":
            compare = P.quarter(period.start.year - 1, (period.start.month - 1) // 3 + 1)
    elif mode == "Choose period":
        if kind == "Custom":
            prev = P.previous(period)
            r2 = st.sidebar.date_input("Comparison range", value=(prev.start.date(), prev.end.date()), key="f_range2")
            if isinstance(r2, (list, tuple)) and len(r2) == 2:
                compare = P.custom(r2[0], r2[1])
        else:
            opts = [p for p in P.available(kind, f_from, f_to) if p.label != period.label]
            if opts:
                labs = [p.label for p in opts]
                l2 = st.sidebar.selectbox("Comparison period", labs, key=f"f_cmp_{kind}",
                                          format_func=lambda l: _nice(opts[labs.index(l)], ds))
                compare = opts[labs.index(l2)]

    groups = an.agent_groups(ds, period)
    if st.session_state.get("f_group") not in ["All agents"] + sorted(groups.keys()):
        st.session_state["f_group"] = "All agents"
    group = st.sidebar.selectbox("Group", ["All agents"] + sorted(groups.keys()), key="f_group",
                                 help="Shift group per the scorecard rule: agents with at least half of their working "
                                      "days on the 12 AM - 9 AM shift are night-shift agents.")
    pool = groups.get(group, ds.kpi_agents) if group != "All agents" else ds.kpi_agents
    st.session_state["f_agents"] = [a for a in st.session_state.get("f_agents", []) if a in pool]
    choice = st.sidebar.multiselect("Agents", pool, key="f_agents", placeholder="All agents")
    agents = choice or (pool if group != "All agents" else None)

    st.sidebar.button("Reset filters", on_click=reset, use_container_width=True)
    return Filters(period, compare, group, agents, choice, mode)


def _nice(p: P.Period, ds: Dataset) -> str:
    c = an.coverage(ds, p)
    base = P.month_label_long(p) if p.kind == "Month" else p.short()
    if not c["complete"]:
        return f"{base} (partial)"
    return base
