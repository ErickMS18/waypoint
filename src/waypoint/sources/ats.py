"""Greenhouse, Lever and Ashby public job-board APIs (read-only, no auth).

Docs:
  Greenhouse  https://developers.greenhouse.io/job-board.html
  Lever       https://github.com/lever/postings-api
  Ashby       https://developers.ashbyhq.com/docs/public-job-posting-api
"""
from __future__ import annotations

import logging
from typing import Iterator

from ..textutil import html_to_text
from .base import Posting, Source, TitleFilter, ts_to_iso

log = logging.getLogger("waypoint.sources")


# --------------------------------------------------------------------------- Greenhouse
class Greenhouse(Source):
    name = "greenhouse"
    refetchable = True
    BASE = "https://boards-api.greenhouse.io/v1/boards"

    def _list(self, board: str, content: bool) -> list[dict] | None:
        data = self.http.get_json(f"{self.BASE}/{board}/jobs", params={"content": "true"} if content else None)
        return None if data is None else data.get("jobs", [])

    def _to_posting(self, board: str, j: dict) -> Posting:
        return Posting(
            source=self.name, board=board, external_id=str(j["id"]),
            company=j.get("company_name") or board.replace("-", " ").title(),
            title=j.get("title", "").strip(),
            text=html_to_text(j.get("content", "")),
            location=(j.get("location") or {}).get("name", ""),
            url=j.get("absolute_url", ""),
            published_at=ts_to_iso(j.get("first_published") or j.get("updated_at")),
        )

    def fetch(self, roles, keep: TitleFilter) -> Iterator[Posting]:
        for board in self.cfg.get("boards", []):
            jobs = self._list(board, content=True)
            if jobs is None:
                log.warning("greenhouse board not found: %s", board)
                continue
            for j in jobs:
                if keep(j.get("title", "")):
                    yield self._to_posting(board, j)

    def fetch_one(self, board: str, external_id: str) -> Posting | None:
        j = self.http.get_json(f"{self.BASE}/{board}/jobs/{external_id}")
        return None if j is None else self._to_posting(board, j)

    def check(self):
        out = []
        for b in self.cfg.get("boards", []):
            jobs = self._list(b, content=False)
            out.append((b, None if jobs is None else len(jobs)))
        return out


# --------------------------------------------------------------------------- Lever
class Lever(Source):
    name = "lever"
    refetchable = True
    HOSTS = ("https://api.lever.co/v0/postings", "https://api.eu.lever.co/v0/postings")

    def _list(self, site: str) -> tuple[list[dict] | None, str]:
        for host in self.HOSTS:
            data = self.http.get_json(f"{host}/{site}", params={"mode": "json"})
            if data is not None:
                return data, host
        return None, ""

    @staticmethod
    def _text(j: dict) -> str:
        parts = [j.get("descriptionPlain") or html_to_text(j.get("description", ""))]
        for lst in j.get("lists", []) or []:
            parts.append(f"{lst.get('text', '')}\n{html_to_text(lst.get('content', ''))}")
        parts.append(j.get("additionalPlain") or html_to_text(j.get("additional", "")))
        return "\n\n".join(p.strip() for p in parts if p and p.strip())

    def _to_posting(self, site: str, j: dict) -> Posting:
        cats = j.get("categories") or {}
        return Posting(
            source=self.name, board=site, external_id=str(j["id"]),
            company=site.replace("-", " ").title(), title=(j.get("text") or "").strip(),
            text=self._text(j), location=cats.get("location", "") or "",
            url=j.get("hostedUrl", ""), remote=(j.get("workplaceType") == "remote"),
            published_at=ts_to_iso(j.get("createdAt")),
        )

    def fetch(self, roles, keep: TitleFilter) -> Iterator[Posting]:
        for site in self.cfg.get("sites", []):
            data, _ = self._list(site)
            if data is None:
                log.warning("lever site not found: %s", site)
                continue
            for j in data:
                if keep(j.get("text", "")):
                    yield self._to_posting(site, j)

    def fetch_one(self, board: str, external_id: str) -> Posting | None:
        for host in self.HOSTS:
            j = self.http.get_json(f"{host}/{board}/{external_id}", params={"mode": "json"})
            if j is not None:
                return self._to_posting(board, j)
        return None

    def check(self):
        out = []
        for s in self.cfg.get("sites", []):
            data, _ = self._list(s)
            out.append((s, None if data is None else len(data)))
        return out


# --------------------------------------------------------------------------- Ashby
class Ashby(Source):
    name = "ashby"
    refetchable = True
    BASE = "https://api.ashbyhq.com/posting-api/job-board"

    def _list(self, board: str) -> list[dict] | None:
        data = self.http.get_json(f"{self.BASE}/{board}", params={"includeCompensation": "false"})
        return None if data is None else [j for j in data.get("jobs", []) if j.get("isListed", True)]

    def _to_posting(self, board: str, j: dict) -> Posting:
        locs = [j.get("location") or ""] + [
            (s.get("location") if isinstance(s, dict) else str(s)) or "" for s in j.get("secondaryLocations") or []
        ]
        return Posting(
            source=self.name, board=board, external_id=str(j["id"]),
            company=board.replace("-", " ").title(), title=(j.get("title") or "").strip(),
            text=j.get("descriptionPlain") or html_to_text(j.get("descriptionHtml", "")),
            location=" / ".join(x for x in locs if x),
            url=j.get("jobUrl", ""),
            remote=bool(j.get("isRemote")) or j.get("workplaceType") == "Remote",
            published_at=ts_to_iso(j.get("publishedAt")),
        )

    def fetch(self, roles, keep: TitleFilter) -> Iterator[Posting]:
        for board in self.cfg.get("boards", []):
            jobs = self._list(board)
            if jobs is None:
                log.warning("ashby board not found: %s", board)
                continue
            for j in jobs:
                if keep(j.get("title", "")):
                    yield self._to_posting(board, j)

    def fetch_one(self, board: str, external_id: str) -> Posting | None:
        for j in self._list(board) or []:
            if str(j.get("id")) == str(external_id):
                return self._to_posting(board, j)
        return None

    def check(self):
        out = []
        for b in self.cfg.get("boards", []):
            jobs = self._list(b)
            out.append((b, None if jobs is None else len(jobs)))
        return out
