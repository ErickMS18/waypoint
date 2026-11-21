"""Gap between market demand and your profile."""
from __future__ import annotations

import pandas as pd

from ..taxonomy import get_taxonomy

STATUS_PT = {"has": "Tem", "partial": "Parcial", "missing": "Falta"}


def coverage(level: int) -> float:
    """Level 2 ("used in a project/job") already counts as covering what postings ask for."""
    return min(max(level, 0), 2) / 2


def gap_table(skill_tbl: pd.DataFrame, levels: dict[str, int], top: int | None = 40) -> pd.DataFrame:
    tax = get_taxonomy()
    t = skill_tbl[~skill_tbl["skill_id"].str.startswith("other:")].copy()
    if top:
        t = t.head(top)
    t["level"] = t["skill_id"].map(lambda s: int(levels.get(s, 0)))
    t["coverage"] = t["level"].map(coverage)
    t["status"] = t["level"].map(lambda lv: "has" if lv >= 2 else ("partial" if lv == 1 else "missing"))
    t["priority"] = t["demand"] * (1 - t["coverage"])
    t["effort_hours"] = [round(tax.effort_of(s) * (1 - c)) for s, c in zip(t["skill_id"], t["coverage"])]
    return t.reset_index(drop=True)


def market_fit(gap: pd.DataFrame) -> float:
    """Demand-weighted coverage of the top skills (0..1)."""
    if gap.empty or gap["demand"].sum() == 0:
        return 0.0
    return float((gap["demand"] * gap["coverage"]).sum() / gap["demand"].sum())
