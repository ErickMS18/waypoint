"""Role matching by title, seniority heuristics and region classification."""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any

from .textutil import fold

_BR = re.compile(
    r"\b(brazil|brasil|sao paulo|rio de janeiro|curitiba|belo horizonte|porto alegre|florianopolis|"
    r"recife|campinas|brasilia|salvador|fortaleza|goiania|joinville|blumenau|londrina|maringa|"
    r"sp|rj|pr|sc|mg|rs)\b"
)


class RoleMatcher:
    def __init__(self, roles: dict[str, dict[str, Any]]):
        self.roles = []
        for rid, r in roles.items():
            inc = [re.compile(p, re.I) for p in r.get("title_include", [])]
            exc = [re.compile(p, re.I) for p in r.get("title_exclude", [])]
            self.roles.append((rid, inc, exc))

    def match(self, title: str) -> str | None:
        t = fold(title)
        for rid, inc, exc in self.roles:
            if any(p.search(t) for p in inc) and not any(p.search(t) for p in exc):
                return rid
        return None


_SEN_TITLE = [
    ("intern", r"\b(intern|internship|estagi\w*|trainee|aprendiz)\b"),
    ("staff_plus", r"\b(staff|principal|distinguished|lead|lider|tech lead|especialista|specialist|expert)\b"),
    ("senior", r"\b(senior|sr|snr)\b\.?|\bsenior\b|\biii\b"),
    ("junior", r"\b(junior|jr|entry[- ]level|associate|new grad|graduate)\b\.?"),
    ("mid", r"\b(pleno|mid[- ]level|mid|ii)\b"),
]
_YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:-\s*\d+\s*)?(?:years|yrs|anos)", re.I)


def seniority_from_title(title: str) -> str:
    t = fold(title)
    for level, pat in _SEN_TITLE:
        if re.search(pat, t):
            return level
    return "unknown"


def seniority_heuristic(title: str, text: str) -> str:
    """Title first; otherwise minimum years of experience mentioned in the text."""
    s = seniority_from_title(title)
    if s != "unknown":
        return s
    years = [int(m.group(1)) for m in _YEARS.finditer(text) if int(m.group(1)) <= 20]
    if not years:
        return "unknown"
    y = min(years)
    if y <= 1:
        return "junior"
    if y <= 4:
        return "mid"
    if y <= 7:
        return "senior"
    return "staff_plus"


def region_of(location: str, *, source: str = "", remote_br_ok: bool = False) -> str:
    if source == "gupy":
        return "BR"
    if _BR.search(fold(location or "")):
        # "Remote - Brazil" from an international board is still a Brazil-based role
        return "BR"
    if remote_br_ok:
        return "REMOTE_BR_OK"
    return "INTL"


@lru_cache(maxsize=8)
def _cached_matcher(key: str, roles_repr: str) -> RoleMatcher:  # pragma: no cover - tiny cache
    import json
    return RoleMatcher(json.loads(roles_repr))


def get_matcher(roles: dict[str, dict[str, Any]]) -> RoleMatcher:
    import json
    return _cached_matcher("m", json.dumps(roles, sort_keys=True))
