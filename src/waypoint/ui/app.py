"""Waypoint — local app (career radar + personal orchestrator).

Open it with the "Waypoint" desktop shortcut or `waypoint ui`. Everything runs on your computer.

UX principles applied here (see README → "UX"):
* One primary action per screen: "Today" opens on what to do *now*, not on charts.
* Navigation grouped by goal (Plan / Market / You), with a visible active state.
* Visibility of system status: background update progress, toasts after every action, last-update stamp.
* User control: undo the last log entry, two-step delete, nothing is ever cut silently (trade-offs are offered).
* Recognition over recall: every area/role has icon + label + color; help text on non-obvious controls.
* Progressive disclosure: details live in expanders and popovers; empty states always offer the next step.
* Accessibility: validated chart palettes per theme, never color alone, visible keyboard focus, dark/light, PT/EN.
"""
from __future__ import annotations

import os
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import altair as alt
import pandas as pd
import streamlit as st

from waypoint import orchestrator as orc
from waypoint import pipeline as pl
from waypoint import updater
from waypoint.analysis import market
from waypoint.analysis.gap import gap_table, market_fit
from waypoint.collect import add_manual, reassign_roles
from waypoint.db import DB
from waypoint.llm import LLMNotConfigured, config_from_env, make_client
from waypoint.profile import build_profile, effective_levels, load_profile, save_overrides
from waypoint.report import linkedin_post_draft, post_numbers
from waypoint.settings import load_config, make_custom_role, save_local
from waypoint.ui import theme as th
from waypoint.ui.i18n import S as STRINGS
from waypoint.ui.i18n import (SENIORITY, hours as fh, lang, long_date, pct, region, role_field, set_lang, short_date,
                              seniority, t, weekday_short)

_ICON = Path(__file__).resolve().parents[3] / "assets" / "waypoint_icon.png"
st.set_page_config(page_title="Waypoint", page_icon=str(_ICON) if _ICON.exists() else "🧭", layout="wide",
                   initial_sidebar_state="expanded")

cfg = load_config()
cfg.paths.ensure()
db = DB(cfg.paths.db)
try:
    from waypoint.launcher import register_server
    register_server(cfg.paths.root)
except Exception:  # never block the UI because of bookkeeping
    pass
SETTINGS = updater.load_ui_settings(cfg)
set_lang(SETTINGS.get("lang", "pt"))
if th.apply_theme(SETTINGS.get("theme", "dark")):
    st.rerun()
th.inject_css()
TOK = th.tok()

TODAY = date.fromisoformat(os.environ["WAYPOINT_TODAY"]) if os.environ.get("WAYPOINT_TODAY") else date.today()
MIN_ROLE_JOBS = 10
PAGES = [("plan", "today", "☀️"), ("plan", "week", "🗓️"), ("plan", "projects", "📁"), ("plan", "plan", "📚"),
         ("market", "market", "📊"), ("market", "compare", "⚖️"), ("market", "jobs", "💼"), ("market", "roles", "🎯"),
         ("you", "profile", "👤"), ("you", "report", "📝")]
AREA_ICON = orc.AREA_ICON


# ============================================================================= helpers
def go(page: str) -> None:
    st.session_state["page"] = page


def save_setting(key: str, widget: str) -> None:
    val = st.session_state.get(widget)
    if val:
        updater.save_ui_settings(cfg, **{key: val})


def area_label(a: str) -> str:
    return f"{AREA_ICON.get(a, '•')} {t('area_' + a)}" if f"area_{a}" in STRINGS else a


def dot(color: str) -> str:
    return f'<span class="wp-dot" style="background:{color}"></span>'


def role_label(rid: str) -> str:
    return cfg.all_roles.get(rid, {}).get("label", rid)


def role_color(rid: str) -> str:
    return th.role_color(rid, list(cfg.all_roles))


def llm_client():
    try:
        return make_client(db)
    except LLMNotConfigured:
        return None


def llm_label() -> Optional[str]:
    try:
        c = config_from_env()
        return f"{c.provider} · {c.model}"
    except LLMNotConfigured:
        return None


def pills(items: list[str], cls: str = "") -> str:
    return " ".join(f'<span class="wp-pill {cls}">{i}</span>' for i in items)


def eyebrow(text: str) -> None:
    st.markdown(f'<div class="wp-eyebrow">{text}</div>', unsafe_allow_html=True)


def page_header(title: str, sub: str = "") -> None:
    st.markdown(f'<div class="wp-h1">{title}</div>' + (f'<p class="wp-sub">{sub}</p>' if sub else ""),
                unsafe_allow_html=True)


def bar(frac: float) -> str:
    return f'<div class="wp-bar"><span style="width:{max(0, min(frac, 1)) * 100:.0f}%"></span></div>'


def due_chip(due: Optional[str]) -> str:
    if not due:
        return ""
    d = date.fromisoformat(due[:10])
    n = (d - TODAY).days
    if n < 0:
        txt, urgent = t("late_by", n=-n), True
    elif n == 0:
        txt, urgent = t("due_today"), True
    elif n == 1:
        txt, urgent = t("due_tomorrow"), True
    elif n <= 7:
        txt, urgent = t("due_in", n=n), False
    else:
        txt, urgent = t("due_on", date=short_date(d)), False
    return f'<span class="wp-chip-due {"urgent" if urgent else ""}">⏰ {txt}</span>'


def _stamp() -> tuple:
    files = [*cfg.paths.data.glob("waypoint.db*"), *cfg.paths.config.glob("*.yaml"),
             cfg.paths.profile / "profile.json", cfg.paths.profile / "overrides.yaml"]
    return (str(cfg.paths.root),) + tuple((f.name, f.stat().st_mtime_ns) for f in files if f.exists())


@st.cache_data(show_spinner=False, max_entries=4)
def get_analysis(stamp: tuple, extractor: str):
    c = load_config()
    d = DB(c.paths.db)
    try:
        return pl.analyze(c, d, extractor)
    finally:
        d.conn.close()


EXTRACTOR = pl.resolve_extractor(db)
A = get_analysis(_stamp(), EXTRACTOR) if db.count_jobs() else None
HAS_DATA = A is not None and not A.jobs_df.empty
PROFILE = load_profile(cfg.paths.profile)
LEVELS = effective_levels(cfg.paths.profile)
STATE_PATH = orc.state_path(cfg.paths.data)
STATE = orc.State.load(STATE_PATH)
PLAN = pl.load_plan(cfg)
SCHED = orc.build_schedule(STATE, PLAN, today=TODAY)
if orc.take_snapshot(STATE, SCHED):
    STATE.save(STATE_PATH)


def save_state() -> None:
    STATE.save(STATE_PATH)


def item_titles() -> dict[str, tuple[str, str, str]]:
    """item id -> (title, area, project)"""
    out: dict[str, tuple[str, str, str]] = {}
    for p in STATE.projects:
        out[f"proj:{p.id}"] = (p.name, p.area, p.name)
        for tk in p.tasks:
            out[f"task:{tk.id}"] = (tk.title, p.area, p.name)
    for it in (PLAN or {}).get("this_week", []):
        foco = orc.STUDY_FOCUS_KEY.get(it.get("foco", ""), "carreira")
        out[it.get("id") or f"study:{foco}:{it.get('item')}"] = (it.get("item", ""), foco, t("area_" + foco))
    return out


def log_block(item: str, hours: float, title: str) -> None:
    STATE.add_log(item, hours, TODAY)
    save_state()
    st.session_state["last_log"] = item
    st.toast(t("logged_toast", h=fh(hours), what=title), icon="✅")


# ============================================================================= charts
def chart_skills(tbl: pd.DataFrame, top: int, select: bool = False):
    tt = tbl[~tbl["skill_id"].str.startswith("other:")].head(top)
    rows = []
    for r in tt.itertuples():
        rows.append({"Skill": r.name, "skill_id": r.skill_id, "kind": t("required"), "korder": 0, "share": r.share_required,
                     "total": r.share_any, "n": int(r.n_any)})
        rows.append({"Skill": r.name, "skill_id": r.skill_id, "kind": t("nice"), "korder": 1, "share": r.share_nice,
                     "total": r.share_any, "n": int(r.n_any)})
    d = pd.DataFrame(rows)
    order = tt["name"].tolist()
    sel = alt.selection_point(fields=["skill_id"], name="skill", on="click", empty=True)
    ch = alt.Chart(d).mark_bar(cornerRadiusEnd=4, height={"band": 0.72}, stroke=TOK["bg"], strokeWidth=1).encode(
        y=alt.Y("Skill:N", sort=order, title=None, axis=alt.Axis(labelLimit=220, labelOverlap=False)),
        x=alt.X("share:Q", stack="zero", title=t("share_postings"), axis=alt.Axis(format="%", tickCount=5)),
        color=alt.Color("kind:N", scale=alt.Scale(domain=[t("required"), t("nice")], range=[TOK["required"], TOK["nice"]]),
                        legend=alt.Legend(title=None)),
        order=alt.Order("korder:Q"),
        tooltip=[alt.Tooltip("Skill:N"), alt.Tooltip("kind:N", title=t("how_asked")),
                 alt.Tooltip("share:Q", format=".0%", title=t("share_postings")),
                 alt.Tooltip("total:Q", format=".0%", title=t("total_share")), alt.Tooltip("n:Q", title=t("n_postings"))],
        opacity=alt.condition(sel, alt.value(1.0), alt.value(0.35)) if select else alt.value(1.0),
    ).properties(height=max(260, 26 * len(order)))
    if select:
        ch = ch.add_params(sel)
    return th.style(ch), max(260, 26 * len(order)) + 70


def chart_hbar(d: pd.DataFrame, y: str, x: str, color_col: Optional[str] = None, fmt: str = ".0%",
               domain_max: Optional[float] = None, height_per: int = 40):
    enc_color = (alt.Color(f"{color_col}:N", scale=None, legend=None) if color_col else alt.value(TOK["primary"]))
    xs = alt.Scale(domain=[0, domain_max]) if domain_max else alt.Undefined
    base = alt.Chart(d).encode(
        y=alt.Y(f"{y}:N", sort="-x", title=None, axis=alt.Axis(labelLimit=230, labelOverlap=False)),
        x=alt.X(f"{x}:Q", title=None, axis=alt.Axis(format=fmt if fmt.endswith("%") else "", tickCount=4), scale=xs),
        tooltip=[y, alt.Tooltip(f"{x}:Q", format=fmt)])
    ch = base.mark_bar(cornerRadiusEnd=4, height={"band": 0.62}).encode(color=enc_color)
    txt = base.mark_text(align="left", dx=5, color=TOK["ink"]).encode(text=alt.Text(f"{x}:Q", format=fmt))
    h = height_per * len(d) + 10
    return th.style((ch + txt).properties(height=h)), h + 40


# ============================================================================= sidebar
def _update_panel_body() -> None:
    s = updater.read_status(cfg)
    if s.get("state") == "running":
        st.session_state["_was_running"] = True
        st.progress(min(max(float(s.get("frac") or 0), 0.0), 1.0), text=s.get("msg") or t("updating"))
        st.caption(t("updating_since", when=s.get("started", "")))
        return
    if st.session_state.pop("_was_running", False):
        st.cache_data.clear()
        st.toast(t("update_done_toast"), icon="✅")
        st.rerun(scope="app")
    st.caption(t("last_update", when=pl.last_update(cfg) or t("never")))
    if s.get("state") == "failed":
        st.error(t("update_failed", err=s.get("error")), icon="⚠️")
    if st.button(f"🔄 {t('update_all')}", width="stretch", help=t("update_help"), key="btn_update"):
        updater.start_background_update(cfg)
        st.rerun(scope="app")


def sidebar() -> None:
    with st.sidebar:
        st.markdown('<p class="wp-brand">🧭 Waypoint</p>', unsafe_allow_html=True)
        st.caption(t("app_tagline"))
        c1, c2 = st.columns(2)
        c1.segmented_control(t("theme"), ["dark", "light"], default=SETTINGS.get("theme", "dark"), key="ui_theme",
                             format_func=lambda x: "🌙" if x == "dark" else "☀️", on_change=save_setting,
                             args=("theme", "ui_theme"), label_visibility="collapsed")
        c2.segmented_control(t("language"), ["pt", "en"], default=SETTINGS.get("lang", "pt"), key="ui_lang",
                             format_func=lambda x: x.upper(), on_change=save_setting, args=("lang", "ui_lang"),
                             label_visibility="collapsed")
        if "page" not in st.session_state:
            st.session_state["page"] = "today"
        current = st.session_state["page"]
        section = None
        for sec, key, icon in PAGES:
            if sec != section:
                st.markdown(f'<div class="wp-nav-section">{t("sec_" + sec)}</div>', unsafe_allow_html=True)
                section = sec
            label = f"{icon}  {t('nav_' + key)}"
            if key == "today" and (SCHED.risks or SCHED.overdue):
                label += "  ⚠️"
            st.button(label, key=f"nav_{key}", type="primary" if key == current else "tertiary", width="stretch",
                      on_click=go, args=(key,))
        st.divider()
        running = updater.is_running(cfg)
        st.fragment(_update_panel_body, run_every=2 if running else None)()
        n_jobs = len(A.jobs_df) if HAS_DATA else 0
        st.caption(t("status_line", n=n_jobs, r=len(cfg.roles), ai=llm_label() or t("no_key")))
        with st.expander(t("options")):
            auto = st.toggle(t("auto_update"), value=bool(SETTINGS["auto_update_on_open"]), help=t("auto_update_help"))
            if auto != SETTINGS["auto_update_on_open"]:
                updater.save_ui_settings(cfg, auto_update_on_open=auto)
            if st.button(f"⏻ {t('shutdown')}", width="stretch", help=t("shutdown_help"), key="btn_quit"):
                st.success(t("shutdown_done"))
                threading.Timer(1.0, lambda: os._exit(0)).start()


# ============================================================================= PLAN: today
def greeting() -> str:
    h = datetime.now().hour
    return t("greet_morning") if h < 12 else (t("greet_afternoon") if h < 18 else t("greet_evening"))


def page_today() -> None:
    eyebrow(long_date(TODAY))
    page_header(greeting() + " 👋")
    titles = item_titles()

    if SCHED.slipped:
        items = ", ".join(f"{s['title']} ({fh(s['missing'])})" for s in SCHED.slipped[:4])
        st.info(t("slipped", day=short_date(date.fromisoformat(SCHED.slipped[0]["date"])), items=items), icon="🔁")
    for i, r in enumerate(SCHED.risks):
        with st.container(key=f"card_risk_{i}"):
            st.markdown("⚠️ " + t("risk", task=r.title, project=r.project, due=due_chip(r.due), h=fh(r.missing)),
                        unsafe_allow_html=True)
            cols = st.columns(len(r.borrowable) + 2)
            for c, (foco, hrs) in zip(cols, r.borrowable.items()):
                h = min(hrs, r.missing)
                if c.button(t("risk_borrow", h=fh(h), foco=t("area_" + foco).lower()), key=f"borrow_{i}_{foco}",
                            help=t("risk_borrow_help", foco=t("area_" + foco).lower())):
                    orc.accept_borrow(STATE, TODAY, foco, h)
                    save_state()
                    st.toast(t("borrow_toast", h=fh(h), foco=t("area_" + foco).lower(), task=r.title), icon="🤝")
                    st.rerun()
            cols[-2].button(t("risk_hours"), key=f"risk_time_{i}", on_click=go, args=("week",))
            cols[-1].button(t("risk_scope"), key=f"risk_scope_{i}", on_click=go, args=("projects",))

    has_anything = bool(STATE.projects) or bool(PLAN)
    if not has_anything:
        with st.container(key="hero_empty"):
            st.markdown(f'<div class="wp-now-title">{t("empty_today_title")}</div>', unsafe_allow_html=True)
            st.write(t("empty_today"))
            c1, c2, c3 = st.columns(3)
            c1.button(t("cta_add_project"), type="primary", on_click=go, args=("projects",), key="cta_proj")
            c2.button(t("cta_make_plan"), on_click=go, args=("plan",), key="cta_plan")
            c3.button(t("cta_set_time"), on_click=go, args=("week",), key="cta_time")
        onboarding()
        return

    left, right = st.columns([1.55, 1], gap="large")
    day = SCHED.days[0]
    skipped = st.session_state.setdefault("skipped", set())
    queue = [b for b in day.blocks if b.item not in skipped] + [b for b in day.blocks if b.item in skipped]
    with left:
        with st.container(key="hero_now"):
            if queue:
                b = queue[0]
                eyebrow(f"{t('now_label')} · {area_label(b.area)}")
                st.markdown(f'<div class="wp-now-title">{b.title}</div>', unsafe_allow_html=True)
                meta = [b.project] if b.project and b.project != b.title else []
                meta.append(fh(b.hours))
                st.markdown(f'<span class="wp-meta">{" · ".join(meta)}</span> &nbsp;{due_chip(b.due)}',
                            unsafe_allow_html=True)
                if st.button(f"✓ {t('done_btn', h=fh(b.hours))}", type="primary", key="now_done", width="stretch"):
                    log_block(b.item, b.hours, b.title)
                    st.rerun()
                c2, c3 = st.columns(2)
                with c2.popover(t("partial_btn"), width="stretch"):
                    hv = st.number_input(t("partial_hours"), 0.5, 12.0, min(1.0, b.hours), 0.5, key="now_partial_h")
                    if st.button(t("partial_save"), key="now_partial_save", type="primary"):
                        log_block(b.item, hv, b.title)
                        st.rerun()
                if c3.button(t("skip_btn"), key="now_skip", help=t("skip_help"), width="stretch", disabled=len(queue) < 2):
                    skipped.add(b.item)
                    st.rerun()
            else:
                st.markdown(f'<div class="wp-now-title">{t("day_done") if STATE.logged_on(TODAY) else t("now_empty")}</div>',
                            unsafe_allow_html=True)
        done, total = orc.today_progress(STATE, SCHED)
        if total > 0:
            st.markdown(bar(done / total), unsafe_allow_html=True)
            st.caption(t("goal_today", done=fh(done), total=fh(total)))
        if st.session_state.get("last_log"):
            if st.button(f"↩️ {t('undo_last')}", key="undo_log", type="tertiary"):
                if STATE.undo_last_log(st.session_state.pop("last_log"), TODAY):
                    save_state()
                    st.toast(t("undone_toast"), icon="↩️")
                st.rerun()

        rest = queue[1:]
        if rest:
            st.markdown(f"#### {t('rest_of_day')}")
            for i, b in enumerate(rest):
                c1, c2 = st.columns([5, 1.2])
                ctx = b.project if b.project and b.project != b.title else area_label(b.area)
                c1.markdown(f'{dot(th.area_color(b.area))}**{b.title}** <span class="wp-muted">· '
                            f'{ctx} · {fh(b.hours)}</span> '
                            f'{due_chip(b.due)}', unsafe_allow_html=True)
                if c2.button("✓ " + fh(b.hours), key=f"rest_done_{i}", help=t("done_btn", h=fh(b.hours)), width="stretch"):
                    log_block(b.item, b.hours, b.title)
                    st.rerun()
        logged = [e for e in STATE.log if e["date"] == TODAY.isoformat()]
        if logged:
            st.markdown(f"#### {t('done_today')}")
            for e in logged:
                ttl, area, _ = titles.get(e["item"], (e["item"], "pessoal", ""))
                st.markdown(f'<div class="wp-block done">{AREA_ICON.get(area, "•")} {ttl} · {fh(e["hours"])}</div>',
                            unsafe_allow_html=True)

    with right:
        with st.container(key="card_freetime"):
            cap = STATE.capacity(TODAY)
            new = st.number_input(f"⏱️ {t('free_today')}", 0.0, 16.0, float(cap), 0.5, help=t("free_today_help"),
                                  key="free_today", format="%.1f")
            if new != cap:
                STATE.day_overrides[TODAY.isoformat()] = new
                save_state()
                st.rerun()
        with st.container(key="card_weekglance"):
            st.markdown(f"**{t('week_glance')}**")
            st.caption(t("week_glance_help"))
            if SCHED.week_load:
                d = pd.DataFrame([{"area": f"{AREA_ICON.get(a, '•')} {t('area_' + a)}", "h": h, "c": th.area_color(a)}
                                  for a, h in SCHED.week_load.items()])
                ch, hgt = chart_hbar(d, "area", "h", color_col="c", fmt=".1f", height_per=34)
                st.altair_chart(ch, width="stretch", height=hgt)
            st.button(t("see_week"), on_click=go, args=("week",), key="go_week", width="stretch")
        if HAS_DATA:
            with st.container(key="card_pulse"):
                st.markdown(f"**{t('market_pulse')}**")
                gap = pl.compute_gap(cfg, A)
                m1, m2 = st.columns(2)
                m1.metric(t("m_jobs"), len(A.jobs_df))
                m2.metric(t("fit_label"), pct(market_fit(gap)) if LEVELS else "—", help=t("fit_help"))
                top = gap[gap["status"] != "has"].sort_values("priority", ascending=False).head(1)
                if len(top):
                    st.caption(f"{t('top_gap')}: **{top.iloc[0]['name']}** · {pct(top.iloc[0]['share_any'])}")
                st.button(t("nav_market"), on_click=go, args=("market",), key="go_market", width="stretch")
    onboarding(compact=True)


def onboarding(compact: bool = False) -> None:
    steps = [(t("ob_key"), llm_label() is not None, t("ob_key_how")),
             (t("ob_cv"), PROFILE is not None, t("ob_cv_how")),
             (t("ob_data"), HAS_DATA, t("ob_data_how")),
             (t("ob_projects"), bool(STATE.projects), t("ob_projects_how"))]
    if all(ok for _, ok, _ in steps):
        return
    with st.expander(f"🧭 {t('onboarding')} · {sum(ok for _, ok, _ in steps)}/{len(steps)}", expanded=not compact):
        for title, ok, how in steps:
            st.markdown(f"{'✅' if ok else '⬜'} **{title}**" + ("" if ok else f" — {how}"))


# ============================================================================= PLAN: week
def day_html(d: date, blocks: list[orc.Block], capacity: float, done_entries: list[dict], titles: dict) -> str:
    is_today = d == TODAY
    head = f'<div class="wp-day {"today" if is_today else ""}">{weekday_short(d)} <span class="wp-muted">{short_date(d)}</span></div>'
    planned = sum(b.hours for b in blocks) + sum(float(e["hours"]) for e in done_entries)
    cap = capacity + (sum(float(e["hours"]) for e in done_entries) if is_today else 0)
    out = [head]
    if d >= TODAY:
        out.append(bar(planned / cap if cap else 0))
        out.append(f'<div class="wp-muted" style="font-size:.78rem">{t("free_of", p=fh(planned), c=fh(cap))}</div>')
    for e in done_entries:
        ttl, area, _ = titles.get(e["item"], (e["item"], "pessoal", ""))
        out.append(f'<div class="wp-block done">{AREA_ICON.get(area, "•")} {ttl}<div class="h">{fh(e["hours"])}</div></div>')
    for b in blocks:
        out.append(f'<div class="wp-block" style="border-left:3px solid {th.area_color(b.area)}">'
                   f'{AREA_ICON.get(b.area, "•")} {b.title}<div class="h">{fh(b.hours)}'
                   f'{" · " + b.project if b.project and b.project != b.title else ""}</div></div>')
    if not blocks and not done_entries:
        out.append(f'<div class="wp-muted" style="margin-top:8px">{t("past_day") if d < TODAY else t("nothing_day")}</div>')
    return "".join(out)


def page_week() -> None:
    page_header(f"🗓️ {t('week_title')}", t("week_sub"))
    which = st.segmented_control(" ", ["this", "next"], default="this", key="week_which",
                                 format_func=lambda x: t("this_week") if x == "this" else t("next_week"),
                                 label_visibility="collapsed") or "this"
    start = orc.week_start(TODAY) + timedelta(7 if which == "next" else 0)
    titles = item_titles()
    cols = st.columns(7, gap="small")
    for i, c in enumerate(cols):
        d = start + timedelta(i)
        sd = SCHED.day(d)
        done = [e for e in STATE.log if e["date"] == d.isoformat()]
        c.markdown(day_html(d, sd.blocks if sd else [], sd.capacity if sd else STATE.capacity(d), done, titles),
                   unsafe_allow_html=True)
    if which == "next":
        st.caption(t("next_week_note"))
    if SCHED.unscheduled_study > 0 and which == "this":
        st.warning(t("unscheduled_study", h=fh(SCHED.unscheduled_study)), icon="📚")

    st.markdown("&nbsp;")
    with st.container(key="card_availability"):
        st.markdown(f"**⏱️ {t('availability')}**")
        st.caption(t("availability_sub"))
        with st.form("availability"):
            cols = st.columns(7)
            vals = {}
            for i, c in enumerate(cols):
                vals[str(i)] = c.number_input(weekday_short(orc.week_start(TODAY) + timedelta(i)), 0.0, 16.0,
                                              float(STATE.availability.get(str(i), 0)), 0.5, key=f"av_{i}", format="%.1f")
            mb = st.number_input(t("max_block"), 0.5, 6.0, float(STATE.max_block), 0.5, format="%.1f")
            ov = pd.DataFrame([{"day": date.fromisoformat(k), "hours": v} for k, v in sorted(STATE.day_overrides.items())
                               if date.fromisoformat(k) >= TODAY], columns=["day", "hours"])
            st.markdown(f"*{t('overrides')}*")
            ov_ed = st.data_editor(ov, num_rows="dynamic", hide_index=True, width="stretch", key="ov_editor",
                                   column_config={"day": st.column_config.DateColumn(t("override_day"), min_value=TODAY,
                                                                                     format="DD/MM/YYYY" if lang() == "pt" else "YYYY-MM-DD"),
                                                  "hours": st.column_config.NumberColumn(t("override_hours"), min_value=0.0,
                                                                                         max_value=16.0, step=0.5)})
            if st.form_submit_button(t("save"), type="primary"):
                STATE.availability = vals
                STATE.max_block = mb
                keep = {k: v for k, v in STATE.day_overrides.items() if date.fromisoformat(k) < TODAY}
                for _, r in ov_ed.dropna().iterrows():
                    keep[pd.Timestamp(r["day"]).date().isoformat()] = float(r["hours"])
                STATE.day_overrides = keep
                save_state()
                st.toast(t("saved"), icon="✅")
                st.rerun()


# ============================================================================= PLAN: projects
def project_progress(p: orc.Project) -> tuple[float, float]:
    if p.tasks:
        total = sum(tk.hours for tk in p.tasks)
        done = sum(tk.hours if tk.done else min(STATE.logged(f"task:{tk.id}"), tk.hours) for tk in p.tasks)
    else:
        total = p.hours
        done = min(STATE.logged(f"proj:{p.id}"), p.hours)
    return round(done, 1), round(total, 1)


def page_projects() -> None:
    page_header(f"📁 {t('projects_title')}", t("projects_sub"))
    active = [p for p in STATE.projects if not p.archived]
    with st.expander(f"➕ {t('new_project')}", expanded=not active):
        with st.form("new_project", clear_on_submit=True):
            name = st.text_input(t("p_name"), placeholder=t("p_name_ph"))
            c1, c2, c3 = st.columns(3)
            area = c1.selectbox(t("p_area"), orc.AREAS, format_func=area_label)
            prio = c2.selectbox(t("p_priority"), [1, 2, 3], index=1, format_func=lambda x: t(f"prio_{x}"))
            hrs = c3.number_input(t("p_hours"), 0.0, 400.0, 8.0, 0.5, help=t("p_hours_help"))
            c4, c5 = st.columns([1, 2])
            has_dl = c4.checkbox(t("p_has_deadline"), value=True)
            dl = c5.date_input(t("p_deadline"), value=TODAY + timedelta(7), min_value=TODAY,
                               format="DD/MM/YYYY" if lang() == "pt" else "YYYY-MM-DD")
            notes = st.text_area(t("p_notes"), height=80)
            brk = st.checkbox(t("p_breakdown"), value=True, help=t("p_breakdown_help"))
            if st.form_submit_button(t("p_create"), type="primary"):
                if not name.strip():
                    st.error(t("p_name_required"))
                else:
                    p = orc.Project(id=orc.new_id(), name=name.strip(), area=area, priority=prio,
                                    deadline=dl.isoformat() if has_dl else None, hours=hrs, notes=notes)
                    if brk:
                        with st.spinner("…"):
                            p.tasks = orc.breakdown_tasks(p.name, area, p.deadline, notes, hrs, client=llm_client(), lang=lang())
                    STATE.projects.append(p)
                    save_state()
                    st.toast(t("p_created", name=p.name), icon="📁")
                    st.rerun()
    if not active:
        st.info(t("p_empty"), icon="📁")
    key_order = lambda p: (p.deadline or "9999", p.priority)  # noqa: E731
    for p in sorted(active, key=key_order):
        project_card(p)
    archived = [p for p in STATE.projects if p.archived]
    if archived:
        with st.expander(t("p_archived", n=len(archived))):
            for p in archived:
                c1, c2 = st.columns([4, 1])
                c1.markdown(f"{area_label(p.area)} · **{p.name}**")
                if c2.button(t("p_unarchive"), key=f"unarch_{p.id}"):
                    p.archived = False
                    save_state()
                    st.rerun()


def project_card(p: orc.Project) -> None:
    done, total = project_progress(p)
    with st.container(key=f"card_proj_{p.id}"):
        c1, c2 = st.columns([5, 1.3])
        c1.markdown(f'{dot(th.area_color(p.area))}<span class="wp-muted">{area_label(p.area)} · {t("prio_" + str(p.priority))}</span>'
                    f'<br><span style="font-size:1.15rem;font-weight:700">{p.name}</span> &nbsp;'
                    f'{due_chip(p.deadline) if p.deadline else "<span class=wp-muted>" + t("p_no_deadline") + "</span>"}',
                    unsafe_allow_html=True)
        c1.markdown(bar(done / total if total else 0), unsafe_allow_html=True)
        c1.caption(t("p_progress", done=fh(done), total=fh(total)))
        with c2.popover(f"⋯ {t('p_edit')}", width="stretch"):
            with st.form(f"edit_{p.id}"):
                nm = st.text_input(t("p_name"), p.name)
                ar = st.selectbox(t("p_area"), orc.AREAS, index=orc.AREAS.index(p.area) if p.area in orc.AREAS else 0,
                                  format_func=area_label)
                pr = st.selectbox(t("p_priority"), [1, 2, 3], index=p.priority - 1, format_func=lambda x: t(f"prio_{x}"))
                hd = st.checkbox(t("p_has_deadline"), value=bool(p.deadline))
                dl = st.date_input(t("p_deadline"), value=date.fromisoformat(p.deadline) if p.deadline else TODAY + timedelta(7),
                                   format="DD/MM/YYYY" if lang() == "pt" else "YYYY-MM-DD")
                hr = st.number_input(t("p_hours"), 0.0, 400.0, float(p.hours), 0.5)
                nt = st.text_area(t("p_notes"), p.notes, height=70)
                if st.form_submit_button(t("save"), type="primary"):
                    p.name, p.area, p.priority, p.hours, p.notes = nm.strip() or p.name, ar, pr, hr, nt
                    p.deadline = dl.isoformat() if hd else None
                    save_state()
                    st.toast(t("saved"), icon="✅")
                    st.rerun()
            b1, b2 = st.columns(2)
            if b1.button(t("p_archive"), key=f"arch_{p.id}", width="stretch"):
                p.archived = True
                save_state()
                st.rerun()
            if st.session_state.get("confirm_del") == p.id:
                st.warning(t("p_delete_confirm", name=p.name))
                y, n = st.columns(2)
                if y.button(t("confirm"), key=f"del_yes_{p.id}", type="primary"):
                    STATE.projects = [x for x in STATE.projects if x.id != p.id]
                    ids = {f"proj:{p.id}"} | {f"task:{tk.id}" for tk in p.tasks}
                    STATE.log = [e for e in STATE.log if e["item"] not in ids]
                    save_state()
                    st.session_state.pop("confirm_del", None)
                    st.toast(t("p_deleted"), icon="🗑️")
                    st.rerun()
                if n.button(t("cancel"), key=f"del_no_{p.id}"):
                    st.session_state.pop("confirm_del", None)
                    st.rerun()
            elif b2.button(t("delete"), key=f"del_{p.id}", width="stretch"):
                st.session_state["confirm_del"] = p.id
                st.rerun()
        with st.expander(f"{t('p_tasks')} ({sum(1 for x in p.tasks if x.done)}/{len(p.tasks)})" if p.tasks else t("p_tasks")):
            df = pd.DataFrame([{"id": tk.id, "title": tk.title, "hours": tk.hours,
                                "due": date.fromisoformat(tk.due) if tk.due else None, "done": tk.done,
                                "logged": round(STATE.logged(f"task:{tk.id}"), 1)} for tk in p.tasks],
                              columns=["id", "title", "hours", "due", "done", "logged"])
            ed = st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key=f"tasks_{p.id}",
                                column_config={"id": None,
                                               "title": st.column_config.TextColumn(t("t_title"), width="large", required=True),
                                               "hours": st.column_config.NumberColumn(t("t_hours"), min_value=0.5, max_value=200.0, step=0.5),
                                               "due": st.column_config.DateColumn(t("t_due"), format="DD/MM/YYYY" if lang() == "pt" else "YYYY-MM-DD"),
                                               "done": st.column_config.CheckboxColumn(t("t_done")),
                                               "logged": st.column_config.NumberColumn(t("t_logged"), disabled=True)})
            if st.button(t("p_save_tasks"), key=f"save_tasks_{p.id}"):
                new_tasks = []
                for _, r in ed.iterrows():
                    if not str(r.get("title") or "").strip():
                        continue
                    due = r.get("due")
                    new_tasks.append(orc.Task(id=r["id"] if isinstance(r.get("id"), str) and r["id"] else orc.new_id(),
                                              title=str(r["title"]).strip(), hours=float(r.get("hours") or 1.0),
                                              due=pd.Timestamp(due).date().isoformat() if due is not None and not pd.isna(due) else None,
                                              done=bool(r.get("done"))))
                p.tasks = new_tasks
                save_state()
                st.toast(t("saved"), icon="✅")
                st.rerun()


# ============================================================================= PLAN: study plan
def page_plan() -> None:
    page_header(f"📚 {t('plan_title')}")
    f = cfg.focus
    w = f.get("weights", {})
    with st.expander(f"⚖️ {t('focus_weights')}", expanded=PLAN is None):
        st.caption(t("focus_help"))
        c1, c2, c3, c4 = st.columns(4)
        hrs = c1.number_input(t("hours_week"), 1.0, 80.0, float(f.get("weekly_hours", 10)), 0.5)
        wc = c2.slider(f"🧭 {t('area_carreira')}", 0, 100, int(w.get("carreira", 50)))
        we = c3.slider(f"🧪 {t('area_exploracao')}", 0, 100, int(w.get("exploracao", 30)))
        wi = c4.slider(f"🎸 {t('area_interesses')}", 0, 100, int(w.get("interesses", 20)))
        topics = st.text_input(t("explore_topics"), ", ".join(f.get("exploration", {}).get("topics") or []))
        interests = st.text_input(t("interests"), ", ".join(f.get("interests") or []), help=t("interests_help"))
        protected = st.checkbox(t("protect_explore"), value=bool(f.get("exploration", {}).get("protected", True)))
        tot = wc + we + wi
        if tot != 100:
            st.caption("ℹ️ " + t("weights_sum", s=tot))
        if st.button(t("save_focus"), key="save_focus"):
            tot = tot or 1
            nc, ne = round(wc * 100 / tot), round(we * 100 / tot)
            save_local(cfg.paths.config, "focus", {
                "weekly_hours": hrs, "weights": {"carreira": nc, "exploracao": ne, "interesses": 100 - nc - ne},
                "exploration": {"protected": protected, "topics": [x.strip() for x in topics.split(",") if x.strip()],
                                "include_emerging": f.get("exploration", {}).get("include_emerging", True)},
                "interests": [x.strip() for x in interests.split(",") if x.strip()]})
            st.toast(t("focus_saved"), icon="✅")

    if not HAS_DATA:
        st.info(t("plan_needs_data"), icon="📊")
        return
    c1, c2 = st.columns([1, 3])
    ideas = c2.checkbox(t("gen_plan_ai"), value=llm_client() is not None)
    if c1.button(t("gen_plan"), type="primary", key="gen_plan"):
        with st.spinner(t("plan_generating")):
            pl.save_plan(cfg, pl.make_plan(cfg, A, pl.compute_gap(cfg, A), client=llm_client() if ideas else None,
                                           lang=lang()), lang=lang())
        st.rerun()
    plan = PLAN
    if plan is None:
        return
    if plan.get("lang", "pt") != lang():
        st.caption("🌐 " + t("plan_lang_mismatch"))
    h = plan.get("hours", {})
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(t("hours_week"), fh(plan.get("weekly_hours", 0)))
    m2.metric(f"🧭 {t('area_carreira')}", fh(h.get("carreira", 0)))
    m3.metric(f"🧪 {t('area_exploracao')}" + (" 🔒" if plan.get("protected_exploration") else ""),
              fh(h.get("exploracao", 0)), help=t("focus_help"))
    m4.metric(f"🎸 {t('area_interesses')}", fh(h.get("interesses", 0)))
    when = str(plan.get("generated_at", ""))[:16].replace("T", " ")
    st.caption(t("generated_at", when=when))

    with st.container(key="card_studyweek"):
        st.markdown(f"**{t('study_week')}**")
        st.caption(t("study_week_help"))
        ws = orc.week_start(TODAY)
        for it in plan.get("this_week", []):
            foco = orc.STUDY_FOCUS_KEY.get(it.get("foco", ""), "carreira")
            iid = it.get("id") or f"study:{foco}:{it.get('item')}"
            got = STATE.logged(iid, since=ws)
            planned = float(it.get("horas") or 0)
            c1, c2 = st.columns([3, 2])
            c1.markdown(f'{dot(th.area_color(foco))}{AREA_ICON.get(foco, "")} **{it.get("item")}** '
                        f'<span class="wp-muted">· {t("area_" + foco)}</span>', unsafe_allow_html=True)
            c2.markdown(f'<span class="wp-muted">{fh(got)} / {fh(planned)}</span>' + bar(got / planned if planned else 0),
                        unsafe_allow_html=True)

    st.markdown(f"### {t('career_prios')}")
    st.caption(t("career_prios_help"))
    career = plan.get("career") or []
    for row in range(0, len(career), 3):
        cols = st.columns(3)
        for c, item in zip(cols, career[row:row + 3]):
            with c.container(key=f"card_career_{item['skill_id']}"):
                st.markdown(f"**{item['name']}**")
                st.caption(t("you_status", s=t("status_" + item["status"]), h=fh(item["effort_hours"])))
                st.write(item["why"])
                if item.get("pairs_with"):
                    st.caption(t("pairs", x=", ".join(item["pairs_with"])))

    if plan.get("projects"):
        st.markdown(f"### {t('suggested_projects')}")
        st.caption(t("suggested_projects_help"))
        existing = {p.name for p in STATE.projects}
        for i, p in enumerate(plan["projects"]):
            with st.expander(p["title"]):
                st.write(p["description"])
                if p.get("deliverable"):
                    st.markdown(f"**{t('deliverable')}:** {p['deliverable']}")
                st.markdown(pills(p.get("skills") or []), unsafe_allow_html=True)
                if p.get("bridge_interest"):
                    st.caption(t("bridge_with", x=p["bridge_interest"]))
                if st.button(f"➕ {t('add_to_projects')}", key=f"plan_proj_{i}", disabled=p["title"] in existing):
                    np_ = orc.Project(id=orc.new_id(), name=p["title"], area="carreira", priority=2, hours=20.0,
                                      notes=p.get("description", ""))
                    np_.tasks = orc.breakdown_tasks(np_.name, "carreira", None, np_.notes, 20.0, client=llm_client(), lang=lang())
                    STATE.projects.append(np_)
                    save_state()
                    st.toast(t("p_created", name=np_.name), icon="📁")
                    st.rerun()
    cA, cB = st.columns(2)
    with cA.container(key="card_explore"):
        st.markdown(f"**🧪 {t('exploration')}**")
        for e in plan.get("exploration") or []:
            st.markdown(f"- **{e['name']}**" + (f" — {e['why']}" if e.get("why") else ""))
        if not plan.get("exploration"):
            st.caption(t("explore_empty"))
    with cB.container(key="card_interests"):
        st.markdown(f"**🎸 {t('interests_bridges')}**")
        for b in plan.get("bridges") or []:
            st.markdown(f"- **{b['interest']}** → {b['idea']}")
        if not plan.get("bridges"):
            for i in plan.get("interests") or []:
                st.markdown(f"- {i['name']} — {fh(i['horas'])}")
            if not plan.get("interests"):
                st.caption(t("interests_empty"))
    if plan.get("tradeoffs"):
        with st.container(key="card_tradeoffs"):
            st.markdown(f"**⚖️ {t('tradeoffs')}**")
            for x in plan["tradeoffs"]:
                st.markdown(f"- {x}")
    for n in plan.get("notes") or []:
        st.info(n, icon="💡")


# ============================================================================= MARKET
def no_market() -> bool:
    if not HAS_DATA:
        st.info(t("no_data_market"), icon="📊")
        return True
    return False


def jobs_asking(skill_id: str, jobs_df: pd.DataFrame, skills_df: pd.DataFrame) -> pd.DataFrame:
    s = skills_df[skills_df["skill_id"] == skill_id][["job_key", "requirement"]].drop_duplicates("job_key")
    j = jobs_df.merge(s, on="job_key")
    return pd.DataFrame({
        t("company"): j["company"], t("title"): j["title"], t("role"): j["role"].map(role_label),
        t("how_asked"): j["requirement"].map({"required": t("required"), "nice_to_have": t("nice")}),
        t("region"): j["region"].map(region), t("link"): j["url"]})


def page_market() -> None:
    page_header(f"📊 {t('market_title')}")
    if no_market():
        return
    opts = ["__all__"] + list(cfg.roles)
    role = st.pills(t("role"), opts, default="__all__", key="mk_role",
                    format_func=lambda r: t("all") if r == "__all__" else role_label(r)) or "__all__"
    if role != "__all__":
        st.markdown(f'<span class="wp-muted">{role_field(cfg.roles[role], "summary") or ""}</span>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.4, 1])
    regions = sorted(A.jobs_df["region"].dropna().unique())
    reg = c1.selectbox(t("region"), ["__all__"] + regions, format_func=lambda x: t("all_regions") if x == "__all__" else region(x))
    sens = c2.multiselect(t("seniority"), list(SENIORITY["pt"]), format_func=seniority, placeholder=t("any"))
    top = c3.slider(t("how_many_skills"), 10, 40, 20)
    j, s = market.filter_frames(A.jobs_df, A.skills_df, role=None if role == "__all__" else role,
                                region=None if reg == "__all__" else reg, seniorities=sens or None)
    tbl = market.skill_table(j, s)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric(t("m_jobs"), len(j))
    m2.metric(t("m_companies"), j["company"].nunique())
    m3.metric(t("m_skills"), tbl["skill_id"].nunique())
    m4.metric(t("m_remote"), pct((j["work_model"] == "remote").mean()) if len(j) else "—")
    if len(j) == 0:
        st.warning(t("no_jobs_filter"))
        return
    if role != "__all__" and len(j) < MIN_ROLE_JOBS:
        st.warning(t("few_jobs_role", n=len(j)), icon="⚠️")
    st.markdown(f"### {t('top_skills')}")
    st.caption(t("top_skills_help"))
    ch, hgt = chart_skills(tbl, top, select=True)
    ev = st.altair_chart(ch, width="stretch", height=hgt, on_select="rerun",
                         key=f"mk_chart_{role}_{reg}_{'-'.join(sens)}_{top}_{lang()}_{th.CURRENT['name']}")
    picked = None
    try:
        sel = (ev or {}).get("selection", {}).get("skill") or []
        picked = sel[0].get("skill_id") if sel else None
    except (AttributeError, IndexError, TypeError):
        picked = None
    names = dict(zip(tbl["skill_id"], tbl["name"]))
    ids = [i for i in tbl["skill_id"] if not i.startswith("other:")][:top]
    picked = st.selectbox(t("see_jobs_asking"), ids, index=ids.index(picked) if picked in ids else 0, format_func=names.get)
    if picked:
        rows = jobs_asking(picked, j, s)
        st.dataframe(rows, hide_index=True, width="stretch", height=min(38 * (len(rows) + 1), 320),
                     column_config={t("link"): st.column_config.LinkColumn(display_text=t("open"))})
        pairs = market.cooccurrence(s, picked, top=5)
        if pairs:
            st.caption(t("pairs", x=", ".join(pairs)))
    cA, cB = st.columns(2)
    with cA:
        st.markdown(f"### {t('seniority')}")
        d = market.distribution(j, "seniority")
        d["lvl"] = d["seniority"].map(seniority)
        order = [seniority(k) for k in SENIORITY["pt"]] + [t("not_informed")]
        chs = alt.Chart(d).mark_bar(cornerRadiusEnd=4, color=TOK["primary"]).encode(
            y=alt.Y("lvl:N", sort=order, title=None), x=alt.X("n:Q", title=t("m_jobs")),
            tooltip=[alt.Tooltip("lvl:N", title=t("level")), alt.Tooltip("n:Q", title=t("m_jobs")),
                     alt.Tooltip("share:Q", format=".0%")])
        st.altair_chart(th.style(chs), width="stretch")
    with cB:
        st.markdown(f"### {t('trends')}")
        if A.trends.empty:
            st.caption(t("trends_empty"))
        else:
            tt = A.trends.head(10)
            st.dataframe(pd.DataFrame({"Skill": tt["name"], t("recent"): (tt["share_recent"] * 100).round(0),
                                       t("older"): (tt["share_older"] * 100).round(0), "Δ p.p.": tt["delta_pp"].round(1)}),
                         hide_index=True, width="stretch")
    with st.expander(t("br_vs_intl")):
        rc = A.region_cmp
        regs = [c for c in rc.columns if c in ("BR", "REMOTE_BR_OK", "INTL")]
        show = rc[["name"] + regs].rename(columns={"name": "Skill", **{r: region(r) for r in regs}})
        st.dataframe(show.style.format({c: "{:.0%}" for c in show.columns if c != "Skill"}), hide_index=True, width="stretch")
    with st.expander(t("full_table")):
        st.dataframe(pd.DataFrame({"Skill": tbl["name"], t("category"): tbl["category"],
                                   t("share_postings"): (tbl["share_any"] * 100).round(0),
                                   t("required"): (tbl["share_required"] * 100).round(0),
                                   t("nice"): (tbl["share_nice"] * 100).round(0), t("n_postings"): tbl["n_any"]}),
                     hide_index=True, width="stretch")


def page_compare() -> None:
    page_header(f"⚖️ {t('compare_title')}")
    if no_market():
        return
    counts = A.jobs_df["role"].value_counts()
    with_data = sorted([r for r in cfg.roles if counts.get(r, 0)], key=lambda r: -counts[r])
    if len(with_data) < 2:
        st.info(t("compare_need2"))
        return
    chosen = st.multiselect(t("compare_pick"), with_data, default=with_data[:3], max_selections=3,
                            format_func=role_label, placeholder=t("compare_ph"))
    if len(chosen) < 2:
        st.caption(t("pick_two"))
        return
    tables = {r: A.tables[r] for r in chosen}
    cols = st.columns(len(chosen))
    for c, r in zip(cols, chosen):
        jr = A.jobs_df[A.jobs_df["role"] == r]
        with c.container(key=f"card_cmp_{r}"):
            st.markdown(f"{dot(role_color(r))}**{role_label(r)}**", unsafe_allow_html=True)
            st.caption(role_field(cfg.all_roles[r], "summary") or "")
            if len(jr) < MIN_ROLE_JOBS:
                st.warning(t("few_jobs_role", n=len(jr)), icon="⚠️")
            a1, a2 = st.columns(2)
            a1.metric(t("m_jobs"), len(jr))
            a2.metric(t("entry_level"), pct(jr["seniority"].isin(["intern", "junior"]).mean() if len(jr) else 0))
            if LEVELS:
                st.metric(t("fit_label"), pct(market_fit(gap_table(tables[r], LEVELS))))
            others = set().union(*[set(tables[o]["skill_id"].head(25)) for o in chosen if o != r])
            own = tables[r][~tables[r]["skill_id"].isin(others) & ~tables[r]["skill_id"].str.startswith("other:")].head(5)
            st.markdown(f"**{t('typical')}:**<br>" + pills(own["name"].tolist()), unsafe_allow_html=True)
    union: list[str] = []
    names: dict[str, str] = {}
    for r in chosen:
        tt = tables[r][~tables[r]["skill_id"].str.startswith("other:")]
        names.update(zip(tt["skill_id"], tt["name"]))
        for sid in tt["skill_id"].head(10):
            if sid not in union:
                union.append(sid)
    rows = []
    for r in chosen:
        share = tables[r].set_index("skill_id")["share_any"]
        for sid in union:
            rows.append({"role": role_label(r), "Skill": names[sid], "share": float(share.get(sid, 0.0))})
    d = pd.DataFrame(rows)
    order = d.groupby("Skill")["share"].max().sort_values(ascending=False).index.tolist()
    st.markdown(f"### {t('same_skills')}")
    st.caption(t("same_skills_help"))
    labels = [role_label(r) for r in chosen]
    enc_y = alt.Y("Skill:N", sort=order, title=None, axis=alt.Axis(labelLimit=220, labelOverlap=False))
    rng = alt.Chart(d).mark_rule(color=TOK["grid"], strokeWidth=2).encode(
        y=enc_y, x=alt.X("min(share):Q", title=t("share_postings"), axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
        x2="max(share):Q")
    dots = alt.Chart(d).mark_point(filled=True, size=110, opacity=1, stroke=TOK["bg"], strokeWidth=2).encode(
        y=enc_y, x="share:Q",
        color=alt.Color("role:N", scale=alt.Scale(domain=labels, range=[role_color(r) for r in chosen]),
                        legend=alt.Legend(title=None)),
        tooltip=[alt.Tooltip("role:N", title=t("role")), "Skill", alt.Tooltip("share:Q", format=".0%", title=t("share_postings"))])
    h = 28 * len(order) + 20
    st.altair_chart(th.style((rng + dots).properties(height=h)), width="stretch", height=h + 70)
    with st.expander(t("as_table")):
        wide = d.pivot_table(index="Skill", columns="role", values="share").reindex(order)
        st.dataframe(wide.style.format("{:.0%}"), width="stretch")


def page_jobs() -> None:
    page_header(f"💼 {t('jobs_title')}")
    if HAS_DATA:
        j, s = A.jobs_df, A.skills_df
        c1, c2, c3, c4 = st.columns([1.6, 1.2, 1, 1])
        q = c1.text_input(t("search"), placeholder=t("search_ph"))
        roles = c2.multiselect(t("role"), list(cfg.roles), format_func=role_label, placeholder=t("all"))
        reg = c3.selectbox(t("region"), ["__all__"] + sorted(j["region"].dropna().unique()),
                           format_func=lambda x: t("all_regions") if x == "__all__" else region(x), key="jb_region")
        sens = c4.multiselect(t("seniority"), list(SENIORITY["pt"]), format_func=seniority, placeholder=t("any"), key="jb_sen")
        tax = s[~s["skill_id"].str.startswith("other:")].drop_duplicates("skill_id").set_index("skill_id")["name"]
        need = st.multiselect(t("that_ask"), tax.index.tolist(), format_func=tax.get, placeholder=t("whatever"))
        m = pd.Series(True, index=j.index)
        if q:
            m &= j["title"].str.contains(q, case=False, regex=False) | j["company"].str.contains(q, case=False, regex=False)
        if roles:
            m &= j["role"].isin(roles)
        if reg != "__all__":
            m &= j["region"] == reg
        if sens:
            m &= j["seniority"].isin(sens)
        for sid in need:
            m &= j["job_key"].isin(s.loc[s["skill_id"] == sid, "job_key"])
        jj = j[m].sort_values("published_at", ascending=False, na_position="last").reset_index(drop=True)
        st.caption(t("n_jobs_click", n=len(jj)))
        view = pd.DataFrame({
            t("company"): jj["company"], t("title"): jj["title"], t("role"): jj["role"].map(role_label),
            t("level"): jj["seniority"].map(seniority), t("region"): jj["region"].map(region),
            t("published"): jj["published_at"].dt.strftime("%d/%m/%Y" if lang() == "pt" else "%Y-%m-%d").fillna("—"),
            t("link"): jj["url"]})
        ev = st.dataframe(view, hide_index=True, width="stretch", height=380, on_select="rerun",
                          selection_mode="single-row", key="jobs_table",
                          column_config={t("link"): st.column_config.LinkColumn(display_text=t("open"))})
        rows = (ev or {}).get("selection", {}).get("rows", []) if ev else []
        if rows and rows[0] < len(jj):
            jr = jj.iloc[rows[0]]
            job = db.job(jr["job_key"])
            js = s[s["job_key"] == jr["job_key"]]
            with st.container(key="card_jobdetail"):
                st.markdown(f"### {jr['title']} — {jr['company']}")
                st.caption(f"{role_label(jr['role'])} · {seniority(jr['seniority'])} · {region(jr['region'])} · "
                           f"{t('source')}: {jr['source']}")
                req = js[js["requirement"] == "required"]["name"].tolist()
                nice = js[js["requirement"] == "nice_to_have"]["name"].tolist()
                if req:
                    st.markdown(f"**{t('required_pl')}:** " + pills(req), unsafe_allow_html=True)
                if nice:
                    st.markdown(f"**{t('nice_pl')}:** " + pills(nice), unsafe_allow_html=True)
                if LEVELS:
                    miss = [n for sid, n in zip(js["skill_id"], js["name"]) if not sid.startswith("other:") and LEVELS.get(sid, 0) < 2]
                    st.caption(t("you_miss", x=", ".join(miss) if miss else t("you_miss_none")))
                if jr["url"]:
                    st.link_button(t("open_job"), jr["url"])
                if job:
                    with st.expander(t("full_text")):
                        st.text(job.text[:8000])
    else:
        no_market()
    with st.expander(f"➕ {t('paste_job')}"):
        with st.form("manual", clear_on_submit=True):
            c1, c2 = st.columns(2)
            ti = c1.text_input(t("title"))
            co = c2.text_input(t("company"))
            u = st.text_input(t("link_opt"))
            body = st.text_area(t("job_text"), height=200)
            if st.form_submit_button(t("add")) and body.strip():
                status, job = add_manual(cfg, db, body, title=ti, company=co, url=u)
                st.toast(t("job_added", s=status, t=job.title), icon="✅")


def page_roles() -> None:
    page_header(f"🎯 {t('roles_title')}", t("roles_sub"))
    counts = pd.Series([j.role for j in db.jobs()]).value_counts().to_dict() if db.count_jobs() else {}
    enabled_now = set(cfg.roles)
    custom = dict(cfg.targets.get("custom_roles") or {})
    for rid, r in cfg.all_roles.items():
        with st.container(key=f"card_role_{rid}"):
            c1, c2 = st.columns([5, 1])
            with c1:
                st.markdown(f"{dot(role_color(rid))}**{r.get('label', rid)}** "
                            f"<span class='wp-muted'>· {t('in_db', n=counts.get(rid, 0))}</span>", unsafe_allow_html=True)
                st.caption(role_field(r, "summary") or "")
            c2.toggle(t("active"), value=rid in enabled_now, key=f"role_on_{rid}")
            with st.expander(t("what_they_do")):
                st.write(role_field(r, "description") or "")
                dd = role_field(r, "day_to_day") or []
                if dd:
                    st.markdown(f"**{t('day_to_day')}:**\n" + "\n".join(f"- {x}" for x in dd))
                ts = role_field(r, "typical_skills") or []
                if ts:
                    st.markdown(f"**{t('typical_skills')}:** " + pills(ts), unsafe_allow_html=True)
                st.caption(t("searches_for", x=", ".join(r.get("search_terms") or [])))
                if rid in custom and st.button(t("remove_custom"), key=f"rm_{rid}"):
                    custom.pop(rid)
                    save_local(cfg.paths.config, "targets", {"custom_roles": custom,
                                                             "roles_enabled": [x for x in cfg.roles if x != rid]})
                    st.rerun()
    if st.button(t("save_roles"), type="primary", key="save_roles"):
        chosen = [rid for rid in cfg.all_roles if st.session_state.get(f"role_on_{rid}")]
        if not chosen:
            st.error(t("roles_none"))
        else:
            save_local(cfg.paths.config, "targets", {"roles_enabled": chosen})
            n = reassign_roles(load_config(), db)
            st.cache_data.clear()
            st.success(t("roles_saved", n=len(chosen), m=n))
    with st.container(key="card_newrole"):
        st.markdown(f"**{t('custom_role')}**")
        st.caption(t("custom_role_help"))
        with st.form("new_role", clear_on_submit=True):
            name = st.text_input(t("role_name"))
            if st.form_submit_button(t("add_role")) and name.strip():
                rid, role = make_custom_role(name)
                custom[rid] = role
                save_local(cfg.paths.config, "targets", {"custom_roles": custom, "roles_enabled": [*cfg.roles, rid]})
                st.toast(t("role_created", n=name), icon="🎯")
                st.rerun()


# ============================================================================= YOU
def render_role_fit() -> None:
    fit = pl.role_fit(cfg, A)
    d = pd.DataFrame([{"role": role_label(r), "fit": v, "n": int((A.jobs_df["role"] == r).sum())} for r, v in fit.items()],
                     columns=["role", "fit", "n"])
    few = d[d["n"] < MIN_ROLE_JOBS]
    d = d[d["n"] >= MIN_ROLE_JOBS].sort_values("fit", ascending=False)
    if len(d):
        ch, hgt = chart_hbar(d, "role", "fit", domain_max=1.1)
        st.altair_chart(ch, width="stretch", height=hgt)
        st.caption(t("closest", r=d.iloc[0]["role"], v=pct(d.iloc[0]["fit"])))
    if len(few):
        st.caption(t("few_roles", n=MIN_ROLE_JOBS, x=", ".join(f"{r.role} ({r.n})" for r in few.itertuples())))


def page_profile() -> None:
    page_header(f"👤 {t('profile_title')}")
    with st.container(key="card_resume"):
        st.markdown(f"**{t('resume')}**")
        st.caption(t("resume_privacy"))
        c1, c2 = st.columns([2, 1])
        up = c1.file_uploader(t("resume_file"), type=["pdf", "docx", "md", "txt"])
        use_llm = c2.checkbox(t("use_ai_levels"), value=llm_client() is not None)
        if PROFILE:
            c2.caption(t("current_profile", n=len(PROFILE.skills), m=PROFILE.method))
        if up and c2.button(t("read_resume"), type="primary"):
            dest = cfg.paths.profile / up.name
            dest.write_bytes(up.getvalue())
            with st.spinner(t("reading")):
                prof = build_profile(dest, cfg.paths.profile, client=llm_client() if use_llm else None)
            st.toast(t("skills_found", n=len(prof.skills), m=prof.method), icon="✅")
            st.rerun()
    if HAS_DATA and LEVELS:
        with st.container(key="card_rolefit"):
            st.markdown(f"**{t('fit_by_role')}**")
            render_role_fit()
        st.markdown(f"### {t('fit_gaps')}")
        opts = ["foco"] + [r for r in cfg.roles if len(A.tables.get(r, []))]
        which = st.pills(t("compare_with"), opts, default="foco", key="pf_role",
                         format_func=lambda r: t("all_roles_focus") if r == "foco" else role_label(r)) or "foco"
        tbl = A.focus_table if which == "foco" else A.tables[which]
        gap = gap_table(tbl, LEVELS)
        a1, a2, a3 = st.columns(3)
        a1.metric(t("fit_label"), pct(market_fit(gap)), help=t("fit_help"))
        a2.metric(t("covered"), int((gap["status"] == "has").sum()))
        a3.metric(t("gaps"), int((gap["status"] != "has").sum()))
        st.dataframe(pd.DataFrame({
            "Skill": gap["name"], t("asked_in"): (gap["share_any"] * 100).round(0).astype(int).astype(str) + "%",
            t("your_level"): gap["level"], t("status"): gap["status"].map(lambda x: t("status_" + x)),
            t("priority"): gap["priority"].round(3), t("est_hours"): gap["effort_hours"]}),
            hide_index=True, width="stretch", height=380,
            column_config={t("priority"): st.column_config.ProgressColumn(min_value=0, max_value=float(max(gap["priority"].max(), 0.01)), format="%.2f")})
    elif HAS_DATA:
        st.caption(t("send_cv_fit"))
    if PROFILE:
        st.markdown(f"### {t('your_levels')}")
        st.caption(t("levels_help"))
        df = pd.DataFrame([{"skill_id": s.skill_id, "Skill": s.name, "lvl": LEVELS.get(s.skill_id, s.level),
                            "ev": s.evidence or ""} for s in PROFILE.skills])
        if HAS_DATA:
            known = set(df["skill_id"])
            extra = A.focus_table[~A.focus_table["skill_id"].isin(known) & ~A.focus_table["skill_id"].str.startswith("other:")].head(15)
            df = pd.concat([df, pd.DataFrame([{"skill_id": r.skill_id, "Skill": r.name, "lvl": LEVELS.get(r.skill_id, 0),
                                               "ev": t("asked_by_market")} for r in extra.itertuples()])])
        edited = st.data_editor(df, hide_index=True, width="stretch", key="levels", column_config={
            "skill_id": None, "lvl": st.column_config.NumberColumn(t("level"), min_value=0, max_value=3, step=1),
            "ev": st.column_config.TextColumn(t("evidence"))}, disabled=["Skill", "ev"])
        if st.button(t("save_levels"), key="save_levels"):
            base = PROFILE.levels()
            ov = {r["skill_id"]: int(r["lvl"]) for _, r in edited.iterrows() if base.get(r["skill_id"], 0) != int(r["lvl"])}
            save_overrides(cfg.paths.profile, ov)
            st.toast(t("levels_saved"), icon="✅")
            st.rerun()


def page_report() -> None:
    page_header(f"📝 {t('report_title')}")
    if no_market():
        return
    numbers = post_numbers(A.jobs_df, A.tables, cfg.roles)
    st.caption(t("post_draft"))
    st.text_area(t("post"), linkedin_post_draft(numbers), height=320)
    c1, c2 = st.columns(2)
    model = db.conn.execute("SELECT model FROM extractions WHERE extractor=? LIMIT 1", (A.extractor,)).fetchone()
    model = model[0] if model else A.extractor
    if c1.button(t("public_report"), key="rep_pub"):
        files = pl.make_report(cfg, A, gap=None, plan=None, model=model, public=True)
        st.success(t("saved_in", p=files["report"].parent))
        for p in files.values():
            if Path(p).suffix == ".png":
                st.image(str(p))
    if c2.button(t("private_report"), key="rep_priv"):
        gap = pl.compute_gap(cfg, A)
        files = pl.make_report(cfg, A, gap=gap, plan=pl.make_plan(cfg, A, gap), model=model)
        st.success(t("saved_in", p=files["report"]))
    with st.expander(t("numbers_json")):
        st.json(numbers, expanded=False)


# ============================================================================= main
sidebar()
{
    "today": page_today, "week": page_week, "projects": page_projects, "plan": page_plan, "market": page_market,
    "compare": page_compare, "jobs": page_jobs, "roles": page_roles, "profile": page_profile, "report": page_report,
}.get(st.session_state.get("page", "today"), page_today)()
