"""Waypoint local app: a small JSON API over the engine + the static interface.

Runs only on 127.0.0.1. Started by the desktop shortcut (see launcher.py) or `waypoint ui`.
Every response is computed from local files (data/, profile/, config/); nothing leaves the machine
except the LLM calls the engine already makes.
"""
from __future__ import annotations

import math
import os
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import orchestrator as orc
from .. import pipeline as pl
from .. import updater
from ..analysis import market
from ..analysis.gap import gap_table, market_fit
from ..collect import add_manual, reassign_roles
from ..db import DB
from ..llm import LLMNotConfigured, config_from_env, make_client
from ..profile import build_profile, effective_levels, load_profile, save_overrides
from ..report import linkedin_post_draft, post_numbers
from ..settings import load_config, make_custom_role, save_local

STATIC = Path(__file__).parent / "static"
MIN_ROLE_JOBS = 10
_lock = threading.RLock()
_cache: dict[str, Any] = {"key": None, "analysis": None}


# ============================================================================= helpers
def today() -> date:
    v = os.environ.get("WAYPOINT_TODAY")
    return date.fromisoformat(v) if v else date.today()


def ctx():
    cfg = load_config()
    cfg.paths.ensure()
    return cfg, DB(cfg.paths.db)


def lang(cfg) -> str:
    return updater.load_ui_settings(cfg).get("lang", "pt")


def clean(v: Any) -> Any:
    """Make pandas/numpy values JSON-safe."""
    if isinstance(v, dict):
        return {str(k): clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [clean(x) for x in v]
    if isinstance(v, (pd.Timestamp, datetime)):
        return None if pd.isna(v) else v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        try:
            v = v.item()
        except (ValueError, AttributeError):
            pass
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if v is pd.NaT:
        return None
    return v


def records(df: pd.DataFrame, cols: Optional[list[str]] = None) -> list[dict]:
    if df is None or df.empty:
        return []
    d = df[cols] if cols else df
    return [clean(r) for r in d.to_dict("records")]


def _stamp(cfg) -> tuple:
    files = [*cfg.paths.data.glob("waypoint.db*"), *cfg.paths.config.glob("*.yaml"),
             cfg.paths.profile / "profile.json", cfg.paths.profile / "overrides.yaml"]
    return (str(cfg.paths.root),) + tuple((f.name, f.stat().st_mtime_ns) for f in files if f.exists())


def analysis(cfg, db) -> Optional[pl.Analysis]:
    if not db.count_jobs():
        return None
    key = _stamp(cfg)
    with _lock:
        if _cache["key"] != key:
            a = pl.analyze(cfg, db, pl.resolve_extractor(db))
            _cache.update(key=key, analysis=a)
        a = _cache["analysis"]
    return a if a is not None and not a.jobs_df.empty else None


def client(db):
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


def role_info(cfg, rid: str) -> dict:
    r = cfg.all_roles.get(rid, {})
    return {"id": rid, "label": r.get("label", rid), "summary": r.get("summary", ""), "summary_en": r.get("summary_en", ""),
            "custom": bool(r.get("custom"))}


def state_of(cfg) -> orc.State:
    return orc.State.load(orc.state_path(cfg.paths.data))


def item_titles(state: orc.State, plan: Optional[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in state.projects:
        out[f"proj:{p.id}"] = {"title": p.name, "area": p.area, "project": p.name}
        for t in p.tasks:
            out[f"task:{t.id}"] = {"title": t.title, "area": p.area, "project": p.name}
    for it in (plan or {}).get("this_week", []):
        foco = orc.STUDY_FOCUS_KEY.get(it.get("foco", ""), "carreira")
        out[it.get("id") or f"study:{foco}:{it.get('item')}"] = {"title": it.get("item", ""), "area": foco, "project": ""}
    return out


def block_json(b: orc.Block) -> dict:
    return {"item": b.item, "title": b.title, "kind": b.kind, "area": b.area, "hours": b.hours,
            "project": b.project if b.project != b.title else "", "project_id": b.project_id, "due": b.due}


# ============================================================================= app
from contextlib import asynccontextmanager


@asynccontextmanager
async def _lifespan(_app):
    try:  # remember which process serves the UI, so the shortcut can restart an outdated one
        from ..launcher import register_server
        register_server(load_config().paths.root)
    except Exception:
        pass
    yield


app = FastAPI(title="Waypoint", docs_url=None, redoc_url=None, lifespan=_lifespan)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def _no_stale_assets(request, call_next):
    resp = await call_next(request)
    if request.url.path.startswith("/static/") and not request.url.path.startswith("/static/fonts/"):
        resp.headers["Cache-Control"] = "no-cache"  # revalidate (cheap ETag check) so updates show up at once
    return resp


# ----------------------------------------------------------------------------- shell
@app.get("/api/shell")
def shell() -> dict:
    cfg, db = ctx()
    s = updater.load_ui_settings(cfg)
    st = updater.read_status(cfg)
    a = analysis(cfg, db)
    state = state_of(cfg)
    sched = orc.build_schedule(state, pl.load_plan(cfg), today=today())
    return clean({
        "settings": s, "today": today().isoformat(), "llm": llm_label(),
        "last_update": pl.last_update(cfg), "update": st,
        "counts": {"jobs": len(a.jobs_df) if a else 0, "roles": len(cfg.roles), "projects": sum(not p.archived for p in state.projects)},
        "has_profile": load_profile(cfg.paths.profile) is not None, "has_plan": pl.load_plan(cfg) is not None,
        "has_routine": bool(state.availability) and orc.state_path(cfg.paths.data).exists(),
        "alerts": len(sched.risks) + len(sched.overdue),
    })


@app.put("/api/settings")
def put_settings(body: dict = Body(...)) -> dict:
    cfg, _ = ctx()
    allowed = {k: v for k, v in body.items() if k in ("theme", "lang", "auto_update_on_open", "auto_update_hours")}
    updater.save_ui_settings(cfg, **allowed)
    return updater.load_ui_settings(cfg)


@app.post("/api/update")
def start_update() -> dict:
    cfg, _ = ctx()
    started = updater.start_background_update(cfg)
    return {"started": started, "status": updater.read_status(cfg)}


@app.get("/api/update")
def update_status() -> dict:
    cfg, _ = ctx()
    return clean({"status": updater.read_status(cfg), "last_update": pl.last_update(cfg)})


@app.post("/api/quit")
def quit_app() -> dict:
    threading.Timer(0.6, lambda: os._exit(0)).start()
    return {"ok": True}


# ----------------------------------------------------------------------------- today / week
@app.get("/api/today")
def get_today() -> dict:
    cfg, db = ctx()
    state = state_of(cfg)
    plan = pl.load_plan(cfg)
    t0 = today()
    sched = orc.build_schedule(state, plan, today=t0)
    if orc.take_snapshot(state, sched):
        state.save(orc.state_path(cfg.paths.data))
    titles = item_titles(state, plan)
    done_h, total_h = orc.today_progress(state, sched)
    ws = orc.week_start(t0)
    week = []
    for i in range(7):
        d = ws + timedelta(i)
        sd = sched.day(d)
        planned = (sd.planned if sd else 0.0) + state.logged_on(d)
        week.append({"date": d.isoformat(), "hours": round(planned, 1), "capacity": state.capacity(d), "today": d == t0,
                     "past": d < t0})
    a = analysis(cfg, db)
    pulse = None
    if a is not None:
        levels = effective_levels(cfg.paths.profile)
        gap = pl.compute_gap(cfg, a)
        top = gap[gap["status"] != "has"].sort_values("priority", ascending=False).head(1)
        pulse = {"jobs": len(a.jobs_df), "roles": len(cfg.roles), "fit": market_fit(gap) if levels else None,
                 "top_gap": ({"name": top.iloc[0]["name"], "share": float(top.iloc[0]["share_any"])} if len(top) else None)}
    logged = [{"item": e["item"], "hours": e["hours"], **titles.get(e["item"], {"title": e["item"], "area": "pessoal", "project": ""})}
              for e in state.log if e["date"] == t0.isoformat()]
    return clean({
        "date": t0.isoformat(), "free": state.capacity(t0), "done_hours": done_h, "total_hours": total_h,
        "blocks": [block_json(b) for b in sched.days[0].blocks], "logged": logged,
        "risks": [{"item": r.item, "title": r.title, "project": r.project, "due": r.due, "missing": r.missing,
                   "borrowable": r.borrowable} for r in sched.risks],
        "overdue": [{"item": w.id, "title": w.title, "project": w.project, "due": w.due} for w in sched.overdue],
        "slipped": sched.slipped, "week": week, "week_load": sched.week_load, "pulse": pulse,
        "empty": not state.projects and plan is None,
    })


@app.post("/api/log")
def post_log(body: dict = Body(...)) -> dict:
    cfg, _ = ctx()
    state = state_of(cfg)
    hours = float(body.get("hours") or 0)
    if hours <= 0 or not body.get("item"):
        raise HTTPException(400, "item and hours > 0 are required")
    state.add_log(str(body["item"]), hours, today())
    state.save(orc.state_path(cfg.paths.data))
    return {"ok": True}


@app.post("/api/undo")
def post_undo(body: dict = Body(...)) -> dict:
    cfg, _ = ctx()
    state = state_of(cfg)
    ok = state.undo_last_log(str(body.get("item")), today())
    state.save(orc.state_path(cfg.paths.data))
    return {"ok": ok}


@app.post("/api/borrow")
def post_borrow(body: dict = Body(...)) -> dict:
    cfg, _ = ctx()
    foco = body.get("foco")
    if foco not in ("carreira", "interesses"):
        raise HTTPException(400, "only career or interests hours can be lent; exploration is protected")
    state = state_of(cfg)
    orc.accept_borrow(state, today(), foco, float(body.get("hours") or 0))
    state.save(orc.state_path(cfg.paths.data))
    return {"ok": True}


@app.put("/api/free-today")
def put_free_today(body: dict = Body(...)) -> dict:
    cfg, _ = ctx()
    state = state_of(cfg)
    state.day_overrides[today().isoformat()] = max(0.0, min(float(body.get("hours") or 0), 16.0))
    state.save(orc.state_path(cfg.paths.data))
    return {"ok": True}


@app.get("/api/week")
def get_week(offset: int = 0) -> dict:
    cfg, _ = ctx()
    state = state_of(cfg)
    plan = pl.load_plan(cfg)
    t0 = today()
    sched = orc.build_schedule(state, plan, today=t0)
    titles = item_titles(state, plan)
    ws = orc.week_start(t0) + timedelta(7 * offset)
    days = []
    for i in range(7):
        d = ws + timedelta(i)
        sd = sched.day(d)
        done = [{"item": e["item"], "hours": e["hours"], **titles.get(e["item"], {"title": e["item"], "area": "pessoal", "project": ""})}
                for e in state.log if e["date"] == d.isoformat()]
        days.append({"date": d.isoformat(), "today": d == t0, "past": d < t0,
                     "capacity": state.capacity(d), "blocks": [block_json(b) for b in sd.blocks] if sd else [], "done": done})
    return clean({"offset": offset, "days": days, "unscheduled_study": sched.unscheduled_study if offset == 0 else 0,
                  "week_load": sched.week_load})


@app.get("/api/routine")
def get_routine() -> dict:
    cfg, _ = ctx()
    state = state_of(cfg)
    t0 = today()
    return {"availability": state.availability, "max_block": state.max_block,
            "overrides": [{"date": k, "hours": v} for k, v in sorted(state.day_overrides.items()) if k >= t0.isoformat()],
            "focus": cfg.focus}


@app.put("/api/routine")
def put_routine(body: dict = Body(...)) -> dict:
    cfg, _ = ctx()
    state = state_of(cfg)
    if "availability" in body:
        state.availability = {str(k): max(0.0, min(float(v), 16.0)) for k, v in body["availability"].items()}
    if "max_block" in body:
        state.max_block = max(0.5, min(float(body["max_block"]), 6.0))
    if "overrides" in body:
        t0 = today().isoformat()
        keep = {k: v for k, v in state.day_overrides.items() if k < t0}
        for o in body["overrides"]:
            if o.get("date") and o["date"] >= t0:
                keep[o["date"][:10]] = max(0.0, min(float(o.get("hours") or 0), 16.0))
        state.day_overrides = keep
    state.save(orc.state_path(cfg.paths.data))
    return get_routine()


# ----------------------------------------------------------------------------- projects
def project_json(state: orc.State, p: orc.Project) -> dict:
    if p.tasks:
        total = sum(t.hours for t in p.tasks)
        done = sum(t.hours if t.done else min(state.logged(f"task:{t.id}"), t.hours) for t in p.tasks)
    else:
        total, done = p.hours, min(state.logged(f"proj:{p.id}"), p.hours)
    return {"id": p.id, "name": p.name, "area": p.area, "deadline": p.deadline, "priority": p.priority, "hours": p.hours,
            "notes": p.notes, "archived": p.archived, "done_hours": round(done, 1), "total_hours": round(total, 1),
            "tasks": [{"id": t.id, "title": t.title, "hours": t.hours, "due": t.due, "done": t.done,
                       "logged": round(state.logged(f"task:{t.id}"), 1)} for t in p.tasks]}


@app.get("/api/projects")
def list_projects() -> dict:
    cfg, _ = ctx()
    state = state_of(cfg)
    ps = sorted(state.projects, key=lambda p: (p.archived, p.deadline or "9999", p.priority))
    return {"projects": [project_json(state, p) for p in ps]}


def _task_list(items: list[dict]) -> list[orc.Task]:
    out = []
    for t in items or []:
        title = str(t.get("title") or "").strip()
        if not title:
            continue
        out.append(orc.Task(id=t.get("id") or orc.new_id(), title=title[:160],
                            hours=max(orc.STEP, min(float(t.get("hours") or 1.0), 200.0)),
                            due=(t.get("due") or None), done=bool(t.get("done"))))
    return out


@app.post("/api/projects")
def create_project(body: dict = Body(...)) -> dict:
    cfg, db = ctx()
    name = str(body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    area = body.get("area") if body.get("area") in orc.AREAS else "pessoal"
    p = orc.Project(id=orc.new_id(), name=name[:120], area=area, deadline=body.get("deadline") or None,
                    priority=int(body.get("priority") or 2), hours=float(body.get("hours") or 0),
                    notes=str(body.get("notes") or ""))
    if body.get("tasks"):
        p.tasks = _task_list(body["tasks"])
    elif body.get("breakdown"):
        p.tasks = orc.breakdown_tasks(p.name, area, p.deadline, p.notes, p.hours or 8.0, client=client(db), lang=lang(cfg))
    state = state_of(cfg)
    state.projects.append(p)
    state.save(orc.state_path(cfg.paths.data))
    return project_json(state, p)


@app.put("/api/projects/{pid}")
def update_project(pid: str, body: dict = Body(...)) -> dict:
    cfg, _ = ctx()
    state = state_of(cfg)
    p = state.project(pid)
    if not p:
        raise HTTPException(404, "project not found")
    for k in ("name", "notes"):
        if k in body:
            setattr(p, k, str(body[k] or "").strip() or getattr(p, k))
    if "area" in body and body["area"] in orc.AREAS:
        p.area = body["area"]
    if "deadline" in body:
        p.deadline = body["deadline"] or None
    if "priority" in body:
        p.priority = max(1, min(int(body["priority"]), 3))
    if "hours" in body:
        p.hours = max(0.0, float(body["hours"] or 0))
    if "archived" in body:
        p.archived = bool(body["archived"])
    if "tasks" in body:
        p.tasks = _task_list(body["tasks"])
    state.save(orc.state_path(cfg.paths.data))
    return project_json(state, p)


@app.delete("/api/projects/{pid}")
def delete_project(pid: str) -> dict:
    cfg, _ = ctx()
    state = state_of(cfg)
    p = state.project(pid)
    if not p:
        raise HTTPException(404, "project not found")
    ids = {f"proj:{p.id}"} | {f"task:{t.id}" for t in p.tasks}
    state.projects = [x for x in state.projects if x.id != pid]
    state.log = [e for e in state.log if e["item"] not in ids]
    state.save(orc.state_path(cfg.paths.data))
    return {"ok": True}


@app.post("/api/capture")
def post_capture(body: dict = Body(...)) -> dict:
    """Plain-language note → project draft (the user reviews it before saving)."""
    cfg, db = ctx()
    text = str(body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text is required")
    return orc.capture(text, today(), client=client(db), lang=lang(cfg))


@app.post("/api/breakdown")
def post_breakdown(body: dict = Body(...)) -> dict:
    cfg, db = ctx()
    tasks = orc.breakdown_tasks(str(body.get("name") or ""), body.get("area") or "pessoal", body.get("deadline"),
                                str(body.get("notes") or ""), float(body.get("hours") or 8.0), client=client(db), lang=lang(cfg))
    return {"tasks": [{"id": t.id, "title": t.title, "hours": t.hours, "due": None, "done": False} for t in tasks]}


# ----------------------------------------------------------------------------- study plan
@app.get("/api/plan")
def get_plan() -> dict:
    cfg, _ = ctx()
    plan = pl.load_plan(cfg)
    state = state_of(cfg)
    ws = orc.week_start(today())
    if plan:
        for it in plan.get("this_week", []):
            foco = orc.STUDY_FOCUS_KEY.get(it.get("foco", ""), "carreira")
            it["area"] = foco
            it["id"] = it.get("id") or f"study:{foco}:{it.get('item')}"
            it["logged"] = round(state.logged(it["id"], since=ws), 1)
    return clean({"plan": plan, "focus": cfg.focus, "lang": lang(cfg),
                  "existing_projects": [p.name for p in state.projects]})


@app.post("/api/plan")
def generate_plan(body: dict = Body(default={})) -> dict:
    cfg, db = ctx()
    a = analysis(cfg, db)
    if a is None:
        raise HTTPException(409, "no market data yet")
    lg = lang(cfg)
    c = client(db) if body.get("ideas", True) else None
    pl.save_plan(cfg, pl.make_plan(cfg, a, pl.compute_gap(cfg, a), client=c, lang=lg), lang=lg)
    return get_plan()


@app.put("/api/focus")
def put_focus(body: dict = Body(...)) -> dict:
    cfg, _ = ctx()
    f = cfg.focus
    w = body.get("weights") or f.get("weights", {})
    tot = sum(float(w.get(k, 0)) for k in ("carreira", "exploracao", "interesses")) or 1
    nc = round(float(w.get("carreira", 0)) * 100 / tot)
    ne = round(float(w.get("exploracao", 0)) * 100 / tot)
    exp = f.get("exploration", {})
    save_local(cfg.paths.config, "focus", {
        "weekly_hours": float(body.get("weekly_hours", f.get("weekly_hours", 10))),
        "weights": {"carreira": nc, "exploracao": ne, "interesses": 100 - nc - ne},
        "exploration": {"protected": bool(body.get("protected", exp.get("protected", True))),
                        "topics": [t.strip() for t in body.get("topics", exp.get("topics") or []) if str(t).strip()],
                        "include_emerging": exp.get("include_emerging", True)},
        "interests": [t.strip() for t in body.get("interests", f.get("interests") or []) if str(t).strip()]})
    return {"focus": load_config().focus}


@app.post("/api/plan/project")
def plan_project_to_projects(body: dict = Body(...)) -> dict:
    cfg, db = ctx()
    title = str(body.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "title is required")
    p = orc.Project(id=orc.new_id(), name=title, area="carreira", priority=2, hours=20.0, notes=str(body.get("description") or ""))
    p.tasks = orc.breakdown_tasks(p.name, "carreira", None, p.notes, 20.0, client=client(db), lang=lang(cfg))
    state = state_of(cfg)
    state.projects.append(p)
    state.save(orc.state_path(cfg.paths.data))
    return project_json(state, p)


# ----------------------------------------------------------------------------- market
def _skills_rows(tbl: pd.DataFrame, top: int) -> list[dict]:
    t = tbl[~tbl["skill_id"].str.startswith("other:")].head(top)
    return records(t, ["skill_id", "name", "category", "share_any", "share_required", "share_nice", "n_any"])


@app.get("/api/market")
def get_market(role: str = "", region: str = "", seniority: str = "", top: int = 20) -> dict:
    cfg, db = ctx()
    a = analysis(cfg, db)
    roles = [role_info(cfg, r) | {"n": int((a.jobs_df["role"] == r).sum()) if a else 0} for r in cfg.roles]
    if a is None:
        return {"empty": True, "roles": roles}
    sens = [s for s in seniority.split(",") if s]
    j, s = market.filter_frames(a.jobs_df, a.skills_df, role=role or None, region=region or None, seniorities=sens or None)
    tbl = market.skill_table(j, s)
    sen = market.distribution(j, "seniority")
    rc = a.region_cmp
    return clean({
        "empty": False, "roles": roles, "regions": sorted(a.jobs_df["region"].dropna().unique().tolist()),
        "kpis": {"jobs": len(j), "companies": int(j["company"].nunique()), "skills": int(tbl["skill_id"].nunique()),
                 "remote": float((j["work_model"] == "remote").mean()) if len(j) else None},
        "small_sample": bool(role) and len(j) < MIN_ROLE_JOBS,
        "skills": _skills_rows(tbl, max(5, min(top, 40))),
        "seniority": records(sen.rename(columns={"seniority": "key"})),
        "trends": records(a.trends.head(10), ["skill_id", "name", "share_recent", "share_older", "delta_pp"]),
        "region_compare": records(rc),
    })


@app.get("/api/market/skill/{skill_id}")
def market_skill(skill_id: str, role: str = "", region: str = "", seniority: str = "") -> dict:
    cfg, db = ctx()
    a = analysis(cfg, db)
    if a is None:
        return {"jobs": [], "pairs": []}
    sens = [s for s in seniority.split(",") if s]
    j, s = market.filter_frames(a.jobs_df, a.skills_df, role=role or None, region=region or None, seniorities=sens or None)
    sub = s[s["skill_id"] == skill_id][["job_key", "requirement"]].drop_duplicates("job_key")
    m = j.merge(sub, on="job_key")
    return clean({"jobs": records(m, ["job_key", "company", "title", "role", "region", "url", "requirement"]),
                  "pairs": market.cooccurrence(s, skill_id, top=5)})


@app.get("/api/compare")
def get_compare(roles: str = "") -> dict:
    cfg, db = ctx()
    a = analysis(cfg, db)
    if a is None:
        return {"empty": True}
    counts = a.jobs_df["role"].value_counts()
    available = sorted([r for r in cfg.roles if counts.get(r, 0)], key=lambda r: -counts[r])
    chosen = [r for r in roles.split(",") if r in available][:3] or available[:3]
    levels = effective_levels(cfg.paths.profile)
    cards, union, names = [], [], {}
    for r in chosen:
        t = a.tables[r]
        jr = a.jobs_df[a.jobs_df["role"] == r]
        others = set().union(*[set(a.tables[o]["skill_id"].head(25)) for o in chosen if o != r]) if len(chosen) > 1 else set()
        own = t[~t["skill_id"].isin(others) & ~t["skill_id"].str.startswith("other:")].head(5)
        cards.append(role_info(cfg, r) | {"n": len(jr), "entry": float(jr["seniority"].isin(["intern", "junior"]).mean()) if len(jr) else 0,
                                          "fit": market_fit(gap_table(t, levels)) if levels else None,
                                          "typical": own["name"].tolist(), "small": len(jr) < MIN_ROLE_JOBS})
        tt = t[~t["skill_id"].str.startswith("other:")]
        names.update(zip(tt["skill_id"], tt["name"]))
        for sid in tt["skill_id"].head(10):
            if sid not in union:
                union.append(sid)
    rows = []
    for sid in union:
        row = {"skill_id": sid, "name": names[sid], "shares": {}}
        for r in chosen:
            sh = a.tables[r].set_index("skill_id")["share_any"]
            row["shares"][r] = float(sh.get(sid, 0.0))
        rows.append(row)
    rows.sort(key=lambda x: -max(x["shares"].values()))
    return clean({"empty": False, "available": [role_info(cfg, r) | {"n": int(counts[r])} for r in available],
                  "chosen": chosen, "cards": cards, "rows": rows})


# ----------------------------------------------------------------------------- jobs
@app.get("/api/jobs")
def get_jobs(q: str = "", roles: str = "", region: str = "", seniority: str = "", skills: str = "", limit: int = 400) -> dict:
    cfg, db = ctx()
    a = analysis(cfg, db)
    if a is None:
        return {"jobs": [], "total": 0, "skills": []}
    j, s = a.jobs_df, a.skills_df
    m = pd.Series(True, index=j.index)
    if q:
        m &= j["title"].str.contains(q, case=False, regex=False) | j["company"].str.contains(q, case=False, regex=False)
    if roles:
        m &= j["role"].isin(roles.split(","))
    if region:
        m &= j["region"] == region
    if seniority:
        m &= j["seniority"].isin(seniority.split(","))
    for sid in [x for x in skills.split(",") if x]:
        m &= j["job_key"].isin(s.loc[s["skill_id"] == sid, "job_key"])
    jj = j[m].sort_values("published_at", ascending=False, na_position="last")
    tax = s[~s["skill_id"].str.startswith("other:")].drop_duplicates("skill_id")[["skill_id", "name"]]
    return clean({"total": len(jj), "jobs": records(jj.head(limit), ["job_key", "company", "title", "role", "seniority", "region",
                                                                    "published_at", "url", "source"]),
                  "skills": records(tax.sort_values("name"))})


@app.get("/api/jobs/{job_key:path}")
def get_job(job_key: str) -> dict:
    cfg, db = ctx()
    a = analysis(cfg, db)
    job = db.job(job_key)
    if job is None:
        raise HTTPException(404, "job not found")
    js = a.skills_df[a.skills_df["job_key"] == job_key] if a is not None else pd.DataFrame(columns=["skill_id", "name", "requirement"])
    levels = effective_levels(cfg.paths.profile)
    miss = [n for sid, n in zip(js["skill_id"], js["name"]) if not str(sid).startswith("other:") and levels.get(sid, 0) < 2] if levels else None
    row = a.jobs_df[a.jobs_df["job_key"] == job_key] if a is not None else pd.DataFrame()
    meta = records(row, ["seniority", "region", "work_model", "published_at"])[0] if len(row) else {}
    return clean({"job_key": job.job_key, "title": job.title, "company": job.company, "url": job.url, "source": job.source,
                  "role": job.role, "text": job.text[:12000], **meta,
                  "required": js[js["requirement"] == "required"]["name"].tolist(),
                  "nice": js[js["requirement"] == "nice_to_have"]["name"].tolist(), "missing": miss})


@app.post("/api/jobs")
def post_job(body: dict = Body(...)) -> dict:
    cfg, db = ctx()
    text = str(body.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text is required")
    status, job = add_manual(cfg, db, text, title=body.get("title") or "", company=body.get("company") or "", url=body.get("url") or "")
    return {"status": status, "title": job.title, "job_key": job.job_key}


# ----------------------------------------------------------------------------- roles
@app.get("/api/roles")
def get_roles() -> dict:
    cfg, db = ctx()
    counts = pd.Series([j.role for j in db.jobs()]).value_counts().to_dict() if db.count_jobs() else {}
    out = []
    for rid, r in cfg.all_roles.items():
        out.append({"id": rid, "label": r.get("label", rid), "enabled": rid in cfg.roles, "n": int(counts.get(rid, 0)),
                    "custom": bool(r.get("custom")), "search_terms": r.get("search_terms") or [],
                    **{k: r.get(k) for k in ("summary", "description", "day_to_day", "typical_skills",
                                             "summary_en", "description_en", "day_to_day_en", "typical_skills_en")}})
    return {"roles": out}


@app.put("/api/roles")
def put_roles(body: dict = Body(...)) -> dict:
    cfg, db = ctx()
    chosen = [r for r in body.get("enabled", []) if r in cfg.all_roles]
    if not chosen:
        raise HTTPException(400, "keep at least one role on")
    save_local(cfg.paths.config, "targets", {"roles_enabled": chosen})
    n = reassign_roles(load_config(), db)
    return {"relabeled": n, **get_roles()}


@app.post("/api/roles/custom")
def post_custom_role(body: dict = Body(...)) -> dict:
    cfg, _ = ctx()
    name = str(body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    rid, role = make_custom_role(name)
    custom = dict(cfg.targets.get("custom_roles") or {})
    custom[rid] = role
    save_local(cfg.paths.config, "targets", {"custom_roles": custom, "roles_enabled": [*cfg.roles, rid]})
    return {"id": rid, **get_roles()}


@app.delete("/api/roles/custom/{rid}")
def delete_custom_role(rid: str) -> dict:
    cfg, _ = ctx()
    custom = dict(cfg.targets.get("custom_roles") or {})
    custom.pop(rid, None)
    save_local(cfg.paths.config, "targets", {"custom_roles": custom, "roles_enabled": [r for r in cfg.roles if r != rid]})
    return get_roles()


# ----------------------------------------------------------------------------- profile
@app.get("/api/profile")
def get_profile(role: str = "") -> dict:
    cfg, db = ctx()
    prof = load_profile(cfg.paths.profile)
    levels = effective_levels(cfg.paths.profile)
    a = analysis(cfg, db)
    out: dict[str, Any] = {"has_profile": prof is not None, "method": prof.method if prof else None,
                           "llm": llm_label(), "skills": [], "fit": [], "gap": [], "role": role or "focus"}
    if prof:
        out["skills"] = [{"skill_id": s.skill_id, "name": s.name, "level": levels.get(s.skill_id, s.level),
                          "base": s.level, "evidence": s.evidence or ""} for s in prof.skills]
    if a is not None and levels:
        for rid, v in pl.role_fit(cfg, a).items():
            n = int((a.jobs_df["role"] == rid).sum())
            out["fit"].append(role_info(cfg, rid) | {"fit": v, "n": n, "small": n < MIN_ROLE_JOBS})
        tbl = a.tables.get(role) if role in a.tables else a.focus_table
        g = gap_table(tbl, levels)
        out["gap"] = records(g, ["skill_id", "name", "share_any", "level", "status", "priority", "effort_hours"])
        out["market_fit"] = market_fit(g)
        known = {s["skill_id"] for s in out["skills"]}
        extra = a.focus_table[~a.focus_table["skill_id"].isin(known) & ~a.focus_table["skill_id"].str.startswith("other:")].head(15)
        out["market_extra"] = [{"skill_id": r.skill_id, "name": r.name, "level": levels.get(r.skill_id, 0)} for r in extra.itertuples()]
    return clean(out)


@app.post("/api/profile/resume")
async def post_resume(file: UploadFile = File(...), use_ai: bool = True) -> dict:
    cfg, db = ctx()
    name = Path(file.filename or "resume.pdf").name
    if Path(name).suffix.lower() not in (".pdf", ".docx", ".md", ".txt"):
        raise HTTPException(400, "use .pdf, .docx, .md or .txt")
    dest = cfg.paths.profile / name
    dest.write_bytes(await file.read())
    prof = build_profile(dest, cfg.paths.profile, client=client(db) if use_ai else None)
    return {"skills": len(prof.skills), "method": prof.method}


@app.put("/api/profile/levels")
def put_levels(body: dict = Body(...)) -> dict:
    cfg, _ = ctx()
    prof = load_profile(cfg.paths.profile)
    base = prof.levels() if prof else {}
    from ..profile import load_overrides
    ov = load_overrides(cfg.paths.profile)
    for sid, lvl in (body.get("levels") or {}).items():
        lvl = max(0, min(int(lvl), 3))
        if base.get(sid, 0) == lvl:
            ov.pop(sid, None)
        else:
            ov[sid] = lvl
    save_overrides(cfg.paths.profile, ov)
    return {"ok": True}


# ----------------------------------------------------------------------------- report
@app.get("/api/report")
def get_report() -> dict:
    cfg, db = ctx()
    a = analysis(cfg, db)
    if a is None:
        return {"empty": True}
    numbers = post_numbers(a.jobs_df, a.tables, cfg.roles)
    return clean({"empty": False, "post": linkedin_post_draft(numbers), "numbers": numbers})


@app.post("/api/report")
def post_report(body: dict = Body(default={})) -> dict:
    cfg, db = ctx()
    a = analysis(cfg, db)
    if a is None:
        raise HTTPException(409, "no market data yet")
    model = db.conn.execute("SELECT model FROM extractions WHERE extractor=? LIMIT 1", (a.extractor,)).fetchone()
    model = model[0] if model else a.extractor
    if body.get("public", True):
        files = pl.make_report(cfg, a, gap=None, plan=None, model=model, public=True)
    else:
        gap = pl.compute_gap(cfg, a)
        files = pl.make_report(cfg, a, gap=gap, plan=pl.make_plan(cfg, a, gap), model=model)
    return {"saved": str(files["report"])}


@app.exception_handler(Exception)
async def _errors(_, exc: Exception) -> JSONResponse:  # a short, readable error for the interface
    return JSONResponse({"detail": f"{type(exc).__name__}: {exc}"}, status_code=500)


def run(host: str = "127.0.0.1", port: int = 8501) -> None:
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    run()
