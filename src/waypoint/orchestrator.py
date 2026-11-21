"""Waypoint v2 — personal orchestrator.

Combines the v1 study plan (career / exploration / interests) with your current projects and deadlines
(college, internship, research, personal) into a concrete schedule for the week and for today, and
re-plans automatically when something slips.

Design rules (same as v1):
* Deadlines are scheduled earliest-first and spread over the available days (no last-minute piles).
* Study time from the v1 plan is reserved every week. Exploration is protected: it is never used to
  rescue a deadline. Career/interest hours can be *lent* to a project, but only when you accept the
  trade-off explicitly (``borrow``), never automatically.
* Nothing is dropped silently: whatever does not fit becomes a visible risk with the missing hours.

Everything here is pure Python over a JSON file in data/ (git-ignored), so it is easy to test.
"""
from __future__ import annotations

import json
import math
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

AREAS = ["faculdade", "estagio", "pesquisa", "pessoal", "carreira"]
AREA_ICON = {"faculdade": "🎓", "estagio": "💼", "pesquisa": "🔬", "pessoal": "🌱", "carreira": "🧭",
             "estudo": "📚", "exploracao": "🧪", "interesses": "🎸"}
STEP = 0.5  # scheduling granularity (hours)
MIN_BLOCK = 1.0  # preferred minimum focused block
STUDY_BLOCK = 1.5
DEFAULT_AVAILABILITY = {"0": 2.0, "1": 2.0, "2": 2.0, "3": 2.0, "4": 1.5, "5": 4.0, "6": 2.0}
STUDY_FOCUS_KEY = {"carreira": "carreira", "exploração": "exploracao", "exploracao": "exploracao",
                   "interesses": "interesses"}


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def _d(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def round_step(x: float) -> float:
    return math.floor(x / STEP + 1e-9) * STEP


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_id(d: date) -> str:
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


# ============================================================================= state
@dataclass
class Task:
    id: str
    title: str
    hours: float                      # estimated total effort
    due: Optional[str] = None         # ISO date; falls back to the project deadline
    done: bool = False


@dataclass
class Project:
    id: str
    name: str
    area: str = "pessoal"
    deadline: Optional[str] = None
    priority: int = 2                 # 1 = high, 2 = normal, 3 = low
    hours: float = 0.0                # effort when the project has no tasks
    notes: str = ""
    archived: bool = False
    tasks: list[Task] = field(default_factory=list)


@dataclass
class State:
    availability: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_AVAILABILITY))
    day_overrides: dict[str, float] = field(default_factory=dict)   # "2026-11-21": 1.0
    max_block: float = 2.0
    projects: list[Project] = field(default_factory=list)
    log: list[dict[str, Any]] = field(default_factory=list)          # {"date","item","hours"}
    borrow: dict[str, dict[str, float]] = field(default_factory=dict)  # week -> {"carreira": h, "interesses": h}
    snapshot: dict[str, Any] = field(default_factory=dict)            # last "today" plan, for slip detection

    # -------------------------------------------------------------- persistence
    @classmethod
    def load(cls, path: Path) -> "State":
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        projects = [Project(**{**p, "tasks": [Task(**t) for t in p.get("tasks", [])]}) for p in raw.get("projects", [])]
        return cls(availability={**DEFAULT_AVAILABILITY, **raw.get("availability", {})},
                   day_overrides=raw.get("day_overrides", {}), max_block=float(raw.get("max_block", 2.0)),
                   projects=projects, log=raw.get("log", []), borrow=raw.get("borrow", {}),
                   snapshot=raw.get("snapshot", {}))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)

    # -------------------------------------------------------------- queries
    def project(self, pid: str) -> Optional[Project]:
        return next((p for p in self.projects if p.id == pid), None)

    def logged(self, item: str, since: Optional[date] = None, until: Optional[date] = None) -> float:
        tot = 0.0
        for e in self.log:
            if e["item"] != item:
                continue
            d = _d(e["date"])
            if (since and d < since) or (until and d > until):
                continue
            tot += float(e["hours"])
        return tot

    def logged_on(self, day: date) -> float:
        return sum(float(e["hours"]) for e in self.log if e["date"] == day.isoformat())

    def capacity(self, day: date) -> float:
        if day.isoformat() in self.day_overrides:
            return float(self.day_overrides[day.isoformat()])
        return float(self.availability.get(str(day.weekday()), 0.0))

    # -------------------------------------------------------------- mutations
    def add_log(self, item: str, hours: float, day: date) -> None:
        if hours > 0:
            self.log.append({"date": day.isoformat(), "item": item, "hours": round(float(hours), 2)})

    def undo_last_log(self, item: str, day: date) -> bool:
        for i in range(len(self.log) - 1, -1, -1):
            if self.log[i]["item"] == item and self.log[i]["date"] == day.isoformat():
                del self.log[i]
                return True
        return False


# ============================================================================= work items
@dataclass
class WorkItem:
    id: str                 # "task:<id>", "proj:<id>" or "study:<foco>[:<skill>]"
    title: str
    kind: str               # task | study
    area: str
    remaining: float
    due: Optional[date] = None
    priority: int = 2
    project: str = ""
    project_id: str = ""
    foco: str = ""          # for study items: carreira | exploracao | interesses


def project_items(state: State) -> list[WorkItem]:
    out = []
    for p in state.projects:
        if p.archived:
            continue
        open_tasks = [t for t in p.tasks if not t.done]
        if p.tasks:
            for t in open_tasks:
                rem = max(t.hours - state.logged(f"task:{t.id}"), 0.0)
                if rem <= 0:
                    continue
                out.append(WorkItem(id=f"task:{t.id}", title=t.title, kind="task", area=p.area, remaining=rem,
                                    due=_d(t.due) or _d(p.deadline), priority=p.priority, project=p.name,
                                    project_id=p.id))
        elif p.hours > 0:
            rem = max(p.hours - state.logged(f"proj:{p.id}"), 0.0)
            if rem > 0:
                out.append(WorkItem(id=f"proj:{p.id}", title=p.name, kind="task", area=p.area, remaining=rem,
                                    due=_d(p.deadline), priority=p.priority, project=p.name, project_id=p.id))
    return out


def study_items(plan: Optional[dict[str, Any]], state: State, today: date) -> list[WorkItem]:
    """This week's study blocks from the v1 plan, minus what was already logged this week and what you lent."""
    if not plan:
        return []
    ws = week_start(today)
    lent = dict(state.borrow.get(week_id(today), {}))
    out = []
    for it in plan.get("this_week", []):
        foco = STUDY_FOCUS_KEY.get(it.get("foco", ""), it.get("foco", ""))
        iid = it.get("id") or f"study:{foco}:{it.get('item')}"
        planned = float(it.get("horas") or 0)
        if foco in lent and lent[foco] > 0:
            take = min(planned, lent[foco])
            planned -= take
            lent[foco] -= take
        rem = round_step(max(planned - state.logged(iid, since=ws), 0.0))
        if rem <= 0:
            continue
        out.append(WorkItem(id=iid, title=it.get("item", ""), kind="study", area=foco, remaining=rem, foco=foco,
                            priority=2))
    return out


# ============================================================================= schedule
@dataclass
class Block:
    item: str
    title: str
    kind: str
    area: str
    hours: float
    project: str = ""
    project_id: str = ""
    due: Optional[str] = None
    foco: str = ""


@dataclass
class Day:
    date: str
    capacity: float
    blocks: list[Block] = field(default_factory=list)

    @property
    def planned(self) -> float:
        return round(sum(b.hours for b in self.blocks), 2)

    @property
    def free(self) -> float:
        return round(max(self.capacity - self.planned, 0.0), 2)


@dataclass
class Risk:
    item: str
    title: str
    project: str
    due: str
    missing: float
    borrowable: dict[str, float]      # hours of career / interests study you could lend this week


@dataclass
class Schedule:
    today: str
    days: list[Day]
    risks: list[Risk]
    overdue: list[WorkItem]
    unscheduled_study: float
    slipped: list[dict[str, Any]]
    week_load: dict[str, float]

    def day(self, d: date) -> Optional[Day]:
        return next((x for x in self.days if x.date == d.isoformat()), None)


def _place(day: Day, cap_left: dict[str, float], it: WorkItem, hours: float) -> float:
    h = round_step(min(hours, cap_left[day.date]))
    if h <= 0:
        return 0.0
    for b in day.blocks:
        if b.item == it.id:
            b.hours = round(b.hours + h, 2)
            break
    else:
        day.blocks.append(Block(item=it.id, title=it.title, kind=it.kind, area=it.area, hours=h, project=it.project,
                                project_id=it.project_id, due=it.due.isoformat() if it.due else None, foco=it.foco))
    cap_left[day.date] = round(cap_left[day.date] - h, 2)
    it.remaining = round(it.remaining - h, 2)
    return h


def build_schedule(state: State, plan: Optional[dict[str, Any]], today: Optional[date] = None,
                   horizon: int = 14) -> Schedule:
    today = today or date.today()
    days = [Day(date=(today + timedelta(i)).isoformat(), capacity=state.capacity(today + timedelta(i)))
            for i in range(horizon)]
    # today: what you already did counts against today's free time (replanning in real time)
    days[0].capacity = max(round(days[0].capacity - state.logged_on(today), 2), 0.0)
    cap_left = {d.date: d.capacity for d in days}
    week_end = week_start(today) + timedelta(6)
    week_days = [d for d in days if _d(d.date) <= week_end]

    study = study_items(plan, state, today)
    tasks = project_items(state)
    overdue = [t for t in tasks if t.due and t.due < today]

    # 1) reserve study time for the rest of the week, proportional to each day's free time
    study_need = sum(s.remaining for s in study)
    week_cap = sum(cap_left[d.date] for d in week_days) or 1.0
    reserve = {d.date: round_step(min(cap_left[d.date], study_need * cap_left[d.date] / week_cap)) for d in week_days}
    for d in week_days:
        cap_left[d.date] = round(cap_left[d.date] - reserve[d.date], 2)

    # 2) deadline work, earliest due first. Tasks of the same project are done IN ORDER (a project is a
    #    sequence), and the project's hours are spread over the days before the due date (no last-minute piles).
    risks: list[Risk] = []
    groups: dict[tuple, list[WorkItem]] = {}
    for t in [t for t in tasks if t.due]:
        groups.setdefault((t.due, t.project_id), []).append(t)
    for (due, _pid), seq in sorted(groups.items(), key=lambda kv: (kv[0][0], min(t.priority for t in kv[1]))):
        last = max(due - timedelta(1), today)
        window = [d for d in days if _d(d.date) <= last] or [days[0]]
        total = sum(t.remaining for t in seq)
        quota = min(max(math.ceil(total / len(window) / STEP) * STEP, MIN_BLOCK), state.max_block)

        def fill(d: Day, budget: float) -> None:
            for t in seq:
                if budget <= 0:
                    break
                if t.remaining <= 0:
                    continue
                budget -= _place(d, cap_left, t, min(t.remaining, budget))

        for d in window:                       # spread …
            fill(d, quota)
        for d in window:                       # … then whatever is left, earliest first
            used = sum(b.hours for b in d.blocks if b.item in {t.id for t in seq})
            fill(d, max(state.max_block * 1.5 - used, 0))
        for t in seq:
            if t.remaining > 0 and t.due <= today + timedelta(horizon):
                borrowable = {f: round(sum(s.remaining for s in study if s.foco == f), 1) for f in ("carreira", "interesses")}
                risks.append(Risk(item=t.id, title=t.title, project=t.project, due=t.due.isoformat(),
                                  missing=round(t.remaining, 1), borrowable={k: v for k, v in borrowable.items() if v > 0}))

    # 3) give the reserved time back and place study in focused blocks (≥1h when possible), on the days with
    #    the most free time, one block per item per day. Exploration goes first: it is protected.
    for d in week_days:
        cap_left[d.date] = round(cap_left[d.date] + reserve[d.date], 2)
    order = {"exploracao": 0, "carreira": 1, "interesses": 2}
    for s in sorted(study, key=lambda s: order.get(s.foco, 3)):
        used_days: set[str] = set()
        while s.remaining > 0:
            cands = [d for d in week_days if cap_left[d.date] >= min(MIN_BLOCK, s.remaining) and d.date not in used_days]
            if not cands:
                cands = [d for d in week_days if cap_left[d.date] >= STEP]
                if not cands:
                    break
            d = max(cands, key=lambda x: (cap_left[x.date], -week_days.index(x)))
            placed = _place(d, cap_left, s, min(STUDY_BLOCK, s.remaining))
            used_days.add(d.date)
            if placed <= 0:
                break
    unscheduled_study = round(sum(s.remaining for s in study), 1)

    # 4) tasks without a deadline fill the remaining time, by priority
    for t in sorted([t for t in tasks if not t.due], key=lambda t: t.priority):
        for d in days:
            if t.remaining <= 0:
                break
            if cap_left[d.date] < min(MIN_BLOCK, t.remaining):
                continue
            _place(d, cap_left, t, min(t.remaining, state.max_block))

    # order blocks inside a day: overdue/urgent first, then deadlines, study, others
    def _key(b: Block) -> tuple:
        due = _d(b.due)
        return (0 if due and due <= today + timedelta(2) else 1, due or date.max, 0 if b.kind == "study" else 1)
    for d in days:
        d.blocks.sort(key=_key)

    load: dict[str, float] = {}
    for d in week_days:
        for b in d.blocks:
            load[b.area] = round(load.get(b.area, 0) + b.hours, 2)
    return Schedule(today=today.isoformat(), days=days, risks=risks, overdue=overdue,
                    unscheduled_study=unscheduled_study, slipped=detect_slips(state, today), week_load=load)


# ============================================================================= replanning
def detect_slips(state: State, today: date) -> list[dict[str, Any]]:
    """Blocks planned for an earlier day (last snapshot) that did not get the planned hours logged."""
    snap = state.snapshot or {}
    d = _d(snap.get("date"))
    if not d or d >= today:
        return []
    out = []
    for b in snap.get("blocks", []):
        done = sum(float(e["hours"]) for e in state.log if e["item"] == b["item"] and e["date"] == d.isoformat())
        if done + 1e-9 < float(b["hours"]):
            out.append({"item": b["item"], "title": b["title"], "missing": round(float(b["hours"]) - done, 1),
                        "date": d.isoformat()})
    return out


def take_snapshot(state: State, sched: Schedule) -> bool:
    """Remember today's plan once per day, so tomorrow we can say what slipped. Returns True if it changed."""
    if state.snapshot.get("date") == sched.today:
        return False
    first = sched.days[0]
    state.snapshot = {"date": sched.today,
                      "blocks": [{"item": b.item, "title": b.title, "hours": b.hours} for b in first.blocks]}
    return True


def today_progress(state: State, sched: Schedule) -> tuple[float, float]:
    """(hours done today, hours planned today incl. done)."""
    done = state.logged_on(_d(sched.today))
    return round(done, 2), round(done + sched.days[0].planned, 2)


def next_block(sched: Schedule) -> Optional[Block]:
    return sched.days[0].blocks[0] if sched.days and sched.days[0].blocks else None


def accept_borrow(state: State, today: date, foco: str, hours: float) -> None:
    wk = week_id(today)
    state.borrow.setdefault(wk, {})
    state.borrow[wk][foco] = round(state.borrow[wk].get(foco, 0.0) + hours, 1)


# ============================================================================= AI helper: break a project into tasks
class _LLMTask(BaseModel):
    title: str
    hours: float = Field(ge=0.5, le=40)


class _LLMTasks(BaseModel):
    tasks: list[_LLMTask] = Field(default_factory=list)


BREAKDOWN_SYSTEM = ("You are a pragmatic study and project coach for a university student who also works. "
                    "Break projects into concrete, verifiable tasks with honest hour estimates. JSON only.")
BREAKDOWN_USER = """Project: {name}
Area: {area}
Deadline: {deadline}
Notes from the person: {notes}
Total effort the person expects (hours, 0 = unknown): {hours}

Return 3 to 8 tasks in {language}, in the order they should be done. Each task must be a concrete deliverable
step (e.g. "Write the methods section draft", not "Work on project"), with an hour estimate (0.5 to 40).
If the expected total is given, keep the sum close to it.
JSON: {{"tasks": [{{"title": "", "hours": 0}}]}}"""

TEMPLATE_TASKS = {
    "pt": [("Entender o que precisa ser entregue e planejar", 0.15), ("Fazer a primeira versão", 0.5),
           ("Revisar e ajustar", 0.25), ("Finalizar e entregar", 0.1)],
    "en": [("Understand what must be delivered and plan", 0.15), ("Build the first version", 0.5),
           ("Review and adjust", 0.25), ("Finish and deliver", 0.1)],
}


def breakdown_tasks(name: str, area: str, deadline: Optional[str], notes: str, hours: float,
                    client=None, lang: str = "pt") -> list[Task]:
    """Suggest tasks for a project (LLM when available, otherwise a simple template)."""
    if client is not None:
        try:
            res = client.complete_model(BREAKDOWN_SYSTEM, BREAKDOWN_USER.format(
                name=name, area=area, deadline=deadline or "-", notes=notes or "-", hours=hours or 0,
                language="Portuguese (Brazil)" if lang == "pt" else "English"), _LLMTasks, cache_tag="breakdown-v1")
            tasks = [Task(id=new_id(), title=t.title.strip(), hours=max(STEP, round_step(t.hours) or STEP))
                     for t in res.tasks[:8] if t.title.strip()]
            if tasks:
                return tasks
        except Exception:
            pass
    total = hours or 8.0
    return [Task(id=new_id(), title=t, hours=max(STEP, round_step(total * f) or STEP)) for t, f in TEMPLATE_TASKS[lang]]


def state_path(data_dir: Path) -> Path:
    return data_dir / "orchestrator.json"


def now_local() -> datetime:
    return datetime.now()


# ============================================================================= AI helper: quick capture in plain words
class _LLMCapture(BaseModel):
    name: str
    area: str = "pessoal"
    deadline: Optional[str] = None      # YYYY-MM-DD
    hours: float = Field(default=0, ge=0, le=400)
    priority: int = Field(default=2, ge=1, le=3)
    tasks: list[_LLMTask] = Field(default_factory=list)


CAPTURE_SYSTEM = ("You turn a short note from a university student who also works into one structured project for "
                  "a personal planner. Resolve relative dates against the given 'today'. JSON only.")
CAPTURE_USER = """Today is {today} ({weekday}).
Note: \"\"\"{text}\"\"\"

Return one project:
- name: short, specific, in {language} (e.g. "Prova de IA", "Relatório do PIBIC").
- area: one of faculdade (college: exams, assignments, classes), estagio (internship/work), pesquisa (research,
  papers), carreira (career, portfolio, job applications), pessoal (anything else).
- deadline: YYYY-MM-DD if the note implies one (e.g. "quinta" = the next Thursday after today), else null.
- hours: total effort if stated or reasonably implied, else your honest estimate.
- priority: 1 high (exam/deadline within 7 days or the note says urgent), 2 normal, 3 low.
- tasks: 2 to 6 concrete steps in order, in {language}, each with an hour estimate (0.5 to 40) summing close to hours.
JSON: {{"name": "", "area": "", "deadline": null, "hours": 0, "priority": 2, "tasks": [{{"title": "", "hours": 0}}]}}"""

_WEEKDAYS_PT = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
_WEEKDAYS_EN = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_AREA_HINTS = {
    "faculdade": ["prova", "trabalho", "tde", "aula", "disciplina", "faculdade", "exam", "assignment", "class", "somativa", "apresentação"],
    "estagio": ["estágio", "estagio", "dashboard", "chamado", "bi ", "power bi", "reunião", "internship", "work"],
    "pesquisa": ["artigo", "pesquisa", "pibic", "paper", "research", "experimento"],
    "carreira": ["portfólio", "portfolio", "linkedin", "currículo", "entrevista", "candidatura", "interview"],
}


def capture_fallback(text: str, today: date, lang: str = "pt") -> dict[str, Any]:
    """Rule-based parse used without an AI key: dates (dd/mm, weekday names), hours ("6h") and area keywords."""
    import re
    low = " " + text.lower() + " "
    deadline = None
    m = re.search(r"\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", low)
    if m:
        y = int(m.group(3)) if m.group(3) else today.year
        y = y + 2000 if y < 100 else y
        try:
            d = date(y, int(m.group(2)), int(m.group(1)))
            if d < today and not m.group(3):
                d = date(y + 1, d.month, d.day)
            deadline = d
        except ValueError:
            deadline = None
    if deadline is None:
        for names in (_WEEKDAYS_PT, _WEEKDAYS_EN):
            for i, n in enumerate(names):
                if re.search(rf"\b{n}(-feira)?\b", low):
                    ahead = (i - today.weekday()) % 7 or 7
                    deadline = today + timedelta(days=ahead)
                    break
            if deadline:
                break
    if deadline is None and re.search(r"\bamanh[ãa]\b|\btomorrow\b", low):
        deadline = today + timedelta(days=1)
    hours = _stated_hours(text) or 6.0
    area = next((a for a, keys in _AREA_HINTS.items() if any(k in low for k in keys)), "pessoal")
    name = re.sub(r"\s+", " ", re.split(r"[,;\n]", text.strip())[0])[:60].strip(" .,;")
    name = name[:1].upper() + name[1:]
    prio = 1 if deadline and (deadline - today).days <= 7 else 2
    tasks = [Task(id=new_id(), title=t, hours=max(STEP, round_step(hours * f) or STEP)) for t, f in TEMPLATE_TASKS[lang]]
    return {"name": name or "Novo projeto", "area": area, "deadline": deadline.isoformat() if deadline else None,
            "hours": hours, "priority": prio, "tasks": [asdict(t) for t in tasks], "method": "rules"}


def _stated_hours(text: str) -> float | None:
    """Hours the user wrote explicitly ("uns 6h", "5 horas", "3.5 hours"), if any."""
    import re
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(h|hrs?|horas?|hours?)\b", text.lower())
    return float(m.group(1).replace(",", ".")) if m else None


def _fit_hours(tasks: list[Task], total: float) -> list[Task]:
    """Scale task estimates so they add up to the total the user stated (their number wins over the model's)."""
    cur = sum(t.hours for t in tasks)
    if not tasks or cur <= 0 or abs(cur - total) < STEP:
        return tasks
    for t in tasks:
        t.hours = max(STEP, round_step(t.hours * total / cur) or STEP)
    diff = round_step(total - sum(t.hours for t in tasks))
    if diff:  # absorb rounding in the largest task
        big = max(tasks, key=lambda t: t.hours)
        big.hours = max(STEP, big.hours + diff)
    return tasks


def capture(text: str, today: date, client=None, lang: str = "pt") -> dict[str, Any]:
    """Turn a plain-language note ("prova de IA quinta, uns 6h de estudo") into a project draft (not saved)."""
    if client is not None:
        try:
            res = client.complete_model(CAPTURE_SYSTEM, CAPTURE_USER.format(
                today=today.isoformat(), weekday=_WEEKDAYS_EN[today.weekday()], text=text.strip()[:1500],
                language="Portuguese (Brazil)" if lang == "pt" else "English"), _LLMCapture, cache_tag="capture-v1")
            area = res.area if res.area in AREAS else "pessoal"
            dl = _d(res.deadline)
            tasks = [Task(id=new_id(), title=t.title.strip(), hours=max(STEP, round_step(t.hours) or STEP))
                     for t in res.tasks[:8] if t.title.strip()]
            stated = _stated_hours(text)
            if stated:
                tasks = _fit_hours(tasks, stated)
            total = sum(t.hours for t in tasks) if tasks else float(stated or res.hours)
            return {"name": res.name.strip()[:80] or text[:60], "area": area,
                    "deadline": dl.isoformat() if dl and dl >= today else None, "hours": total,
                    "priority": int(res.priority), "tasks": [asdict(t) for t in tasks], "method": "llm"}
        except Exception:
            pass
    return capture_fallback(text, today, lang)
