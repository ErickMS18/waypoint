"""Postings you paste yourself: files in inbox/ or text pasted in the UI."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterator

from ..models import text_hash
from .base import Posting, Source, TitleFilter

_FM = re.compile(r"^\s*(title|company|url|location|role)\s*:\s*(.+)$", re.I)


def parse_manual(raw: str, *, default_title: str = "") -> Posting:
    """Parse optional 'key: value' header lines ended by '---', then the posting text."""
    meta: dict[str, str] = {}
    body = raw
    if "\n---" in raw[:2000]:
        head, body = raw.split("\n---", 1)
        for ln in head.splitlines():
            m = _FM.match(ln)
            if m:
                meta[m.group(1).lower()] = m.group(2).strip()
    body = body.strip()
    title = meta.get("title") or default_title or body.splitlines()[0][:120] if body else default_title
    return Posting(
        source="manual", board="inbox", external_id=text_hash(body), company=meta.get("company", ""),
        title=title, text=body, location=meta.get("location", ""), url=meta.get("url", ""),
        role_hint=meta.get("role"),
    )


class Manual(Source):
    name = "manual"

    def __init__(self, http, cfg, root: Path | None = None):
        super().__init__(http, cfg)
        self.dir = (root or Path.cwd()) / self.cfg.get("inbox_dir", "inbox")

    def fetch(self, roles, keep: TitleFilter) -> Iterator[Posting]:
        if not self.dir.exists():
            return
        for f in sorted(self.dir.iterdir()):
            if f.suffix.lower() in {".txt", ".md"} and f.name.lower() != "readme.md":
                p = parse_manual(f.read_text(encoding="utf-8", errors="ignore"), default_title=f.stem)
                if p.text:
                    yield p  # manual postings are never dropped by the title filter
