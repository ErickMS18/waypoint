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

Write in {language}.
1. Propose 3 practical portfolio projects (each doable in 2-4 weeks at ~{career_hours}h/week) that close
   the top gaps while reusing what the person already knows. When natural, connect a project to one of
   the interests (fill bridge_interest).
2. For EACH interest, propose one concrete "bridge": a small project or angle that links the interest
   to the target roles' skills, without turning the hobby into an obligation.

JSON: {{"projects": [{{"title": "", "description": "", "skills": [""], "deliverable": "", "why": "", "bridge_interest": ""}}],
"bridges": [{{"interest": "", "idea": "", "career_skills": [""]}}]}}
"""


# ----------------------------------------------------------------------------- texts (pt / en)
TXT = {
    "pt": {
        "ongoing": "{name} aparece em {share:.0%} das vagas. Não entra nas horas do plano (é prática contínua), mas vale ficar de olho.",
        "why": "aparece em {share:.0%} das vagas ({req:.0%} como obrigatória)",
        "chosen": "tópico que você escolheu explorar",
        "rising": "subiu {v:.0f} p.p. nas vagas recentes",
        "new": "aparece em {v:.0f} vagas e ainda não está na taxonomia",
        "free_explore": "Algo novo à sua escolha", "free": "Tempo para seus interesses", "trains": "Treina: ",
        "no_interests": "nenhum informado",
        "llm_fail": "Ideias via IA indisponíveis ({err}); usei os modelos de projeto locais.",
        "need_key": "Configure uma chave de IA para receber pontes entre seus interesses e a carreira.",
        "t_weeks": "Com {h:g}h/semana em carreira, os {n} itens prioritários levam ~{w} semanas.",
        "t_move": "Mover 1h/semana de interesses para carreira anteciparia isso em ~{w} semana(s), em troca de menos tempo para seus interesses. Quer mudar os pesos? (Plano → Focos e pesos)",
        "t_protected": "As {h:g}h de exploração estão protegidas e não são realocadas automaticamente.",
        "language": "Portuguese (Brazil)",
    },
    "en": {
        "ongoing": "{name} shows up in {share:.0%} of postings. It is not part of the plan's hours (it is continuous practice), but keep an eye on it.",
        "why": "in {share:.0%} of postings ({req:.0%} as required)",
        "chosen": "a topic you chose to explore",
        "rising": "up {v:.0f} p.p. in recent postings",
        "new": "in {v:.0f} postings and not in the taxonomy yet",
        "free_explore": "Something new of your choice", "free": "Time for your interests", "trains": "Trains: ",
        "no_interests": "none given",
        "llm_fail": "AI ideas unavailable ({err}); used the local project templates.",
        "need_key": "Add an AI key to get bridges between your interests and your career.",
        "t_weeks": "At {h:g}h/week on career, the {n} priority items take ~{w} weeks.",
        "t_move": "Moving 1h/week from interests to career would bring that forward by ~{w} week(s), at the cost of less time for your interests. Change the weights? (Plan → Focus & weights)",
        "t_protected": "The {h:g}h of exploration are protected and never reallocated automatically.",
        "language": "English",
    },
}


# ----------------------------------------------------------------------------- planner
def split_hours(focus: dict[str, Any]) -> dict[str, float]:
    total = float(focus.get("weekly_hours", 10))
    w = focus.get("weights", {"carreira": 50, "exploracao": 30, "interesses": 20})
    return {k: round(total * float(v) / 100, 1) for k, v in w.items()}


def _template_projects(gap: pd.DataFrame, top: int = 3, lang: str = "pt") -> list[ProjectIdea]:
    prio = dict(zip(gap["skill_id"], gap["priority"]))
    names = dict(zip(gap["skill_id"], gap["name"]))
    scored = []
    for p in load_yaml(RESOURCES / "projects.yaml")["projects"]:
        score = sum(prio.get(s, 0) for s in p["skills"])
        if score > 0:
            trains = [names[s] for s in p["skills"] if prio.get(s, 0) > 0]
            sfx = "_en" if lang == "en" else ""
            scored.append((score, ProjectIdea(title=p.get("title" + sfx, p["title"]),
                                              description=p.get("description" + sfx, p["description"]),
                                              skills=[get_taxonomy().name_of(s) for s in p["skills"]],
                                              deliverable=p.get("deliverable" + sfx, p.get("deliverable", "")),
                                              why=TXT[lang]["trains"] + ", ".join(trains))))
    return [p for _, p in sorted(scored, key=lambda x: -x[0])[:top]]


def build_plan(gap: pd.DataFrame, focus: dict[str, Any], *, roles: list[str],
               skills_df: Optional[pd.DataFrame] = None, emerging_df: Optional[pd.DataFrame] = None,
               client=None, max_items: int = 6, lang: str = "pt") -> Plan:
    T = TXT.get(lang, TXT["pt"])
    hours = split_hours(focus)
    career_h = max(hours.get("carreira", 0.0), 0.1)
    notes: list[str] = []

    todo = gap[gap["priority"] > 0].sort_values("priority", ascending=False)
    ongoing = todo[todo["category"].isin(NON_STUDY_CATS)]
    for _, r in ongoing.iterrows():
        notes.append(T["ongoing"].format(name=r["name"], share=r["share_any"]))
    todo = todo[~todo["category"].isin(NON_STUDY_CATS)]
    career: list[CareerItem] = []
    for _, r in todo.head(max_items).iterrows():
        pairs = cooccurrence(skills_df, r["skill_id"]) if skills_df is not None else []
        career.append(CareerItem(
            skill_id=r["skill_id"], name=r["name"], status=r["status"], demand=float(r["demand"]),
            share_required=float(r["share_required"]), priority=float(r["priority"]),
            effort_hours=int(r["effort_hours"]), weeks=round(r["effort_hours"] / career_h, 1),
            why=T["why"].format(share=r["share_any"], req=r["share_required"]),
            pairs_with=pairs,
        ))
    quick = [c for c in career if c.status == "partial"][:3]

    # this week: focus on at most 2 career items, hours proportional to priority
    active = career[:2]
    tot = sum(c.priority for c in active) or 1
    this_week = [{"id": f"study:carreira:{c.skill_id}", "foco": "carreira", "item": c.name,
                  "horas": round(career_h * c.priority / tot, 1)} for c in active]

    # exploration (protected)
    exp_cfg = focus.get("exploration", {}) or {}
    exploration = [{"name": t, "why": T["chosen"]} for t in exp_cfg.get("topics", []) or []]
    if exp_cfg.get("include_emerging", True) and emerging_df is not None and not emerging_df.empty:
        # exploration = things NOT already on the career list (otherwise it is just more career time)
        in_career = {c.skill_id for c in career}
        for _, r in emerging_df.iterrows():
            if r["skill_id"] in in_career or get_taxonomy().category_of(r["skill_id"]) in NON_STUDY_CATS:
                continue
            kind = r.get("kind") if hasattr(r, "get") else None
            why = T[kind].format(v=r["value"]) if kind in ("rising", "new") else r["why"]
            exploration.append({"name": r["name"], "why": why})
    if hours.get("exploracao"):
        this_week.append({"id": "study:exploracao", "foco": "exploração",
                          "item": exploration[0]["name"] if exploration else T["free_explore"], "horas": hours["exploracao"]})

    interests = [{"name": i, "horas": round(hours.get("interesses", 0) / max(len(focus.get("interests") or []), 1), 1)}
                 for i in (focus.get("interests") or [])]
    if hours.get("interesses"):
        this_week.append({"id": "study:interesses", "foco": "interesses",
                          "item": ", ".join(i["name"] for i in interests) or T["free"], "horas": hours["interesses"]})

    # projects + bridges
    projects: list[ProjectIdea] = []
    bridges: list[Bridge] = []
    if client is not None:
        try:
            has = gap[gap["status"] == "has"]["name"].tolist()[:15]
            ideas = client.complete_model(IDEAS_SYSTEM, IDEAS_USER.format(
                roles=", ".join(roles), has=", ".join(has) or "-",
                gaps=", ".join(f"{c.name} ({c.why})" for c in career) or "-",
                interests=", ".join(focus.get("interests") or []) or T["no_interests"], language=T["language"],
                exploration=", ".join(e["name"] for e in exploration) or "-", career_hours=career_h,
            ), _LLMIdeas, cache_tag=f"ideas-v2-{lang}")
            projects = [ProjectIdea(**p.model_dump()) for p in ideas.projects[:3]]
            bridges = [Bridge(**b.model_dump()) for b in ideas.bridges]
        except Exception as e:  # fall back to templates, but say so
            notes.append(T["llm_fail"].format(err=type(e).__name__))
    if not projects:
        projects = _template_projects(gap, lang=lang)
    if (focus.get("interests") or []) and not bridges:
        notes.append(T["need_key"])

    # trade-offs: explicit questions, never automatic cuts
    tradeoffs: list[str] = []
    total_effort = sum(c.effort_hours for c in career)
    if total_effort and career_h:
        weeks_now = total_effort / career_h
        tradeoffs.append(T["t_weeks"].format(h=career_h, n=len(career), w=math.ceil(weeks_now)))
        if hours.get("interesses", 0) >= 1:
            w2 = total_effort / (career_h + 1)
            tradeoffs.append(T["t_move"].format(w=max(1, round(weeks_now - w2))))
        if exp_cfg.get("protected", True) and hours.get("exploracao"):
            tradeoffs.append(T["t_protected"].format(h=hours["exploracao"]))

    return Plan(weekly_hours=float(focus.get("weekly_hours", 10)), hours=hours,
                protected_exploration=bool(exp_cfg.get("protected", True)), career=career, quick_wins=quick,
                this_week=this_week, projects=projects, exploration=exploration[:8], interests=interests,
                bridges=bridges, tradeoffs=tradeoffs, notes=notes)
