"""Core data models."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

Seniority = Literal["intern", "junior", "mid", "senior", "staff_plus", "unknown"]
Requirement = Literal["required", "nice_to_have"]
WorkModel = Literal["remote", "hybrid", "onsite", "unknown"]

SENIORITY_ORDER = ["intern", "junior", "mid", "senior", "staff_plus"]
SENIORITY_PT = {
    "intern": "Estágio",
    "junior": "Júnior",
    "mid": "Pleno",
    "senior": "Sênior",
    "staff_plus": "Staff+/Especialista",
    "unknown": "Não informada",
}
REGION_PT = {
    "BR": "Brasil",
    "REMOTE_BR_OK": "Remoto internacional (aceita Brasil)",
    "INTL": "Internacional",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def text_hash(text: str) -> str:
    norm = " ".join(text.split()).lower()
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


class Job(BaseModel):
    """A normalized job posting."""

    job_key: str  # "<source>:<board>:<external_id>"
    source: str
    board: str = ""
    external_id: str
    company: str
    title: str
    location: str = ""
    region: str = "INTL"
    remote: bool = False
    url: str = ""
    published_at: Optional[str] = None
    collected_at: str = Field(default_factory=now_iso)
    role: str = ""
    lang: str = "en"
    text: str

    @property
    def hash(self) -> str:
        return text_hash(self.text)


class SkillMention(BaseModel):
    name: str
    requirement: Requirement = "required"
    evidence: Optional[str] = None

    @field_validator("requirement", mode="before")
    @classmethod
    def _norm_req(cls, v):  # tolerate LLM variants
        v = str(v or "required").strip().lower().replace("-", "_").replace(" ", "_")
        if v in {"nice_to_have", "nice", "preferred", "desirable", "plus", "bonus", "optional", "diferencial", "desejavel", "desejável"}:
            return "nice_to_have"
        return "required"


class JobExtraction(BaseModel):
    seniority: Seniority = "unknown"
    years_experience_min: Optional[int] = None
    work_model: WorkModel = "unknown"
    skills: list[SkillMention] = Field(default_factory=list)
    summary: str = ""

    @field_validator("seniority", mode="before")
    @classmethod
    def _norm_sen(cls, v):
        v = str(v or "unknown").strip().lower().replace("-", "_").replace(" ", "_")
        aliases = {
            "internship": "intern", "estagio": "intern", "estágio": "intern", "entry": "junior",
            "entry_level": "junior", "jr": "junior", "júnior": "junior", "pleno": "mid",
            "mid_level": "mid", "middle": "mid", "sr": "senior", "sênior": "senior",
            "staff": "staff_plus", "principal": "staff_plus", "lead": "staff_plus",
            "staff+": "staff_plus", "specialist": "staff_plus", "especialista": "staff_plus",
        }
        v = aliases.get(v, v)
        return v if v in {"intern", "junior", "mid", "senior", "staff_plus"} else "unknown"

    @field_validator("work_model", mode="before")
    @classmethod
    def _norm_wm(cls, v):
        v = str(v or "unknown").strip().lower()
        mapping = {"remoto": "remote", "híbrido": "hybrid", "hibrido": "hybrid", "presencial": "onsite", "on-site": "onsite", "on_site": "onsite"}
        v = mapping.get(v, v)
        return v if v in {"remote", "hybrid", "onsite"} else "unknown"

    @field_validator("years_experience_min", mode="before")
    @classmethod
    def _norm_years(cls, v):
        if v in (None, "", "null"):
            return None
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None


class CanonicalSkill(BaseModel):
    skill_id: str  # taxonomy id, or "other:<slug>" when unknown
    name: str
    requirement: Requirement


class ProfileSkill(BaseModel):
    skill_id: str
    name: str
    level: int = Field(ge=0, le=3)  # 0 none, 1 exposure, 2 used in projects/work, 3 strong
    evidence: Optional[str] = None
