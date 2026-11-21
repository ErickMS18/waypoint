"""Collection pipeline: sources -> role filter -> normalized Job -> SQLite."""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable

from .db import DB
from .http import Http
from .models import Job
from .roles import RoleMatcher, region_of
from .settings import Config
from .sources import Posting, build_sources, parse_manual
from .textutil import fold, guess_lang

log = logging.getLogger("waypoint.collect")


@dataclass
class CollectStats:
    by_source: Counter = field(default_factory=Counter)
    new: int = 0
    seen: int = 0
    duplicate: int = 0
    skipped_empty: int = 0
    pruned: int = 0
    near_duplicates_removed: int = 0
    reassigned: int = 0
    errors: list[str] = field(default_factory=list)


def make_http(cfg: Config, transport=None) -> Http:
    h = cfg.sources.get("http", {})
    return Http(user_agent=h.get("user_agent", "waypoint/0.1"), delay=float(h.get("delay_seconds", 1.0)),
                timeout=float(h.get("timeout_seconds", 30)), transport=transport)


def guess_role(p: Posting, matcher: RoleMatcher, roles: dict) -> str:
    """Title match first, then the source's hint, then search terms found in the text."""
    rid = matcher.match(p.title)
    if rid:
        return rid
    if p.role_hint and p.role_hint in roles:
        return p.role_hint
    text = fold(p.text[:5000])
    scores = {r: sum(text.count(fold(t)) for t in roles[r].get("search_terms", [])) for r in roles}
    best = max(scores, key=scores.get) if scores else ""
    return best if scores.get(best) else next(iter(roles), "")


def posting_to_job(p: Posting, matcher: RoleMatcher, roles: dict) -> Job:
    return Job(
        job_key=p.job_key, source=p.source, board=p.board, external_id=p.external_id,
        company=p.company or p.board, title=p.title, location=p.location,
        region=p.region or region_of(p.location, source=p.source), remote=p.remote, url=p.url,
        published_at=p.published_at, role=guess_role(p, matcher, roles), lang=guess_lang(p.text), text=p.text,
    )


def collect(cfg: Config, db: DB, only: list[str] | None = None, transport=None,
            progress: Callable[[str], None] | None = None) -> CollectStats:
    stats = CollectStats()
    roles = cfg.roles
    matcher = RoleMatcher(roles)
    http = make_http(cfg, transport)
    try:
        for src in build_sources(cfg.sources, http, cfg.paths.root, only):
            if progress:
                progress(f"Coletando {src.name}…")
            try:
                for p in src.fetch(roles, keep=lambda t: matcher.match(t) is not None):
                    if len(p.text) < 200:
                        stats.skipped_empty += 1
                        continue
                    status = db.upsert_job(posting_to_job(p, matcher, roles))
                    setattr(stats, status, getattr(stats, status) + 1)
                    if status == "new":
                        stats.by_source[src.name] += 1
                db.conn.commit()
            except Exception as e:  # one broken source must not stop the others
                log.exception("source %s failed", src.name)
                stats.errors.append(f"{src.name}: {e}")
    finally:
        http.close()
    stats.pruned = prune_unmatched(db, RoleMatcher(cfg.all_roles))
    stats.reassigned = reassign_roles(cfg, db)
    stats.near_duplicates_removed = db.remove_near_duplicates()
    return stats


def reassign_roles(cfg: Config, db: DB) -> int:
    """Re-label stored postings after the role list changes (e.g. 'MLOps Engineer' used to fall
    under AI/ML and now has its own role). Enabled roles win; otherwise the catalog order decides."""
    enabled, every = RoleMatcher(cfg.roles), RoleMatcher(cfg.all_roles)
    n = 0
    for job in db.jobs():
        if job.source == "manual":
            continue
        new = enabled.match(job.title) or every.match(job.title)
        if new and new != job.role:
            db.conn.execute("UPDATE jobs SET role=? WHERE job_key=?", (new, job.job_key))
            n += 1
    db.conn.commit()
    return n


def prune_unmatched(db: DB, matcher: RoleMatcher) -> int:
    """Drop collected postings whose title matches no known role at all (catalog + custom).
    Turning a role off does NOT delete its postings: they are only hidden from the analysis.
    Postings you pasted yourself are always kept."""
    drop = [j.job_key for j in db.jobs() if j.source != "manual" and matcher.match(j.title) is None]
    return db.delete_jobs(drop)


def add_manual(cfg: Config, db: DB, raw: str, title: str = "", company: str = "", url: str = "") -> tuple[str, Job]:
    p = parse_manual(raw, default_title=title)
    if title:
        p.title = title
    if company:
        p.company = company
    if url:
        p.url = url
    job = posting_to_job(p, RoleMatcher(cfg.roles), cfg.roles)
    status = db.upsert_job(job)
    db.conn.commit()
    return status, job
