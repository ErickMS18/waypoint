import json
from pathlib import Path

from waypoint.analysis.gap import gap_table, market_fit
from waypoint.analysis.plan import build_plan, split_hours
from waypoint.collect import collect
from waypoint.extract import run_extraction
from waypoint.pipeline import analyze, compute_gap, make_plan, make_report
from waypoint.profile import (build_profile, effective_levels, extract_profile_baseline, redact, save_overrides)

RESUME = """Maria Fictícia da Silva
Cientista de Dados | Python
Curitiba, PR | linkedin.com/in/maria-ficticia | (41) 99999-1234 | maria.f@example.com | CPF 123.456.789-09
EXPERIÊNCIA
- Modelos de churn em Python com scikit-learn e pandas; consultas SQL no SQL Server.
- Dashboards em Power BI. Pipelines no Airflow.
- Python em produção; SQL diário.
HABILIDADES
PyTorch - Básico
"""


def test_redact_removes_pii():
    out = redact(RESUME)
    for secret in ("Maria", "Fictícia", "99999-1234", "maria.f@example.com", "123.456.789-09", "linkedin.com"):
        assert secret not in out
    assert "scikit-learn" in out and "Curitiba" in out


def test_profile_baseline_levels():
    levels = {s.skill_id: s.level for s in extract_profile_baseline(RESUME)}
    assert levels["python"] >= 2 and levels["sql"] >= 2
    assert levels["pytorch"] == 1  # declared basic


def test_build_profile_and_overrides(cfg, tmp_path):
    cv = tmp_path / "cv.md"
    cv.write_text(RESUME, encoding="utf-8")
    prof = build_profile(cv, cfg.paths.profile)
    assert prof.method == "baseline" and (cfg.paths.profile / "profile.json").exists()
    assert "maria.f@example.com" not in (cfg.paths.profile / "resume_redacted.txt").read_text(encoding="utf-8")
    save_overrides(cfg.paths.profile, {"docker": 2, "python": 3})
    lv = effective_levels(cfg.paths.profile)
    assert lv["docker"] == 2 and lv["python"] == 3


def test_split_hours_sum():
    h = split_hours({"weekly_hours": 10, "weights": {"carreira": 50, "exploracao": 30, "interesses": 20}})
    assert h == {"carreira": 5.0, "exploracao": 3.0, "interesses": 2.0}


def test_full_pipeline_baseline(cfg, db, transport, tmp_path):
    collect(cfg, db, transport=transport)
    run_extraction(db, db.jobs(), "baseline")
    a = analyze(cfg, db, "baseline")
    assert len(a.jobs_df) == db.count_jobs() >= 6
    assert set(a.tables) == {"ai_ml_engineer", "data_scientist"}
    top = a.overall.iloc[0]
    assert top["skill_id"] == "python" and 0 < top["share_any"] <= 1
    assert set(a.regions["region"]) >= {"BR", "INTL", "REMOTE_BR_OK"}

    cv = tmp_path / "cv.md"
    cv.write_text(RESUME, encoding="utf-8")
    build_profile(cv, cfg.paths.profile)
    gap = compute_gap(cfg, a)
    assert {"has", "missing"} <= set(gap["status"])
    assert (gap.loc[gap["status"] == "has", "priority"] == 0).all()
    assert 0 < market_fit(gap) < 1

    cfg.focus["interests"] = ["violão"]
    cfg.focus["exploration"]["topics"] = ["Rust"]
    plan = make_plan(cfg, a, gap, client=None)
    assert plan.career and plan.projects and plan.tradeoffs
    assert any(t["foco"] == "exploração" for t in plan.this_week)
    assert plan.exploration[0]["name"] == "Rust"
    text = json.dumps(plan.to_dict(), ensure_ascii=False).lower()
    assert "irrelevante" not in text and "irrelevant" not in text
    assert any("protegidas" in t for t in plan.tradeoffs)

    files = make_report(cfg, a, gap=gap, plan=plan, model="taxonomy-v1")
    md = files["report"].read_text(encoding="utf-8")
    assert "Seu gap (privado)" in md and "Esta semana" in md and files["chart_ai_ml_engineer"].exists()
    pub = make_report(cfg, a, gap=gap, plan=plan, model="taxonomy-v1", public=True)
    pmd = pub["report"].read_text(encoding="utf-8")
    assert "Seu gap" not in pmd and "Plano" not in pmd and "Brasil" in pmd
    nums = json.loads(pub["numbers"].read_text(encoding="utf-8"))
    assert nums["n_jobs"] == len(a.jobs_df) and "data_scientist" in nums["roles"]


def test_gap_priority_ordering():
    import pandas as pd
    tbl = pd.DataFrame([
        {"skill_id": "python", "name": "Python", "category": "language", "n_required": 9, "n_nice": 0, "n_any": 9,
         "share_any": .9, "share_required": .9, "share_nice": 0, "demand": .9},
        {"skill_id": "docker", "name": "Docker", "category": "mlops", "n_required": 5, "n_nice": 2, "n_any": 7,
         "share_any": .7, "share_required": .5, "share_nice": .2, "demand": .6},
        {"skill_id": "rag", "name": "RAG", "category": "genai", "n_required": 2, "n_nice": 2, "n_any": 4,
         "share_any": .4, "share_required": .2, "share_nice": .2, "demand": .3},
    ])
    g = gap_table(tbl, {"python": 3, "rag": 1})
    pr = dict(zip(g["skill_id"], g["priority"]))
    assert pr["python"] == 0 and pr["docker"] > pr["rag"] > 0
    plan = build_plan(g, {"weekly_hours": 10, "weights": {"carreira": 50, "exploracao": 30, "interesses": 20}},
                      roles=["X"])
    assert [c.skill_id for c in plan.career] == ["docker", "rag"]
    assert plan.quick_wins[0].skill_id == "rag"
