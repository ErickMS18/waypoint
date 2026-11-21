import json

import httpx
import pytest

from rota.collect import collect
from rota.extract import build_prompt, canonicalize, extract_baseline, extract_llm, run_extraction
from rota.llm import LLMConfig, LLMError, LLMNotConfigured, config_from_env, make_client, parse_json_loose
from rota.models import Job, JobExtraction, SkillMention
from rota.roles import seniority_heuristic
from rota.taxonomy import get_taxonomy


def _job(title, text, **kw):
    return Job(job_key="t:x:1", source="t", external_id="1", company="C", title=title, text=text, **kw)


# ---------------------------------------------------------------- taxonomy
@pytest.mark.parametrize("name,expected", [
    ("Python", ["python"]), ("python3", ["python"]), ("Scikit Learn", ["scikit_learn"]),
    ("Large Language Models", ["llms"]), ("Retrieval-Augmented Generation", ["rag"]),
    ("Estatística", ["statistics"]), ("estatistica", ["statistics"]), ("Inglês avançado", ["english"]),
    ("OpenAI", ["llm_apis"]), ("PostgreSQL", ["postgresql"]), ("PySpark", ["spark"]),
])
def test_canonicalize_known(name, expected):
    assert get_taxonomy().canonicalize(name) == expected


def test_canonicalize_unknown_and_combined():
    tax = get_taxonomy()
    assert tax.canonicalize("Quantum basket weaving") == ["other:quantum-basket-weaving"]
    assert tax.canonicalize("Python/SQL") == ["python", "sql"]


def test_find_in_text_boundaries():
    tax = get_taxonomy()
    found = tax.find_in_text("We use PostgreSQL and NoSQL stores; C++ is a plus. Python or R.")
    assert {"postgresql", "nosql", "cpp", "python", "r"} <= found
    assert "sql" not in tax.find_in_text("PostgreSQL only")
    assert "r" not in tax.find_in_text("R$ 5.000 de salário")


def test_seniority_heuristic():
    assert seniority_heuristic("Senior Data Scientist", "") == "senior"
    assert seniority_heuristic("Cientista de Dados Pleno", "") == "mid"
    assert seniority_heuristic("Estágio em Ciência de Dados", "") == "intern"
    assert seniority_heuristic("Data Scientist", "3+ years of experience") == "mid"
    assert seniority_heuristic("Data Science Specialist", "") == "staff_plus"
    assert seniority_heuristic("Data Scientist", "no years mentioned") == "unknown"


# ---------------------------------------------------------------- baseline
def test_baseline_sections():
    text = ("Requirements\n- Python and SQL\n- Experience with Docker\n"
            "Nice to have\n- Kubernetes\n- Spark\nBenefits\n- Gym")
    ext = extract_baseline(_job("Machine Learning Engineer", text))
    got = {s.name: s.requirement for s in ext.skills}
    assert got["Python"] == got["SQL"] == got["Docker"] == "required"
    assert got["Kubernetes"] == got["Spark / PySpark"] == "nice_to_have"


def test_baseline_inline_plus_and_pt():
    ext = extract_baseline(_job("Cientista de Dados", "Requisitos\n- Python\n- Conhecimento em Azure será um diferencial"))
    got = {s.name: s.requirement for s in ext.skills}
    assert got == {"Python": "required", "Azure": "nice_to_have"}


def test_canonicalize_keeps_required_over_nice():
    ext = JobExtraction(skills=[SkillMention(name="python", requirement="nice_to_have"),
                                SkillMention(name="Python 3", requirement="required"),
                                SkillMention(name="sklearn", requirement="desejável")])
    got = {c.skill_id: c.requirement for c in canonicalize(ext)}
    assert got["python"] == "required" and got["scikit_learn"] == "nice_to_have"


def test_models_normalize_llm_variants():
    ext = JobExtraction.model_validate({"seniority": "Pleno", "work_model": "Remoto", "years_experience_min": "3",
                                        "skills": [{"name": "dbt", "requirement": "Nice to have"}]})
    assert (ext.seniority, ext.work_model, ext.years_experience_min) == ("mid", "remote", 3)
    assert ext.skills[0].requirement == "nice_to_have"


# ---------------------------------------------------------------- LLM client
def _gemini_transport(payloads):
    calls = {"n": 0}

    def handler(req: httpx.Request):
        assert req.headers["x-goog-api-key"] == "k"
        body = json.loads(req.content)
        assert "JOB TITLE" in body["contents"][0]["parts"][0]["text"] or "RESUME" in body["contents"][0]["parts"][0]["text"]
        text = payloads[min(calls["n"], len(payloads) - 1)]
        calls["n"] += 1
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}}]})
    return httpx.MockTransport(handler), calls


GOOD = json.dumps({"seniority": "mid", "years_experience_min": 3, "work_model": "hybrid", "summary": "x",
                   "skills": [{"name": "Python", "requirement": "required"},
                              {"name": "Kubernetes", "requirement": "nice_to_have"}]})


def test_llm_extract_with_retry_and_cache(db):
    transport, calls = _gemini_transport(["sorry, not json", "```json\n" + GOOD + "\n```"])
    client = make_client(db, transport=transport, cfg=LLMConfig("gemini", "m", "k"))
    job = _job("ML Engineer", "Requirements: Python. Nice: Kubernetes. " * 20)
    ext = extract_llm(job, client)
    assert ext.seniority == "mid" and len(ext.skills) == 2 and calls["n"] == 2
    ext2 = extract_llm(job, client)  # cached
    assert ext2 == ext and calls["n"] == 2 and client.cache_hits == 1


def test_llm_gives_up_on_garbage(db):
    transport, _ = _gemini_transport(["nope"])
    client = make_client(db, transport=transport, cfg=LLMConfig("gemini", "m", "k"))
    with pytest.raises(LLMError):
        extract_llm(_job("ML Engineer", "x" * 300), client)


def test_parse_json_loose():
    assert parse_json_loose('Here: {"a": 1} done') == {"a": 1}


def test_config_from_env_requires_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(LLMNotConfigured):
        config_from_env()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "abc")
    c = config_from_env()
    assert c.model == "claude-haiku-5-5" and c.min_interval == 0


def test_anthropic_and_openai_payloads():
    seen = {}

    def handler(req):
        seen[req.url.host] = json.loads(req.content)
        if req.url.host == "api.anthropic.com":
            return httpx.Response(200, json={"content": [{"type": "text", "text": GOOD}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": GOOD}}]})
    t = httpx.MockTransport(handler)
    job = _job("ML Engineer", "Python " * 50)
    for cfg in (LLMConfig("anthropic", "claude-x", "k"), LLMConfig("openai", "gpt-x", "k")):
        assert extract_llm(job, make_client(transport=t, cfg=cfg)).seniority == "mid"
    assert seen["api.anthropic.com"]["system"]
    assert seen["api.openai.com"]["response_format"] == {"type": "json_object"}


def test_prompt_contains_guidelines_and_vocabulary():
    p = build_prompt(_job("ML Engineer", "Python"))
    assert "nice_to_have" in p and "scikit-learn" in p and "JOB TITLE: ML Engineer" in p


# ---------------------------------------------------------------- batch
def test_run_extraction_baseline_is_incremental(cfg, db, transport):
    collect(cfg, db, transport=transport)
    r1 = run_extraction(db, db.jobs(), "baseline")
    r2 = run_extraction(db, db.jobs(), "baseline")
    assert r1["extracted"] == db.count_jobs() and r2["skipped"] == db.count_jobs()


def test_retries_without_temperature_when_rejected():
    bodies = []

    def handler(req):
        body = json.loads(req.content)
        bodies.append(body)
        if "temperature" in body:
            return httpx.Response(400, json={"error": {"message": "temperature is not supported for this model"}})
        return httpx.Response(200, json={"content": [{"type": "text", "text": GOOD}]})
    client = make_client(transport=httpx.MockTransport(handler), cfg=LLMConfig("anthropic", "m", "k"))
    assert extract_llm(_job("ML Engineer", "Python " * 50), client).seniority == "mid"
    assert "temperature" in bodies[0] and "temperature" not in bodies[1]
