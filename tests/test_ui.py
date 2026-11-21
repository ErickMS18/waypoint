from pathlib import Path

import pytest

from waypoint.collect import collect
from waypoint.extract import run_extraction

APP = Path(__file__).resolve().parents[1] / "src" / "waypoint" / "ui" / "app.py"


def test_ui_renders_empty(project):
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at.exception
    assert any("Ainda não há vagas" in i.value for i in at.info)


def test_ui_renders_with_data_and_builds_plan(cfg, db, transport):
    from streamlit.testing.v1 import AppTest
    collect(cfg, db, transport=transport)
    run_extraction(db, db.jobs(), "baseline")
    at = AppTest.from_file(str(APP), default_timeout=60).run()
    assert not at.exception, at.exception
    gen = next(b for b in at.button if b.label == "Gerar plano")
    gen.click().run()
    assert not at.exception, at.exception
    assert any("Esta semana" in s.value for s in at.subheader)
