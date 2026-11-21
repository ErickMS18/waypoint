"""Market analysis over extracted postings (pandas)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

import pandas as pd

from ..db import DB
from ..extract import canonicalize
from ..models import Job, JobExtraction
from ..taxonomy import get_taxonomy

REQ_WEIGHT, NICE_WEIGHT = 1.0, 0.5


def build_frames(jobs: Iterable[Job], extractions: dict[str, JobExtraction]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (jobs_df, skills_df). Only jobs that have an extraction are included."""
    tax = get_taxonomy()
    jrows, srows = [], []
    for j in jobs:
        ext = extractions.get(j.job_key)
        if ext is None:
            continue
        jrows.append({
            "job_key": j.job_key, "source": j.source, "company": j.company, "title": j.title,
            "role": j.role, "region": j.region, "lang": j.lang, "url": j.url,
            "published_at": pd.to_datetime(j.published_at, utc=True, errors="coerce") if j.published_at else pd.NaT,
            "seniority": ext.seniority, "years_min": ext.years_experience_min, "work_model": ext.work_model,
        })
        for cs in canonicalize(ext, tax):
            srows.append({"job_key": j.job_key, "skill_id": cs.skill_id, "name": cs.name,
                          "category": tax.category_of(cs.skill_id), "requirement": cs.requirement})
    jobs_df = pd.DataFrame(jrows, columns=["job_key", "source", "company", "title", "role", "region", "lang", "url",
                                           "published_at", "seniority", "years_min", "work_model"])
    skills_df = pd.DataFrame(srows, columns=["job_key", "skill_id", "name", "category", "requirement"])
    if not skills_df.empty:
        skills_df = skills_df.merge(jobs_df[["job_key", "role", "region", "seniority", "published_at"]], on="job_key")
    return jobs_df, skills_df


def load_frames(db: DB, extractor: str = "llm") -> tuple[pd.DataFrame, pd.DataFrame]:
    return build_frames(db.jobs(), db.extractions(extractor))


def filter_frames(jobs_df: pd.DataFrame, skills_df: pd.DataFrame, *, role: Optional[str] = None,
                  region: Optional[str] = None, seniorities: Optional[list[str]] = None):
    m = pd.Series(True, index=jobs_df.index)
    if role:
        m &= jobs_df["role"] == role
    if region:
        m &= jobs_df["region"] == region
    if seniorities:
        m &= jobs_df["seniority"].isin(seniorities)
    j = jobs_df[m]
    s = skills_df[skills_df["job_key"].isin(j["job_key"])] if not skills_df.empty else skills_df
    return j, s


def skill_table(jobs_df: pd.DataFrame, skills_df: pd.DataFrame, include_other: bool = True) -> pd.DataFrame:
    """One row per skill: counts, shares and weighted demand (required=1, nice=0.5)."""
    cols = ["skill_id", "name", "category", "n_required", "n_nice", "n_any", "share_any", "share_required",
            "share_nice", "demand"]
    n = len(jobs_df)
    if n == 0 or skills_df.empty:
        return pd.DataFrame(columns=cols)
    s = skills_df if include_other else skills_df[~skills_df["skill_id"].str.startswith("other:")]
    g = s.groupby(["skill_id", "name", "category"])
    t = pd.DataFrame({
        "n_required": g.apply(lambda x: (x["requirement"] == "required").sum(), include_groups=False),
        "n_nice": g.apply(lambda x: (x["requirement"] == "nice_to_have").sum(), include_groups=False),
    }).reset_index()
    t["n_any"] = t["n_required"] + t["n_nice"]
    t["share_any"] = t["n_any"] / n
    t["share_required"] = t["n_required"] / n
    t["share_nice"] = t["n_nice"] / n
    t["demand"] = (REQ_WEIGHT * t["n_required"] + NICE_WEIGHT * t["n_nice"]) / n
    return t.sort_values(["demand", "n_any"], ascending=False).reset_index(drop=True)[cols]


def distribution(jobs_df: pd.DataFrame, col: str) -> pd.DataFrame:
    if jobs_df.empty:
        return pd.DataFrame(columns=[col, "n", "share"])
    c = jobs_df[col].fillna("unknown").value_counts()
    return pd.DataFrame({col: c.index, "n": c.values, "share": c.values / c.values.sum()})


def region_compare(jobs_df: pd.DataFrame, skills_df: pd.DataFrame, top: int = 15) -> pd.DataFrame:
    """Share of postings mentioning each top skill, per region."""
    base = skill_table(jobs_df, skills_df, include_other=False).head(top)
    out = base[["skill_id", "name"]].copy()
    for region in sorted(jobs_df["region"].dropna().unique()):
        j, s = filter_frames(jobs_df, skills_df, region=region)
        t = skill_table(j, s).set_index("skill_id")["share_any"] if len(j) else pd.Series(dtype=float)
        out[region] = out["skill_id"].map(t).fillna(0.0)
        out[f"n_{region}"] = len(j)
    return out


def trends(jobs_df: pd.DataFrame, skills_df: pd.DataFrame, recent_days: int = 45, min_jobs: int = 10,
           now: Optional[datetime] = None) -> pd.DataFrame:
    """Compare skill shares between recent and older postings (by publication date)."""
    cols = ["skill_id", "name", "share_recent", "share_older", "delta_pp", "n_recent_jobs", "n_older_jobs"]
    if jobs_df.empty or jobs_df["published_at"].isna().all():
        return pd.DataFrame(columns=cols)
    now = now or datetime.now(timezone.utc)
    cut = pd.Timestamp(now - timedelta(days=recent_days))
    recent = jobs_df[jobs_df["published_at"] >= cut]
    older = jobs_df[jobs_df["published_at"] < cut]
    if len(recent) < min_jobs or len(older) < min_jobs:
        return pd.DataFrame(columns=cols)
    a = skill_table(recent, skills_df[skills_df["job_key"].isin(recent["job_key"])]).set_index("skill_id")
    b = skill_table(older, skills_df[skills_df["job_key"].isin(older["job_key"])]).set_index("skill_id")
    ids = a.index.union(b.index)
    t = pd.DataFrame(index=ids)
    t["name"] = a["name"].combine_first(b["name"])
    t["share_recent"] = a["share_any"].reindex(ids).fillna(0)
    t["share_older"] = b["share_any"].reindex(ids).fillna(0)
    t["delta_pp"] = (t["share_recent"] - t["share_older"]) * 100
    t["n_recent_jobs"], t["n_older_jobs"] = len(recent), len(older)
    return t.reset_index(names="skill_id").sort_values("delta_pp", ascending=False)[cols]


def emerging(jobs_df: pd.DataFrame, skills_df: pd.DataFrame, top: int = 8) -> pd.DataFrame:
    """Candidates for exploration: rising skills, plus frequent skills outside the taxonomy."""
    rows = []
    tr = trends(jobs_df, skills_df)
    for _, r in tr[tr["delta_pp"] >= 5].head(top).iterrows():
        rows.append({"skill_id": r["skill_id"], "name": r["name"], "kind": "rising", "value": float(r["delta_pp"]),
                     "why": f"subiu {r['delta_pp']:.0f} p.p. nas vagas recentes"})
    t = skill_table(jobs_df, skills_df)
    other = t[t["skill_id"].str.startswith("other:") & (t["n_any"] >= 2)].head(top)
    for _, r in other.iterrows():
        rows.append({"skill_id": r["skill_id"], "name": r["name"], "kind": "new", "value": float(r["n_any"]),
                     "why": f"aparece em {int(r['n_any'])} vagas e ainda não está na taxonomia"})
    return pd.DataFrame(rows, columns=["skill_id", "name", "kind", "value", "why"]).drop_duplicates("skill_id").head(top)


def cooccurrence(skills_df: pd.DataFrame, skill_id: str, top: int = 3) -> list[str]:
    if skills_df.empty:
        return []
    jobs_with = skills_df.loc[skills_df["skill_id"] == skill_id, "job_key"]
    other = skills_df[skills_df["job_key"].isin(jobs_with) & (skills_df["skill_id"] != skill_id)
                      & ~skills_df["skill_id"].str.startswith("other:")
                      & ~skills_df["category"].isin(["spoken", "soft"])]
    return other["name"].value_counts().head(top).index.tolist()
