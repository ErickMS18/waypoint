"""Shared fixtures: an isolated project folder and a fake network."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import httpx
import pytest
import yaml

from waypoint.db import DB
from waypoint.settings import load_config

REPO = Path(__file__).resolve().parents[1]
FIX = Path(__file__).parent / "fixtures"


def _load(name: str):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def fake_jobs_api(request: httpx.Request) -> httpx.Response:
    url = str(request.url)
    host, path = request.url.host, request.url.path
    if host == "boards-api.greenhouse.io" and path == "/v1/boards/acme/jobs":
        return httpx.Response(200, json=_load("greenhouse_acme.json"))
    if host == "boards-api.greenhouse.io" and path == "/v1/boards/acme/jobs/101":
        return httpx.Response(200, json=_load("greenhouse_acme.json")["jobs"][0])
    if host == "api.lever.co" and path == "/v0/postings/betaco":
        return httpx.Response(200, json=_load("lever_betaco.json"))
    if host == "api.eu.lever.co" and path == "/v0/postings/euco":
        return httpx.Response(200, json=[])
    if host == "api.ashbyhq.com" and path == "/posting-api/job-board/gammaai":
        return httpx.Response(200, json=_load("ashby_gammaai.json"))
    if host == "himalayas.app" and path == "/jobs/api/search":
        page = request.url.params.get("page", "1")
        return httpx.Response(200, json=_load("himalayas_search.json") if page == "1" else {"jobs": []})
    if host == "portal.gupy.io" and path == "/api/job-search/jobs":
        off = request.url.params.get("offset", "0")
        return httpx.Response(200, json=_load("gupy_search.json") if off == "0" else {"data": []})
    return httpx.Response(404, text=f"not found: {url}")


@pytest.fixture
def transport():
    return httpx.MockTransport(fake_jobs_api)


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> Path:
    """A copy of the repo config pointing at fake boards."""
    shutil.copytree(REPO / "config", tmp_path / "config")
    shutil.copy(REPO / ".env.example", tmp_path / ".env.example")
    src = yaml.safe_load((tmp_path / "config" / "sources.yaml").read_text(encoding="utf-8"))
    src["http"]["delay_seconds"] = 0
    src["greenhouse"]["boards"] = ["acme", "doesnotexist"]
    src["lever"]["sites"] = ["betaco", "euco"]
    src["ashby"]["boards"] = ["gammaai"]
    src["himalayas"]["max_pages"] = 2
    src["gupy"].update({"enabled": True, "delay_seconds": 0, "max_pages": 2})
    (tmp_path / "config" / "sources.yaml").write_text(yaml.safe_dump(src, allow_unicode=True), encoding="utf-8")
    (tmp_path / "inbox").mkdir()
    (tmp_path / "inbox" / "vaga.txt").write_text(
        "title: Engenheira de Machine Learning\ncompany: Loja X\n---\n"
        "Procuramos pessoa para criar modelos de recomendação. Requisitos: Python, PySpark e AWS. "
        "Diferenciais: experiência com MLflow. " * 3, encoding="utf-8")
    monkeypatch.setenv("WAYPOINT_HOME", str(tmp_path))
    for k in ("LLM_PROVIDER", "GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "LLM_MODEL", "LLM_MIN_INTERVAL"):
        monkeypatch.delenv(k, raising=False)
    return tmp_path


@pytest.fixture
def cfg(project):
    c = load_config(project)
    c.paths.ensure()
    return c


@pytest.fixture
def db(cfg):
    d = DB(cfg.paths.db)
    yield d
    d.close()
