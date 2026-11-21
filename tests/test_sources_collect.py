from waypoint.collect import add_manual, collect
from waypoint.sources import Greenhouse, Lever
from waypoint.http import Http


def test_collect_all_sources(cfg, db, transport):
    st = collect(cfg, db, transport=transport)
    assert not st.errors
    jobs = {j.job_key: j for j in db.jobs()}
    # the sales role is filtered out by the title regex
    assert "greenhouse:acme:101" in jobs and "greenhouse:acme:102" not in jobs
    assert set(st.by_source) == {"greenhouse", "lever", "ashby", "himalayas", "gupy", "manual"}
    gh = jobs["greenhouse:acme:101"]
    assert gh.role == "ai_ml_engineer" and gh.region == "BR" and "pgvector" in gh.text
    assert "<li>" not in gh.text and "&lt;" not in gh.text
    lv = jobs["lever:betaco:aaaa-1"]
    assert lv.role == "data_scientist" and lv.region == "INTL" and "Bonus points" in lv.text
    hm = next(j for j in jobs.values() if j.source == "himalayas")
    assert hm.region == "REMOTE_BR_OK" and hm.remote
    gp = next(j for j in jobs.values() if j.source == "gupy")
    assert gp.region == "BR" and gp.lang == "pt" and gp.role == "data_scientist"
    man = next(j for j in jobs.values() if j.source == "manual")
    assert man.company == "Loja X" and man.role == "ai_ml_engineer"


def test_collect_is_idempotent(cfg, db, transport):
    collect(cfg, db, transport=transport)
    n = db.count_jobs()
    st = collect(cfg, db, transport=transport)
    assert st.new == 0 and st.seen == n and db.count_jobs() == n


def test_board_check_and_refetch(transport):
    http = Http(delay=0, transport=transport)
    gh = Greenhouse(http, {"boards": ["acme", "doesnotexist"]})
    assert dict(gh.check()) == {"acme": 2, "doesnotexist": None}
    p = gh.fetch_one("acme", "101")
    assert p and p.title == "Machine Learning Engineer"
    lv = Lever(http, {"sites": ["euco"]})  # only exists on the EU host
    assert dict(lv.check()) == {"euco": 0}


def test_add_manual_dedupes(cfg, db):
    raw = "Vaga de Cientista de Dados. Requisitos: Python, SQL, estatística. " * 10
    s1, job = add_manual(cfg, db, raw, title="Cientista de Dados Pleno", company="Y")
    s2, _ = add_manual(cfg, db, raw, title="Cientista de Dados Pleno", company="Y")
    assert (s1, s2) == ("new", "seen") and job.role == "data_scientist"


def test_near_duplicates_and_pruning(cfg, db):
    from waypoint.collect import prune_unmatched
    from waypoint.models import Job
    from waypoint.roles import RoleMatcher
    base = "We build ML systems. Requirements: Python, PyTorch, Docker, AWS and five years of experience. " * 8
    a = Job(job_key="g:x:1", source="greenhouse", external_id="1", company="Acme", title="Applied AI Engineer",
            location="Tokyo", text=base + " Location Tokyo.")
    b = a.model_copy(update={"job_key": "g:x:2", "external_id": "2", "location": "Toronto", "text": base + " Location Toronto."})
    c = a.model_copy(update={"job_key": "g:x:3", "external_id": "3", "title": "AI Support Engineer", "text": "Help customers. " * 40})
    assert db.upsert_job(a) == "new" and db.upsert_job(b) == "duplicate" and db.upsert_job(c) == "new"
    assert prune_unmatched(db, RoleMatcher(cfg.roles)) == 1  # support role excluded by targets.yaml
    assert [j.job_key for j in db.jobs()] == ["g:x:1"]


def test_gupy_fetches_full_description_when_summary_is_short():
    import json as _json
    import httpx
    from waypoint.http import Http
    from waypoint.sources import Gupy
    page = ('<html><script id="__NEXT_DATA__" type="application/json">' + _json.dumps({"props": {"pageProps": {"job": {
        "description": "<p>Time de dados de crédito.</p>" * 5,
        "prerequisites": "<ul><li>Python e SQL</li><li>Estatística</li></ul>" * 5}}}}) + "</script></html>")

    def handler(req):
        if req.url.host == "portal.gupy.io":
            if req.url.params.get("offset") != "0":
                return httpx.Response(200, json={"data": []})
            return httpx.Response(200, json={"data": [{"id": 9, "name": "Cientista de Dados Pleno", "careerPageName": "X",
                                                       "jobUrl": "https://x.gupy.io/job/abc", "description": "Resumo curto"}]})
        if req.url.host == "x.gupy.io":
            return httpx.Response(200, text=page)
        return httpx.Response(404)
    g = Gupy(Http(delay=0, transport=httpx.MockTransport(handler)), {"max_pages": 1, "page_size": 20, "delay_seconds": 0})
    roles = {"data_scientist": {"search_terms": ["cientista de dados"]}}
    posts = list(g.fetch(roles, keep=lambda t: True))
    assert len(posts) == 1 and "Python e SQL" in posts[0].text and len(posts[0].text) > 200


def test_catalog_roles_and_custom_role(cfg, db, monkeypatch):
    from waypoint.models import Job
    from waypoint.roles import RoleMatcher
    from waypoint.settings import load_config, make_custom_role, save_local
    m = RoleMatcher(cfg.roles)
    assert m.match("Analista de BI Pleno") == "bi_analyst"
    assert m.match("MLOps Engineer") == "mlops_engineer"
    assert m.match("Analytics Engineer") == "analytics_engineer"
    assert m.match("Senior Machine Learning Engineer") == "ai_ml_engineer"
    assert m.match("Engenheiro de Dados") is None  # in the catalog, but not enabled by default
    for r in cfg.all_roles.values():
        assert r.get("label") and r.get("description") and r.get("search_terms")
    rid, role = make_custom_role("Prompt Engineer")
    save_local(cfg.paths.config, "targets", {"custom_roles": {rid: role}, "roles_enabled": [*cfg.roles, rid]})
    c2 = load_config(cfg.paths.root)
    assert rid in c2.roles and RoleMatcher(c2.roles).match("Senior Prompt Engineer") == rid


def test_disabling_a_role_keeps_its_postings(cfg, db):
    from waypoint.collect import prune_unmatched
    from waypoint.models import Job
    from waypoint.roles import RoleMatcher
    job = Job(job_key="g:x:9", source="greenhouse", external_id="9", company="Acme", title="Data Engineer",
              text="Build pipelines with Airflow and Spark. " * 20, role="data_engineer")
    db.upsert_job(job)
    assert prune_unmatched(db, RoleMatcher(cfg.all_roles)) == 0  # data_engineer is a known (disabled) role
    assert db.job("g:x:9") is not None
