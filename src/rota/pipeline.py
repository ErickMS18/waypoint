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
