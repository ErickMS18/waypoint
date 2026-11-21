"""The local app's API (what the interface calls) and the static interface files."""
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from waypoint.collect import collect
from waypoint.extract import run_extraction

MON = "2026-11-23"
STATIC = Path(__file__).resolve().parents[1] / "src" / "waypoint" / "web" / "static"


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setenv("WAYPOINT_TODAY", MON)


@pytest.fixture
def api(project):
    from waypoint.web import server
    server._cache.update(key=None, analysis=None)
    return TestClient(server.app)


@pytest.fixture
def filled(cfg, db, transport):
    collect(cfg, db, transport=transport)
    run_extraction(db, db.jobs(), "baseline")
    return cfg


def test_static_interface_is_served(api):
    r = api.get("/")
    assert r.status_code == 200 and "<html" in r.text.lower()
    for f in ("app.js", "app.css", "fonts/instrument-serif-latin-400-normal.woff2"):
        assert api.get(f"/static/{f}").status_code == 200


def test_every_screen_answers_on_an_empty_install(api):
    for path in ("/api/shell", "/api/today", "/api/week", "/api/routine", "/api/projects", "/api/plan",
                 "/api/market", "/api/compare", "/api/jobs", "/api/roles", "/api/profile", "/api/report", "/api/update"):
        r = api.get(path)
        assert r.status_code == 200, (path, r.text)
    assert api.get("/api/today").json()["empty"] is True


def test_every_screen_answers_with_data(api, filled):
    assert api.post("/api/plan", json={"ideas": False}).json()["plan"]["this_week"]
    for path in ("/api/shell", "/api/today", "/api/week?offset=1", "/api/market", "/api/market?role=ai_ml_engineer&top=10",
                 "/api/compare", "/api/jobs?q=engineer", "/api/roles", "/api/profile", "/api/report"):
        r = api.get(path)
        assert r.status_code == 200, (path, r.text)
    m = api.get("/api/market").json()
    sid = m["skills"][0]["skill_id"]
    assert api.get(f"/api/market/skill/{sid}").json()["jobs"]
    key = api.get("/api/jobs").json()["jobs"][0]["job_key"]
    assert api.get(f"/api/jobs/{key}").json()["title"]


def test_projects_today_log_undo_and_routine(api):
    p = api.post("/api/projects", json={"name": "TDE de Banco de Dados", "area": "faculdade", "hours": 4,
                                        "deadline": (date.fromisoformat(MON) + timedelta(3)).isoformat(), "breakdown": True}).json()
    assert len(p["tasks"]) == 4
    t = api.get("/api/today").json()
    assert t["blocks"] and t["blocks"][0]["area"] == "faculdade"
    item = t["blocks"][0]["item"]
    assert api.post("/api/log", json={"item": item, "hours": 1}).json()["ok"]
    assert api.get("/api/today").json()["done_hours"] == 1
    assert api.post("/api/undo", json={"item": item}).json()["ok"]
    assert api.get("/api/today").json()["done_hours"] == 0
    r = api.put("/api/routine", json={"availability": {str(i): 1.0 for i in range(7)}, "max_block": 1.5,
                                      "overrides": [{"date": MON, "hours": 0}]}).json()
    assert r["availability"]["0"] == 1.0 and r["overrides"][0]["hours"] == 0
    assert api.get("/api/today").json()["blocks"] == []
    api.put(f"/api/projects/{p['id']}", json={"archived": True})
    assert api.delete(f"/api/projects/{p['id']}").json()["ok"]


def test_capture_without_key_uses_rules(api):
    d = api.post("/api/capture", json={"text": "Prova de IA na quinta, uns 6h de estudo"}).json()
    assert d["area"] == "faculdade" and d["deadline"] == "2026-11-26" and d["hours"] == 6 and d["tasks"]
    assert d["name"].startswith("Prova de IA")


def test_borrow_never_takes_exploration(api):
    assert api.post("/api/borrow", json={"foco": "exploracao", "hours": 2}).status_code == 400
    assert api.post("/api/borrow", json={"foco": "carreira", "hours": 2}).json()["ok"]


def test_roles_settings_and_focus(api, filled):
    r = api.put("/api/roles", json={"enabled": ["ai_ml_engineer", "data_engineer"]}).json()
    assert {x["id"] for x in r["roles"] if x["enabled"]} == {"ai_ml_engineer", "data_engineer"}
    assert api.put("/api/roles", json={"enabled": []}).status_code == 400
    r = api.post("/api/roles/custom", json={"name": "Prompt Engineer"}).json()
    assert any(x["id"] == "custom_prompt_engineer" and x["enabled"] for x in r["roles"])
    s = api.put("/api/settings", json={"theme": "light", "lang": "en", "evil": 1}).json()
    assert s["theme"] == "light" and s["lang"] == "en" and "evil" not in s
    f = api.put("/api/focus", json={"weights": {"carreira": 2, "exploracao": 1, "interesses": 1}, "weekly_hours": 8}).json()["focus"]
    assert sum(f["weights"].values()) == 100 and f["weekly_hours"] == 8


def test_interface_strings_exist_in_both_languages():
    import json
    import re
    js = (STATIC / "i18n.js").read_text(encoding="utf-8")
    body = js[js.index("{"): js.rindex("}") + 1]
    pt_part, en_part = body.split("\n  en: {")
    pt_keys = set(re.findall(r'^\s{4}([a-zA-Z0-9_]+):', pt_part, re.M))
    en_keys = set(re.findall(r'^\s{4}([a-zA-Z0-9_]+):', en_part, re.M))
    assert pt_keys and pt_keys == en_keys, sorted(pt_keys ^ en_keys)
    used = set()
    for f in STATIC.glob("*.js"):
        used |= set(re.findall(r'\bt\(\s*["\']([a-zA-Z0-9_]+)["\']', f.read_text(encoding="utf-8")))
    used = {k for k in used if not k.endswith("_")}  # dynamic prefixes like t("area_" + a)
    assert not (used - pt_keys), sorted(used - pt_keys)


# ----------------------------------------------------------------------------- background update + launcher
def test_update_status_and_launcher_helpers(cfg, db, transport):
    from waypoint import pipeline as pl
    from waypoint import updater
    res = pl.update_all(cfg, db, client=None, transport=transport)
    assert res["collect"]["novas"] > 0 and pl.last_update(cfg) and pl.load_plan(cfg)
    updater.write_status(cfg, state="running", pid=999999)
    assert updater.read_status(cfg)["state"] == "failed"
    assert updater.hours_since_last_update(cfg) < 1
    updater.save_ui_settings(cfg, auto_update_on_open=False)
    assert updater.load_ui_settings(cfg)["auto_update_on_open"] is False


def test_launcher_opens_browser_and_auto_updates_when_stale(cfg, monkeypatch):
    from waypoint import launcher, updater
    opened, started = [], []
    monkeypatch.setattr(launcher, "server_up", lambda timeout=0.5: True)
    monkeypatch.setattr(launcher, "stale_server_pid", lambda root: None)
    monkeypatch.setattr(launcher, "open_window", lambda root: opened.append(launcher.URL))
    monkeypatch.setattr(updater, "start_background_update", lambda c: started.append(1) or True)
    (cfg.paths.data / "last_update.txt").write_text("01/01/2026 08:00", encoding="utf-8")
    assert launcher.main() == 0
    assert opened == [launcher.URL] and started == [1]
    updater.save_ui_settings(cfg, auto_update_on_open=False)
    started.clear()
    launcher.main()
    assert started == []


def test_launcher_detects_outdated_server(cfg, monkeypatch):
    import json
    from waypoint import launcher
    info = cfg.paths.data / "logs" / "ui_server.json"
    info.parent.mkdir(parents=True, exist_ok=True)
    info.write_text(json.dumps({"pid": 4242, "stamp": "0"}), encoding="utf-8")
    assert launcher.stale_server_pid(cfg.paths.root) == 4242
    info.write_text(json.dumps({"pid": 4242, "stamp": launcher.code_stamp()}), encoding="utf-8")
    assert launcher.stale_server_pid(cfg.paths.root) is None
