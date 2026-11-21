import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from waypoint.collect import collect
from waypoint.extract import run_extraction

APP = Path(__file__).resolve().parents[1] / "src" / "waypoint" / "ui" / "app.py"
PAGES = ["today", "week", "projects", "plan", "market", "compare", "jobs", "roles", "profile", "report"]
MON = "2026-11-23"


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    monkeypatch.setenv("WAYPOINT_TODAY", MON)


def _app():
    from streamlit.testing.v1 import AppTest
    return AppTest.from_file(str(APP), default_timeout=90)


def _go(at, page):
    at.button(key=f"nav_{page}").click().run()
    assert not at.exception, (page, at.exception)
    return at


@pytest.mark.parametrize("lang_", ["pt", "en"])
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_every_page_renders_empty_in_both_languages_and_themes(project, lang_, theme):
    from waypoint import updater
    from waypoint.settings import load_config
    updater.save_ui_settings(load_config(project), lang=lang_, theme=theme)
    at = _app().run()
    assert not at.exception, at.exception
    for p in PAGES[1:]:
        _go(at, p)


@pytest.fixture
def filled(cfg, db, transport):
    collect(cfg, db, transport=transport)
    run_extraction(db, db.jobs(), "baseline")
    return cfg


def test_every_page_renders_with_data(filled):
    at = _app().run()
    assert not at.exception, at.exception
    for p in PAGES[1:]:
        _go(at, p)


def test_full_flow_plan_project_today_done_undo(filled):
    from waypoint import orchestrator as orc
    from waypoint import pipeline as pl
    at = _app().run()
    _go(at, "plan")
    at.button(key="gen_plan").click().run()
    assert not at.exception, at.exception
    assert pl.load_plan(filled) is not None
    _go(at, "projects")
    at.text_input[0].input("TDE de Banco de Dados")
    next(b for b in at.button if b.label in ("Criar projeto", "Create project")).click()
    at.run()
    assert not at.exception, at.exception
    st_ = orc.State.load(orc.state_path(filled.paths.data))
    assert st_.projects and st_.projects[0].tasks  # template breakdown without a key
    _go(at, "today")
    assert any("now_done" == b.key for b in at.button)
    at.button(key="now_done").click().run()
    assert not at.exception, at.exception
    st_ = orc.State.load(orc.state_path(filled.paths.data))
    assert len(st_.log) == 1
    at.button(key="undo_log").click().run()
    assert orc.State.load(orc.state_path(filled.paths.data)).log == []


def test_risk_offers_borrow_never_exploration(filled):
    from waypoint import orchestrator as orc
    from waypoint import pipeline as pl
    from waypoint.db import DB
    a = pl.analyze(filled, DB(filled.paths.db), "baseline")
    pl.save_plan(filled, pl.make_plan(filled, a, pl.compute_gap(filled, a), lang="pt"), lang="pt")
    s = orc.State(availability={str(i): 2.0 for i in range(7)})
    s.projects.append(orc.Project(id="p1", name="Artigo SBSEG", area="pesquisa", hours=40,
                                  deadline=(date.fromisoformat(MON) + timedelta(2)).isoformat()))
    s.save(orc.state_path(filled.paths.data))
    at = _app().run()
    assert not at.exception, at.exception
    keys = [b.key for b in at.button if b.key and b.key.startswith("borrow_")]
    assert keys and not any("exploracao" in k for k in keys)
    at.button(key=keys[0]).click().run()
    assert orc.State.load(orc.state_path(filled.paths.data)).borrow


def test_roles_toggle_and_custom_role(filled):
    from waypoint.settings import load_config
    at = _app().run()
    _go(at, "roles")
    at.toggle(key="role_on_data_engineer").set_value(True)
    at.button(key="save_roles").click().run()
    assert not at.exception, at.exception
    assert "data_engineer" in load_config(filled.paths.root).roles
    at.text_input[0].input("Prompt Engineer")
    next(b for b in at.button if b.label in ("Adicionar cargo", "Add role")).click()
    at.run()
    assert not at.exception, at.exception
    assert "custom_prompt_engineer" in load_config(filled.paths.root).roles


def test_theme_and_language_toggles_persist(project):
    from waypoint import updater
    from waypoint.settings import load_config
    at = _app().run()
    at.sidebar.button_group(key="ui_lang").set_value("en").run()
    at.sidebar.button_group(key="ui_theme").set_value("light").run()
    assert not at.exception, at.exception
    s = updater.load_ui_settings(load_config(project))
    assert s["lang"] == "en" and s["theme"] == "light"
    assert any(b.label.endswith("Today") for b in at.sidebar.button)


def test_all_ui_strings_have_both_languages():
    from waypoint.ui.i18n import S
    src = APP.read_text(encoding="utf-8")
    used = set(re.findall(r'\bt\("([a-z0-9_]+)"\)', src)) | set(re.findall(r'\bt\("([a-z0-9_]+)",', src))
    assert not [k for k in used if k not in S]
    assert all(set(v) == {"pt", "en"} and all(v.values()) for v in S.values())


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
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: opened.append(url))
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
