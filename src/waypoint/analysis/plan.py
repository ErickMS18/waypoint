"""Focus-weighted study plan.

Design rules (from the project brief):
* Hours are split by your focus weights; exploration hours are protected.
* Nothing is ever labeled irrelevant: conflicts become explicit trade-off questions.
* Interests outside the career focus get "bridges" to the career, not cuts.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

import pandas as pd
from pydantic import BaseModel, Field

from ..settings import RESOURCES, load_yaml
from ..taxonomy import get_taxonomy
from .market import cooccurrence

NON_STUDY_CATS = {"spoken", "soft"}


@dataclass
class CareerItem:
    skill_id: str
    name: str
    status: str
    demand: float
    share_required: float
    priority: float
    effort_hours: int
    weeks: float
    why: str
    pairs_with: list[str] = field(default_factory=list)


@dataclass
class ProjectIdea:
    title: str
    description: str
    skills: list[str]
    deliverable: str = ""
    why: str = ""
    bridge_interest: str = ""


@dataclass
class Bridge:
    interest: str
    idea: str
    career_skills: list[str]


@dataclass
class Plan:
    weekly_hours: float
    hours: dict[str, float]
    protected_exploration: bool
    career: list[CareerItem]
    quick_wins: list[CareerItem]
    this_week: list[dict[str, Any]]
    projects: list[ProjectIdea]
    exploration: list[dict[str, str]]
    interests: list[dict[str, Any]]
    bridges: list[Bridge]
    tradeoffs: list[str]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------------------------- LLM ideas
class _LLMProject(BaseModel):
    title: str
    description: str
    skills: list[str] = Field(default_factory=list)
    deliverable: str = ""
    why: str = ""
    bridge_interest: str = ""


class _LLMBridge(BaseModel):
    interest: str
    idea: str
    career_skills: list[str] = Field(default_factory=list)


class _LLMIdeas(BaseModel):
    projects: list[_LLMProject] = Field(default_factory=list)
    bridges: list[_LLMBridge] = Field(default_factory=list)


IDEAS_SYSTEM = (
    "You are a pragmatic career mentor for a computer-science student. You never call any of the "
    "person's interests or projects irrelevant; you connect them to their goals. Answer with JSON only."
)
IDEAS_USER = """Target roles: {roles}
Skills the person already has (strong/working): {has}
Highest-priority gaps (from real job postings): {gaps}
Personal interests (outside career focus): {interests}
Exploration topics: {exploration}

Write in Portuguese (Brazil).
1. Propose 3 practical portfolio projects (each doable in 2-4 weeks at ~{career_hours}h/week) that close
   the top gaps while reusing what the person already knows. When natural, connect a project to one of
   the interests (fill bridge_interest).
2. For EACH interest, propose one concrete "bridge": a small project or angle that links the interest
   to the target roles' skills, without turning the hobby into an obligation.

JSON: {{"projects": [{{"title": "", "description": "", "skills": [""], "deliverable": "", "why": "", "bridge_interest": ""}}],
"bridges": [{{"interest": "", "idea": "", "career_skills": [""]}}]}}
"""


# ----------------------------------------------------------------------------- planner
def split_hours(focus: dict[str, Any]) -> dict[str, float]:
    total = float(focus.get("weekly_hours", 10))
    w = focus.get("weights", {"carreira": 50, "exploracao": 30, "interesses": 20})
    return {k: round(total * float(v) / 100, 1) for k, v in w.items()}


def _template_projects(gap: pd.DataFrame, top: int = 3) -> list[ProjectIdea]:
    prio = dict(zip(gap["skill_id"], gap["priority"]))
    names = dict(zip(gap["skill_id"], gap["name"]))
    scored = []
    for p in load_yaml(RESOURCES / "projects.yaml")["projects"]:
        score = sum(prio.get(s, 0) for s in p["skills"])
        if score > 0:
            trains = [names[s] for s in p["skills"] if prio.get(s, 0) > 0]
            scored.append((score, ProjectIdea(title=p["title"], description=p["description"],
                                              skills=[get_taxonomy().name_of(s) for s in p["skills"]],
                                              deliverable=p.get("deliverable", ""),
                                              why="Treina: " + ", ".join(trains))))
    return [p for _, p in sorted(scored, key=lambda x: -x[0])[:top]]


def build_plan(gap: pd.DataFrame, focus: dict[str, Any], *, roles: list[str],
               skills_df: Optional[pd.DataFrame] = None, emerging_df: Optional[pd.DataFrame] = None,
               client=None, max_items: int = 6) -> Plan:
    hours = split_hours(focus)
    career_h = max(hours.get("carreira", 0.0), 0.1)
    notes: list[str] = []

    todo = gap[gap["priority"] > 0].sort_values("priority", ascending=False)
    ongoing = todo[todo["category"].isin(NON_STUDY_CATS)]
    for _, r in ongoing.iterrows():
        notes.append(f"{r['name']} aparece em {r['share_any']:.0%} das vagas. Não entra nas horas do plano "
                     "(é prática contínua), mas vale ficar de olho.")
    todo = todo[~todo["category"].isin(NON_STUDY_CATS)]
    career: list[CareerItem] = []
    for _, r in todo.head(max_items).iterrows():
        pairs = cooccurrence(skills_df, r["skill_id"]) if skills_df is not None else []
        career.append(CareerItem(
            skill_id=r["skill_id"], name=r["name"], status=r["status"], demand=float(r["demand"]),
            share_required=float(r["share_required"]), priority=float(r["priority"]),
            effort_hours=int(r["effort_hours"]), weeks=round(r["effort_hours"] / career_h, 1),
            why=f"aparece em {r['share_any']:.0%} das vagas ({r['share_required']:.0%} como obrigatória)",
            pairs_with=pairs,
        ))
    quick = [c for c in career if c.status == "partial"][:3]

    # this week: focus on at most 2 career items, hours proportional to priority
    active = career[:2]
    tot = sum(c.priority for c in active) or 1
    this_week = [{"foco": "carreira", "item": c.name, "horas": round(career_h * c.priority / tot, 1)} for c in active]

    # exploration (protected)
    exp_cfg = focus.get("exploration", {}) or {}
    exploration = [{"name": t, "why": "tópico que você escolheu explorar"} for t in exp_cfg.get("topics", []) or []]
    if exp_cfg.get("include_emerging", True) and emerging_df is not None and not emerging_df.empty:
        # exploration = things NOT already on the career list (otherwise it is just more career time)
        in_career = {c.skill_id for c in career}
        for _, r in emerging_df.iterrows():
            if r["skill_id"] in in_career or get_taxonomy().category_of(r["skill_id"]) in NON_STUDY_CATS:
                continue
            exploration.append({"name": r["name"], "why": r["why"]})
    if hours.get("exploracao"):
        this_week.append({"foco": "exploração", "item": exploration[0]["name"] if exploration else "livre (escolha algo novo)",
                          "horas": hours["exploracao"]})

    interests = [{"name": i, "horas": round(hours.get("interesses", 0) / max(len(focus.get("interests") or []), 1), 1)}
                 for i in (focus.get("interests") or [])]
    if hours.get("interesses"):
        this_week.append({"foco": "interesses", "item": ", ".join(i["name"] for i in interests) or "livre",
                          "horas": hours["interesses"]})

    # projects + bridges
    projects: list[ProjectIdea] = []
    bridges: list[Bridge] = []
    if client is not None:
        try:
            has = gap[gap["status"] == "has"]["name"].tolist()[:15]
            ideas = client.complete_model(IDEAS_SYSTEM, IDEAS_USER.format(
                roles=", ".join(roles), has=", ".join(has) or "-",
                gaps=", ".join(f"{c.name} ({c.why})" for c in career) or "-",
                interests=", ".join(focus.get("interests") or []) or "nenhum informado",
                exploration=", ".join(e["name"] for e in exploration) or "-", career_hours=career_h,
            ), _LLMIdeas, cache_tag="ideas-v1")
            projects = [ProjectIdea(**p.model_dump()) for p in ideas.projects[:3]]
            bridges = [Bridge(**b.model_dump()) for b in ideas.bridges]
        except Exception as e:  # fall back to templates, but say so
            notes.append(f"Ideias via LLM indisponíveis ({type(e).__name__}); usei os modelos de projeto locais.")
    if not projects:
        projects = _template_projects(gap)
    if (focus.get("interests") or []) and not bridges:
        notes.append("Configure uma chave de LLM para receber pontes entre seus interesses e a carreira.")

    # trade-offs: explicit questions, never automatic cuts
    tradeoffs: list[str] = []
    total_effort = sum(c.effort_hours for c in career)
    if total_effort and career_h:
        weeks_now = total_effort / career_h
        tradeoffs.append(
            f"Com {career_h:g}h/semana em carreira, os {len(career)} itens prioritários levam ~{math.ceil(weeks_now)} semanas."
        )
        if hours.get("interesses", 0) >= 1:
            w2 = total_effort / (career_h + 1)
            tradeoffs.append(
                f"Mover 1h/semana de interesses para carreira anteciparia isso em ~{max(1, round(weeks_now - w2))} "
                "semana(s), em troca de menos tempo para seus interesses. Quer mudar os pesos? (interface: Plano → Focos e pesos)"
            )
        if exp_cfg.get("protected", True) and hours.get("exploracao"):
            tradeoffs.append(f"As {hours['exploracao']:g}h de exploração estão protegidas e não são realocadas automaticamente.")

    return Plan(weekly_hours=float(focus.get("weekly_hours", 10)), hours=hours,
                protected_exploration=bool(exp_cfg.get("protected", True)), career=career, quick_wins=quick,
                this_week=this_week, projects=projects, exploration=exploration[:8], interests=interests,
                bridges=bridges, tradeoffs=tradeoffs, notes=notes)
