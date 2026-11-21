"""Skill extraction: LLM extractor, dictionary baseline and canonicalization."""
from __future__ import annotations

import logging
import re
from typing import Callable, Iterable

from ..db import DB
from ..models import CanonicalSkill, Job, JobExtraction, SkillMention, text_hash
from ..roles import seniority_heuristic
from ..taxonomy import Taxonomy, get_taxonomy
from ..textutil import fold, trim_for_llm

log = logging.getLogger("rota.extract")

PROMPT_VERSION = "job-v1"

GUIDELINES = """\
Extract what a CANDIDATE needs for this job. Rules:
1. Skills = technical skills, tools, frameworks, libraries, cloud services, methods/techniques
   (e.g. "A/B testing", "RAG", "feature engineering"), math/statistics areas and spoken languages.
   Include soft skills only when explicitly demanded (e.g. "strong communication").
2. requirement = "nice_to_have" when the posting marks it as optional: sections such as
   "Nice to have", "Preferred", "Bonus", "Plus", "Diferenciais", "Desejável", or phrases like
   "is a plus", "preferably", "ideally", "familiarity is a bonus", "será um diferencial".
   Everything else the candidate is expected to know or use is "required".
3. Skills that appear only in the responsibilities count when the candidate will use them hands-on
   ("build RAG pipelines" -> RAG, required). Ignore technologies that only describe the company's
   product, the benefits, the hiring process or legal text.
4. One skill per item. Split combinations ("Python/SQL" -> Python and SQL). Do not invent skills.
   Generic phrases like "AI" or "technology" are not skills; "machine learning" and "LLMs" are.
5. Prefer the canonical names listed below when one fits; otherwise use the short standard name.
6. seniority: use the title first (intern/estágio -> intern; junior/jr/entry/associate -> junior;
   pleno/mid/II -> mid; senior/sr/III -> senior; staff/principal/lead/specialist/especialista ->
   staff_plus). If the title says nothing, use the minimum years of experience required:
   0-1 -> junior, 2-4 -> mid, 5-7 -> senior, 8+ -> staff_plus. Otherwise "unknown".
"""

SYSTEM = (
    "You are a meticulous technical recruiter who turns job postings into structured data. "
    "You answer with a single JSON object and nothing else."
)

USER_TEMPLATE = """{guidelines}
Canonical skill names (by category):
{vocabulary}

Return JSON with exactly these keys:
{{"seniority": "intern|junior|mid|senior|staff_plus|unknown",
  "years_experience_min": <int or null>,
  "work_model": "remote|hybrid|onsite|unknown",
  "skills": [{{"name": "<skill>", "requirement": "required|nice_to_have", "evidence": "<max 12 words copied from the posting>"}}],
  "summary": "<one sentence in Portuguese describing the role>"}}

JOB TITLE: {title}
COMPANY: {company}
LOCATION: {location}
POSTING:
\"\"\"
{text}
\"\"\"
"""


def build_prompt(job: Job, tax: Taxonomy | None = None) -> str:
    tax = tax or get_taxonomy()
    return USER_TEMPLATE.format(
        guidelines=GUIDELINES, vocabulary=tax.prompt_vocabulary(), title=job.title,
        company=job.company, location=job.location, text=trim_for_llm(job.text),
    )


def extract_llm(job: Job, client) -> JobExtraction:
    return client.complete_model(SYSTEM, build_prompt(job), JobExtraction, cache_tag=PROMPT_VERSION)


# ----------------------------------------------------------------------------- baseline
_NICE_HDR = re.compile(
    r"(nice[- ]to[- ]have|preferred|preferable|bonus|pluses|plus points|good to have|"
    r"diferencia(l|is)|desejave(l|is)|seria (um )?(otimo|legal)|extra points|it'?s a plus|we'?d love)", re.I)
_REQ_HDR = re.compile(
    r"(requirements|requisitos|qualifications|qualificac|what you('| wi)ll need|what we('re| are) looking for|"
    r"o que (esperamos|buscamos)|must[- ]have|you have|you bring|obrigatori|minimum|about you|sobre voce|"
    r"responsibilit|responsabilidades|what you'?ll do|o que voce (vai|ira) fazer|atividades|atribuic)", re.I)
_INLINE_NICE = re.compile(
    r"(is a plus|a plus\b|nice to have|preferred|preferably|ideally|bonus|desejavel|diferencial|"
    r"sera um diferencial|e um plus|good to have|familiarity with .* (is|a) (plus|bonus))", re.I)


def extract_baseline(job: Job, tax: Taxonomy | None = None) -> JobExtraction:
    """Dictionary matcher with section awareness (the comparison point for the LLM)."""
    tax = tax or get_taxonomy()
    found: dict[str, str] = {}
    section = "required"
    for line in job.text.splitlines():
        f = fold(line)
        is_header = len(f) < 80 and not f.startswith("- ")
        if is_header and _NICE_HDR.search(f):
            section = "nice_to_have"
        elif is_header and _REQ_HDR.search(f):
            section = "required"
        level = "nice_to_have" if (section == "nice_to_have" or _INLINE_NICE.search(f)) else "required"
        for sid in tax.find_in_text(line):
            if found.get(sid) != "required":
                found[sid] = level
    skills = [SkillMention(name=tax.name_of(s), requirement=lvl) for s, lvl in sorted(found.items())]
    return JobExtraction(seniority=seniority_heuristic(job.title, job.text), skills=skills)


# ----------------------------------------------------------------------------- canonicalize
def canonicalize(ext: JobExtraction, tax: Taxonomy | None = None) -> list[CanonicalSkill]:
    tax = tax or get_taxonomy()
    out: dict[str, CanonicalSkill] = {}
    for m in ext.skills:
        for sid in tax.canonicalize(m.name):
            prev = out.get(sid)
            if prev is None or (prev.requirement == "nice_to_have" and m.requirement == "required"):
                out[sid] = CanonicalSkill(skill_id=sid, name=tax.name_of(sid), requirement=m.requirement)
    return list(out.values())


# ----------------------------------------------------------------------------- batch runner
def run_extraction(db: DB, jobs: Iterable[Job], extractor: str = "llm", client=None, *, force: bool = False,
                   progress: Callable[[int, int, Job], None] | None = None) -> dict[str, int]:
    jobs = list(jobs)
    done = errors = skipped = 0
    for i, job in enumerate(jobs, 1):
        h = text_hash(job.text)
        prev = db.extraction(job.job_key, extractor)
        if prev and not force and prev[1].get("text_hash") == h and (
            extractor != "llm" or prev[1].get("prompt_version") == PROMPT_VERSION
        ):
            skipped += 1
            continue
        if progress:
            progress(i, len(jobs), job)
        try:
            if extractor == "llm":
                ext = extract_llm(job, client)
                model = client.model_id
            else:
                ext = extract_baseline(job)
                model = "taxonomy-v1"
            db.save_extraction(job.job_key, extractor, ext, model=model, prompt_version=PROMPT_VERSION, text_hash_=h)
            db.conn.commit()
            done += 1
        except Exception as e:  # keep going; report at the end
            log.error("extraction failed for %s: %s", job.job_key, e)
            errors += 1
            if errors >= 5 and done == 0:
                raise
    return {"extracted": done, "skipped": skipped, "errors": errors}
