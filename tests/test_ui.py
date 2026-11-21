from pathlib import Path

import pytest

from waypoint.collect import collect
from waypoint.extract import run_extraction

APP = Path(__file__).resolve().parents[1] / "src" / "waypoint" / "ui" / "app.py"
PAGES = ["🏠 Início", "📊 Mercado", "⚖️ Comparar cargos", "👤 Meu perfil", "🗺️ Plano", "🎯 Cargos", "💼 Vagas",
         "📝 Relatório e post"]


def _app():
    from streamlit.testing.v1 import AppTest
    return AppTest.from_file(str(APP), default_timeout=90)


def test_ui_every_page_renders_empty(project):
    at = _app().run()
    assert not at.exception, at.exception
    assert any("Primeiros passos" in s.value for s in at.subheader)
    for p in PAGES[1:]:
        at.sidebar.radio[0].set_value(p).run()
        assert not at.exception, (p, at.exception)


@pytest.fixture
def filled(cfg, db, transport):
    collect(cfg, db, transport=transport)
    run_extraction(db, db.jobs(), "baseline")
    return cfg


def test_ui_every_page_renders_with_data(filled):
    at = _app().run()
    assert not at.exception, at.exception
    assert any(m.label == "Vagas analisadas" for m in at.metric)
    for p in PAGES[1:]:
        at.sidebar.radio[0].set_value(p).run()
        assert not at.exception, (p, at.exception)


def test_ui_generates_plan_and_marks_done(filled):
    from waypoint import pipeline as pl
    at = _app().run()
    at.sidebar.radio[0].set_value("🗺️ Plano").run()
    next(b for b in at.button if b.label == "Gerar plano").click().run()
    assert not at.exception, at.exception
    assert pl.load_plan(filled) is not None
    assert any("Esta semana" in s.value for s in at.subheader)
    at.checkbox(key="plan_wk_0").check().run()
    assert not at.exception, at.exception
    assert len(pl.load_done(filled)) == 1


def test_ui_roles_toggle_and_custom_role(filled):
    from waypoint.settings import load_config
    at = _app().run()
    at.sidebar.radio[0].set_value("🎯 Cargos").run()
    at.toggle(key="role_on_data_engineer").set_value(True).run()
    next(b for b in at.button if b.label == "Salvar cargos").click().run()
    assert not at.exception, at.exception
    assert "data_engineer" in load_config(filled.paths.root).roles
    at.text_input[0].input("Prompt Engineer")
    next(b for b in at.button if b.label == "Adicionar cargo").click()
    at.run()
    assert not at.exception, at.exception
    assert "custom_prompt_engineer" in load_config(filled.paths.root).roles


def test_update_status_and_launcher_helpers(cfg, db, transport, monkeypatch):
    from waypoint import pipeline as pl
    from waypoint import updater
    res = pl.update_all(cfg, db, client=None, transport=transport)
    assert res["collect"]["novas"] > 0 and pl.last_update(cfg) and pl.load_plan(cfg)
    updater.write_status(cfg, state="running", pid=999999)  # dead pid -> reported as failed, never stuck
    assert updater.read_status(cfg)["state"] == "failed"
    assert updater.hours_since_last_update(cfg) < 1
    updater.save_ui_settings(cfg, auto_update_on_open=False)
    assert updater.load_ui_settings(cfg)["auto_update_on_open"] is False


def test_launcher_opens_browser_and_auto_updates_when_stale(cfg, monkeypatch):
    from waypoint import launcher, updater
    opened, started = [], []
    monkeypatch.setattr(launcher, "server_up", lambda timeout=0.5: True)
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: opened.append(url))
    monkeypatch.setattr(updater, "start_background_update", lambda c: started.append(1) or True)
    (cfg.paths.data / "last_update.txt").write_text("01/01/2026 08:00", encoding="utf-8")
    assert launcher.main() == 0
    assert opened == [launcher.URL] and started == [1]
    updater.save_ui_settings(cfg, auto_update_on_open=False)
    started.clear()
    launcher.main()
    assert started == []
