"""Your profile: resume parsing (local), PII redaction, skill levels and manual overrides.

Everything is stored under profile/ (git-ignored). Only the *redacted* resume text is
ever sent to the LLM provider.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

from .models import ProfileSkill, now_iso
from .taxonomy import Taxonomy, get_taxonomy
from .textutil import fold

PROFILE_PROMPT_VERSION = "profile-v1"


# ----------------------------------------------------------------------------- reading
def read_resume(path: Path) -> str:
    suf = path.suffix.lower()
    if suf == ".pdf":
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    if suf == ".docx":
        import docx
        return "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
    return path.read_text(encoding="utf-8", errors="ignore")


# ----------------------------------------------------------------------------- redaction
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?:\+?\d{1,3}[\s.-]?)?\(?\d{2}\)?[\s.-]?\d{4,5}[\s.-]?\d{4}")
_URL = re.compile(r"(?:https?://|www\.)\S+|\b(?:linkedin\.com|github\.com)/\S+", re.I)
_CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
_CEP = re.compile(r"\b\d{5}-?\d{3}\b")


def redact(text: str, extra_terms: list[str] | None = None) -> str:
    """Remove name (first line), contacts, links and documents before sending to an LLM."""
    lines = [ln for ln in text.splitlines()]
    first = next((ln.strip() for ln in lines if ln.strip()), "")
    name_tokens = [t for t in re.findall(r"[A-Za-zÀ-ÿ]{3,}", first) if t.lower() not in {"cv", "resume", "curriculo"}]
    out = text.replace(first, "[NOME]", 1) if first else text
    for pat, tag in ((_EMAIL, "[EMAIL]"), (_URL, "[LINK]"), (_CPF, "[DOC]"), (_PHONE, "[TELEFONE]"), (_CEP, "[CEP]")):
        out = pat.sub(tag, out)
    for term in [*name_tokens, *(extra_terms or [])]:
        if term.strip():
            out = re.sub(rf"\b{re.escape(term.strip())}\b", "[NOME]", out, flags=re.I)
    return out


# ----------------------------------------------------------------------------- extraction
class _LLMSkill(BaseModel):
    name: str
    level: int = Field(ge=0, le=3)
    evidence: Optional[str] = None


class _LLMProfile(BaseModel):
    skills: list[_LLMSkill]


PROFILE_SYSTEM = "You assess resumes precisely and conservatively. Answer with one JSON object only."
PROFILE_USER = """List the skills this person demonstrably has, with a level:
3 = strong: used professionally or as the core of a substantial project with results
2 = working: used hands-on in a project, research or job
1 = exposure: only coursework, a listed keyword without evidence, or self-declared "basic"
Only include skills supported by the resume. One skill per item; split combinations.
Prefer these canonical names when one fits:
{vocabulary}

Return: {{"skills": [{{"name": "...", "level": 1-3, "evidence": "<max 12 words from the resume>"}}]}}

RESUME (personal data removed):
\"\"\"
{resume}
\"\"\"
"""


def extract_profile_llm(resume_text: str, client, tax: Taxonomy | None = None) -> list[ProfileSkill]:
    tax = tax or get_taxonomy()
    prompt = PROFILE_USER.format(vocabulary=tax.prompt_vocabulary(), resume=resume_text[:15000])
    res = client.complete_model(PROFILE_SYSTEM, prompt, _LLMProfile, cache_tag=PROFILE_PROMPT_VERSION)
    return _merge([(sid, s.level, s.evidence) for s in res.skills for sid in tax.canonicalize(s.name)], tax)


_BASIC = re.compile(r"(basico|basic|iniciante|beginner)", re.I)


def extract_profile_baseline(resume_text: str, tax: Taxonomy | None = None) -> list[ProfileSkill]:
    """No-LLM fallback: dictionary matches, level by how often the skill shows up."""
    tax = tax or get_taxonomy()
    counts: dict[str, int] = {}
    basic: set[str] = set()
    for line in resume_text.splitlines():
        for sid in tax.find_in_text(line):
            counts[sid] = counts.get(sid, 0) + 1
            if _BASIC.search(fold(line)):
                basic.add(sid)
    items = [(sid, 1 if sid in basic and n < 3 else (2 if n >= 2 else 1), None) for sid, n in counts.items()]
    return _merge(items, tax)


def _merge(items, tax: Taxonomy) -> list[ProfileSkill]:
    best: dict[str, ProfileSkill] = {}
    for sid, level, ev in items:
        if sid.startswith("other:") and level < 2:
            continue
        if sid not in best or level > best[sid].level:
            best[sid] = ProfileSkill(skill_id=sid, name=tax.name_of(sid), level=int(level), evidence=ev)
    return sorted(best.values(), key=lambda s: (-s.level, s.name.lower()))


# ----------------------------------------------------------------------------- storage
class Profile(BaseModel):
    created_at: str = Field(default_factory=now_iso)
    source_file: str = ""
    method: str = ""
    skills: list[ProfileSkill] = Field(default_factory=list)

    def levels(self) -> dict[str, int]:
        return {s.skill_id: s.level for s in self.skills}


def profile_path(profile_dir: Path) -> Path:
    return profile_dir / "profile.json"


def overrides_path(profile_dir: Path) -> Path:
    return profile_dir / "overrides.yaml"


def save_profile(profile_dir: Path, profile: Profile) -> Path:
    profile_dir.mkdir(parents=True, exist_ok=True)
    p = profile_path(profile_dir)
    p.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    return p


def load_overrides(profile_dir: Path) -> dict[str, int]:
    p = overrides_path(profile_dir)
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {str(k): int(v) for k, v in (data.get("levels") or {}).items()}


def save_overrides(profile_dir: Path, levels: dict[str, int]) -> None:
    profile_dir.mkdir(parents=True, exist_ok=True)
    body = {"levels": dict(sorted(levels.items()))}
    overrides_path(profile_dir).write_text(
        "# Ajustes manuais de nível (0 = não tenho, 1 = exposição, 2 = uso em projetos, 3 = forte).\n"
        + yaml.safe_dump(body, allow_unicode=True, sort_keys=False), encoding="utf-8")


def load_profile(profile_dir: Path) -> Optional[Profile]:
    p = profile_path(profile_dir)
    if not p.exists():
        return None
    return Profile.model_validate(json.loads(p.read_text(encoding="utf-8")))


def effective_levels(profile_dir: Path) -> dict[str, int]:
    prof = load_profile(profile_dir)
    levels = prof.levels() if prof else {}
    levels.update(load_overrides(profile_dir))
    return levels


def build_profile(resume_path: Path, profile_dir: Path, client=None, extra_redact: list[str] | None = None) -> Profile:
    text = read_resume(resume_path)
    safe = redact(text, extra_redact)
    (profile_dir).mkdir(parents=True, exist_ok=True)
    (profile_dir / "resume_redacted.txt").write_text(safe, encoding="utf-8")
    if client is not None:
        skills, method = extract_profile_llm(safe, client), f"llm:{client.model_id}"
    else:
        skills, method = extract_profile_baseline(text), "baseline"
    prof = Profile(source_file=resume_path.name, method=method, skills=skills)
    save_profile(profile_dir, prof)
    return prof
