"""High-level steps shared by the CLI and the web UI."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

from .analysis import market
from .analysis.gap import gap_table
from .analysis.plan import Plan, build_plan
from .db import DB
from .profile import effective_levels
from .report import write_report
from .settings import Config

MIN_FOCUS_JOBS = 15


@dataclass
class Analysis:
    extractor: str
    jobs_df: pd.DataFrame
    skills_df: pd.DataFrame
    tables: dict[str, pd.DataFrame]  # per role, all seniorities
    overall: pd.DataFrame             # all target roles together
    focus_table: pd.DataFrame         # roles together, filtered to seniority_focus (if enough jobs)
    focus_note: str
    seniority: pd.DataFrame
    regions: pd.DataFrame
    region_cmp: pd.DataFrame
    trends: pd.DataFrame
    emerging: pd.DataFrame
    extra: dict[str, Any] = field(default_factory=dict)


def analyze(cfg: Config, db: DB, extractor: str = "llm") -> Analysis:
    jobs_df, skills_df = market.load_frames(db, extractor)
    # only enabled roles (disabled roles keep their postings in the database)
    enabled = set(cfg.roles)
    keep = jobs_df["role"].isin(enabled) | (jobs_df["source"] == "manual")
    jobs_df = jobs_df[keep].reset_index(drop=True)
    skills_df = skills_df[skills_df["job_key"].isin(jobs_df["job_key"])].reset_index(drop=True)
    tables = {}
    for rid in cfg.roles:
        j, s = market.filter_frames(jobs_df, skills_df, role=rid)
        tables[rid] = market.skill_table(j, s)
    overall = market.skill_table(jobs_df, skills_df)
    fj, fs = market.filter_frames(jobs_df, skills_df, seniorities=cfg.seniority_focus)
    if len(fj) >= MIN_FOCUS_JOBS:
        focus_table = market.skill_table(fj, fs)
        note = f"Gap calculado sobre {len(fj)} vagas de nível {', '.join(cfg.seniority_focus)}."
    else:
        focus_table = overall
        note = (f"Só {len(fj)} vagas no seu nível-alvo ({', '.join(cfg.seniority_focus)}); "
                f"o gap usa todas as {len(jobs_df)} vagas.")
    return Analysis(
        extractor=extractor, jobs_df=jobs_df, skills_df=skills_df, tables=tables, overall=overall,
        focus_table=focus_table, focus_note=note,
        seniority=market.distribution(jobs_df, "seniority"), regions=market.distribution(jobs_df, "region"),
        region_cmp=market.region_compare(jobs_df, skills_df), trends=market.trends(jobs_df, skills_df),
        emerging=market.emerging(jobs_df, skills_df),
    )


def compute_gap(cfg: Config, a: Analysis) -> pd.DataFrame:
    return gap_table(a.focus_table, effective_levels(cfg.paths.profile))


def make_plan(cfg: Config, a: Analysis, gap: pd.DataFrame, client=None) -> Plan:
    roles = [r.get("label", rid) for rid, r in cfg.roles.items()]
    return build_plan(gap, cfg.focus, roles=roles, skills_df=a.skills_df, emerging_df=a.emerging, client=client)


def make_report(cfg: Config, a: Analysis, *, gap: Optional[pd.DataFrame], plan: Optional[Plan],
                model: str, public: bool = False):
    out = cfg.paths.reports / ("public" if public else "")
    return write_report(out, jobs_df=a.jobs_df, tables=a.tables, roles_cfg=cfg.roles, seniority=a.seniority,
                        regions=a.regions, region_cmp=a.region_cmp, trends=a.trends, gap=gap, plan=plan,
                        extractor_model=model, public=public)


# ----------------------------------------------------------------------------- shared helpers for the UI
import json as _json
from datetime import date as _date, datetime as _datetime, timezone as _tz
from pathlib import Path as _Path
from typing import Callable as _Callable


def resolve_extractor(db: DB) -> str:
    n = db.conn.execute("SELECT COUNT(*) FROM extractions WHERE extractor='llm'").fetchone()[0]
    return "llm" if n else "baseline"


def role_fit(cfg: Config, a: Analysis) -> dict[str, float]:
    """Demand-weighted coverage of each enabled role's top skills (0..1)."""
    from .analysis.gap import market_fit
    levels = effective_levels(cfg.paths.profile)
    return {rid: market_fit(gap_table(tbl, levels)) for rid, tbl in a.tables.items() if len(tbl)}


# --- plan persistence (so the home page can show the week's mission without recomputing)
def plan_path(cfg: Config) -> _Path:
    return cfg.paths.data / "plan.json"


def save_plan(cfg: Config, plan: Plan) -> None:
    d = plan.to_dict()
    d["generated_at"] = _datetime.now(_tz.utc).isoformat(timespec="seconds")
    plan_path(cfg).write_text(_json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def load_plan(cfg: Config) -> Optional[dict[str, Any]]:
    p = plan_path(cfg)
    return _json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def _week_id(today: Optional[_date] = None) -> str:
    y, w, _ = (today or _date.today()).isocalendar()
    return f"{y}-W{w:02d}"


def load_done(cfg: Config, today: Optional[_date] = None) -> set[str]:
    """Items marked as done this ISO week (resets automatically every Monday)."""
    p = cfg.paths.data / "plan_state.json"
    if not p.exists():
        return set()
    d = _json.loads(p.read_text(encoding="utf-8"))
    return set(d.get("done", [])) if d.get("week") == _week_id(today) else set()


def set_done(cfg: Config, item: str, done: bool, today: Optional[_date] = None) -> None:
    cur = load_done(cfg, today)
    (cur.add if done else cur.discard)(item)
    (cfg.paths.data / "plan_state.json").write_text(
        _json.dumps({"week": _week_id(today), "done": sorted(cur)}, ensure_ascii=False), encoding="utf-8")


def last_update(cfg: Config) -> Optional[str]:
    p = cfg.paths.data / "last_update.txt"
    return p.read_text(encoding="utf-8").strip() if p.exists() else None


def update_all(cfg: Config, db: DB, client=None, progress: Optional[_Callable[[str, float], None]] = None,
               transport=None) -> dict[str, Any]:
    """Everything the 'Atualizar' button does: collect -> extract -> plan -> reports."""
    from .collect import collect
    from .extract import run_extraction

    def say(msg: str, frac: float) -> None:
        if progress:
            progress(msg, frac)

    out: dict[str, Any] = {}
    say("Coletando vagas nas fontes…", 0.02)
    st = collect(cfg, db, transport=transport, progress=lambda m: say(m, 0.1))
    out["collect"] = {"novas": st.new, "vistas": st.seen, "erros": st.errors}
    jobs = db.jobs()
    say("Extraindo habilidades (dicionário)…", 0.3)
    out["baseline"] = run_extraction(db, jobs, "baseline")
    if client is not None:
        def prog(i: int, n: int, j) -> None:
            say(f"IA lendo vaga {i}/{n}: {j.company} — {j.title}", 0.35 + 0.5 * i / max(n, 1))
        out["llm"] = run_extraction(db, jobs, "llm", client, progress=prog)
    say("Atualizando análises e plano…", 0.88)
    a = analyze(cfg, db, resolve_extractor(db))
    if not a.jobs_df.empty:
        gap = compute_gap(cfg, a)
        plan = make_plan(cfg, a, gap, client=client)
        save_plan(cfg, plan)
        say("Gerando relatórios…", 0.95)
        model = db.conn.execute("SELECT model FROM extractions WHERE extractor=? LIMIT 1", (a.extractor,)).fetchone()
        make_report(cfg, a, gap=gap, plan=plan, model=model[0] if model else a.extractor)
        make_report(cfg, a, gap=None, plan=None, model=model[0] if model else a.extractor, public=True)
    stamp = _datetime.now().strftime("%d/%m/%Y %H:%M")
    (cfg.paths.data / "last_update.txt").write_text(stamp, encoding="utf-8")
    out["stamp"] = stamp
    say("Pronto!", 1.0)
    return out
