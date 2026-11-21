"""Keyword-search sources: Himalayas (remote, official free API) and Gupy (opt-in)."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterator

from ..textutil import html_to_text
from .base import Posting, Source, TitleFilter, ts_to_iso

log = logging.getLogger("waypoint.sources")


def _names(items: Any) -> list[str]:
    out = []
    for x in items or []:
        if isinstance(x, str):
            out.append(x)
        elif isinstance(x, dict):
            out.append(str(x.get("name") or x.get("country") or x.get("alpha2") or ""))
    return [x for x in out if x]


class Himalayas(Source):
    """https://himalayas.app/docs/remote-jobs-api — attribution required, no redistribution."""

    name = "himalayas"
    URL = "https://himalayas.app/jobs/api/search"

    def fetch(self, roles, keep: TitleFilter) -> Iterator[Posting]:
        seen: set[str] = set()
        country = self.cfg.get("country")
        for role_id, role in roles.items():
            for term in role.get("search_terms", []):
                for page in range(1, int(self.cfg.get("max_pages", 3)) + 1):
                    params: dict[str, Any] = {"q": term, "page": page}
                    if country:
                        params["country"] = country
                    data = self.http.get_json(self.URL, params=params)
                    jobs = (data or {}).get("jobs", [])
                    if not jobs:
                        break
                    for j in jobs:
                        guid = str(j.get("guid") or j.get("applicationLink") or "")
                        ext = guid.rstrip("/").split("/")[-1].split("?")[0] or guid
                        if not ext or ext in seen or not keep(j.get("title", "")):
                            continue
                        seen.add(ext)
                        restr = _names(j.get("locationRestrictions"))
                        br_ok = (not restr) or any(r.lower() in {"brazil", "brasil", "br"} for r in restr)
                        yield Posting(
                            source=self.name, board=str(j.get("companySlug") or "himalayas"), external_id=ext,
                            company=j.get("companyName", ""), title=j.get("title", "").strip(),
                            text=html_to_text(j.get("description") or j.get("excerpt") or ""),
                            location="Remote" + (f" ({', '.join(restr[:6])}{'…' if len(restr) > 6 else ''})" if restr else " (worldwide)"),
                            url=j.get("applicationLink") or guid, remote=True,
                            published_at=ts_to_iso(j.get("pubDate")),
                            region="REMOTE_BR_OK" if br_ok else "INTL", role_hint=role_id,
                            extra={"seniority": j.get("seniority")},
                        )


class Gupy(Source):
    """Gupy public job portal search (undocumented endpoint used by portal.gupy.io).

    Disabled by default: Gupy's Terms of Use forbid aggregating/copying platform content.
    Only enable for personal use, keep the pace slow and never redistribute posting text.
    """

    name = "gupy"
    URL = "https://portal.gupy.io/api/job-search/jobs"  # endpoint used by portal.gupy.io (changed in 2026)

    def fetch(self, roles, keep: TitleFilter) -> Iterator[Posting]:
        seen: set[str] = set()
        size = int(self.cfg.get("page_size", 20))
        delay = float(self.cfg.get("delay_seconds", 3.0))
        for role_id, role in roles.items():
            for term in role.get("search_terms", []):
                for page in range(int(self.cfg.get("max_pages", 2))):
                    data = self.http.get_json(self.URL, params={"jobName": term, "limit": size, "offset": page * size}, delay=delay)
                    if data is None:
                        log.warning("gupy: search endpoint returned 404 for %r", term)
                        break
                    if not isinstance(data, dict) or "data" not in data:
                        log.warning("gupy: unexpected response shape: %s", list(data)[:8] if isinstance(data, dict) else type(data))
                        break
                    jobs = data.get("data") or []
                    if not jobs:
                        break
                    for j in jobs:
                        ext = str(j.get("id"))
                        if ext in seen or not keep(j.get("name", "")):
                            continue
                        seen.add(ext)
                        loc = ", ".join(x for x in [j.get("city"), j.get("state"), "Brasil"] if x)
                        text = html_to_text(j.get("description") or "")
                        if len(text) < 600 and j.get("jobUrl"):
                            full = self._full_description(j["jobUrl"], delay)
                            if len(full) > len(text):
                                text = full
                        yield Posting(
                            source=self.name, board=str(j.get("careerPageName") or "gupy"), external_id=ext,
                            company=j.get("careerPageName", ""), title=j.get("name", "").strip(),
                            text=text, location=loc,
                            url=j.get("jobUrl", ""), remote=bool(j.get("isRemoteWork")),
                            published_at=ts_to_iso(j.get("publishedDate")), region="BR", role_hint=role_id,
                        )
                    if len(jobs) < size:
                        break

    _SECTION_KEYS = ("description", "responsibilities", "prerequisites", "requirements",
                     "relevantExperiences", "additionalInformation", "aboutCompany")

    def _full_description(self, job_url: str, delay: float) -> str:
        """The search API may return only a summary: read the job page's embedded JSON (__NEXT_DATA__)."""
        page = self.http.get_text(job_url, delay=delay)
        if not page:
            return ""
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', page, re.S)
        parts: list[str] = []
        if m:
            try:
                data = json.loads(m.group(1))
            except ValueError:
                data = None

            def walk(node):
                if isinstance(node, dict):
                    for k, v in node.items():
                        if k in self._SECTION_KEYS and isinstance(v, str) and len(v) > 40:
                            parts.append(html_to_text(v))
                        else:
                            walk(v)
                elif isinstance(node, list):
                    for v in node:
                        walk(v)
            walk(data)
        if not parts:  # fall back to the visible page text
            parts = [html_to_text(page)]
        seen, out = set(), []
        for p in parts:
            if p not in seen:
                seen.add(p)
                out.append(p)
        return "\n\n".join(out)[:20000]
