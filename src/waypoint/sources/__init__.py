from __future__ import annotations

from pathlib import Path
from typing import Any

from ..http import Http
from .ats import Ashby, Greenhouse, Lever
from .base import Posting, Source
from .manual import Manual, parse_manual
from .search import Gupy, Himalayas

REGISTRY: dict[str, type[Source]] = {
    "greenhouse": Greenhouse,
    "lever": Lever,
    "ashby": Ashby,
    "himalayas": Himalayas,
    "gupy": Gupy,
    "manual": Manual,
}


def build_sources(sources_cfg: dict[str, Any], http: Http, root: Path, only: list[str] | None = None) -> list[Source]:
    out: list[Source] = []
    for name, cls in REGISTRY.items():
        cfg = sources_cfg.get(name) or {}
        if only and name not in only:
            continue
        if not cfg.get("enabled", name == "manual"):
            continue
        out.append(Manual(http, cfg, root) if cls is Manual else cls(http, cfg))
    return out


__all__ = ["Posting", "Source", "REGISTRY", "build_sources", "parse_manual", "Greenhouse", "Lever", "Ashby", "Himalayas", "Gupy", "Manual"]
