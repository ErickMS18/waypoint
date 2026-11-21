from datetime import date, timedelta

from waypoint import orchestrator as o

MON = date(2026, 11, 23)  # a Monday
PLAN = {"this_week": [
    {"id": "study:carreira:llms", "foco": "carreira", "item": "LLMs", "horas": 3.0},
    {"id": "study:exploracao", "foco": "exploração", "item": "Vector databases", "horas": 2.0},
    {"id": "study:interesses", "foco": "interesses", "item": "violão", "horas": 1.0},
]}


def state(**kw):
    s = o.State(availability={str(i): 3.0 for i in range(7)})
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def proj(name, hours, deadline=None, area="faculdade", tasks=None, priority=2):
    return o.Project(id=o.new_id(), name=name, area=area, deadline=deadline, hours=hours, priority=priority,
                     tasks=tasks or [])


def total(sched, item, until=None):
    return sum(b.hours for d in sched.days for b in d.blocks if b.item == item and (until is None or d.date <= until))


def test_study_is_reserved_and_deadline_spread_before_due():
    p = proj("TDE", 6.0, deadline=(MON + timedelta(3)).isoformat())
    s = state(projects=[p])
    sch = o.build_schedule(s, PLAN, today=MON)
    assert total(sch, f"proj:{p.id}", until=(MON + timedelta(2)).isoformat()) == 6.0  # done before the due day
    per_day = [sum(b.hours for b in d.blocks if b.item == f"proj:{p.id}") for d in sch.days[:3]]
    assert max(per_day) <= 2.0 and min(per_day) > 0  # spread, not piled on day 1
    assert total(sch, "study:exploracao") == 2.0 and total(sch, "study:carreira:llms") == 3.0
    assert not sch.risks
    for d in sch.days:
        assert d.planned <= d.capacity + 1e-9


def test_overload_becomes_visible_risk_and_never_eats_exploration():
    p = proj("Artigo", 30.0, deadline=(MON + timedelta(2)).isoformat(), area="pesquisa")
    sch = o.build_schedule(state(projects=[p]), PLAN, today=MON)
    assert sch.risks and sch.risks[0].missing > 0
    assert total(sch, "study:exploracao") == 2.0                      # protected
    assert set(sch.risks[0].borrowable) == {"carreira", "interesses"}  # exploration is never offered


def test_accepting_a_borrow_moves_career_hours_to_the_deadline():
    p = proj("Artigo", 30.0, deadline=(MON + timedelta(2)).isoformat(), area="pesquisa")
    s = state(projects=[p])
    before = o.build_schedule(s, PLAN, today=MON).risks[0].missing
    o.accept_borrow(s, MON, "carreira", 3.0)
    after = o.build_schedule(s, PLAN, today=MON)
    assert total(after, "study:carreira:llms") == 0
    assert (after.risks[0].missing if after.risks else 0) < before


def test_logging_progress_replans_today_and_slips_are_detected():
    t = o.Task(id="t1", title="Escrever introdução", hours=4.0)
    p = proj("Relatório", 0, deadline=(MON + timedelta(5)).isoformat(), tasks=[t])
    s = state(projects=[p])
    sch = o.build_schedule(s, None, today=MON)
    o.take_snapshot(s, sch)
    planned_today = sum(b.hours for b in sch.days[0].blocks)
    assert planned_today > 0
    s.add_log("task:t1", 0.5, MON)                                  # did less than planned
    tue = o.build_schedule(s, None, today=MON + timedelta(1))
    assert tue.slipped and tue.slipped[0]["missing"] == planned_today - 0.5
    assert total(tue, "task:t1") == 3.5                              # remaining hours were redistributed
    done, planned = o.today_progress(s, o.build_schedule(s, None, today=MON))
    assert done == 0.5


def test_study_logged_this_week_is_not_rescheduled_and_resets_next_week():
    s = state()
    s.add_log("study:carreira:llms", 3.0, MON)
    sch = o.build_schedule(s, PLAN, today=MON + timedelta(1))
    assert total(sch, "study:carreira:llms") == 0
    nxt = o.build_schedule(s, PLAN, today=MON + timedelta(7))
    assert total(nxt, "study:carreira:llms") == 3.0


def test_day_override_and_state_roundtrip(tmp_path):
    s = state(projects=[proj("Pessoal", 2.0, area="pessoal")])
    s.day_overrides[MON.isoformat()] = 0.0
    sch = o.build_schedule(s, PLAN, today=MON)
    assert sch.days[0].blocks == []
    path = o.state_path(tmp_path)
    s.save(path)
    s2 = o.State.load(path)
    assert s2.projects[0].name == "Pessoal" and s2.day_overrides == s.day_overrides


def test_breakdown_without_llm_uses_template():
    tasks = o.breakdown_tasks("TCC", "faculdade", None, "", 20, client=None, lang="en")
    assert len(tasks) == 4 and abs(sum(t.hours for t in tasks) - 20) <= 2
