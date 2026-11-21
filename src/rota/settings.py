"""Project paths and configuration loading.

The project root is the folder that contains ``config/targets.yaml``. It is found by
walking up from the current directory, or set explicitly with the ``ROTA_HOME``
environment variable.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

RESOURCES = Path(__file__).parent / "resources"


def find_root(start: Path | None = None) -> Path:
    env = os.environ.get("ROTA_HOME")
    if env:
        return Path(env).expanduser().resolve()
    here = (start or Path.cwd()).resolve()
    for p in [here, *here.parents]:
        if (p / "config" / "targets.yaml").exists():
            return p
    raise FileNotFoundError(
        "Could not find config/targets.yaml. Run rota from the project folder "
        "or set ROTA_HOME to it."
    )


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def config(self) -> Path:
        return self.root / "config"

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def db(self) -> Path:
        return self.data / "rota.db"

    @property
    def profile(self) -> Path:
        return self.root / "profile"

    @property
    def reports(self) -> Path:
        return self.root / "reports"

    @property
    def inbox(self) -> Path:
        return self.root / "inbox"

    @property
    def eval_dir(self) -> Path:
        return self.root / "eval"

    @property
    def eval_data(self) -> Path:
        return self.data / "eval"

    def ensure(self) -> "Paths":
        for d in (self.data, self.profile, self.reports, self.inbox, self.eval_data):
            d.mkdir(parents=True, exist_ok=True)
        return self


def load_yaml(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@dataclass
class Config:
    paths: Paths
    targets: dict[str, Any]
    sources: dict[str, Any]
    focus: dict[str, Any]

    @property
    def roles(self) -> dict[str, dict[str, Any]]:
        return self.targets.get("roles", {})

    @property
    def seniority_focus(self) -> list[str]:
        return list(self.targets.get("seniority_focus", ["intern", "junior", "mid"]))


def load_config(root: Path | None = None) -> Config:
    paths = Paths(root or find_root())
    load_dotenv(paths.root / ".env", override=False)
    cfg = Config(
        paths=paths,
        targets=load_with_local(paths.config, "targets"),
        sources=load_with_local(paths.config, "sources"),
        focus=load_with_local(paths.config, "focus"),
    )
    validate_focus(cfg.focus)
    return cfg


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in override.items():
        out[k] = deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load_with_local(config_dir: Path, name: str) -> dict[str, Any]:
    """config/<name>.yaml, overridden by the git-ignored config/<name>.local.yaml if it exists."""
    data = load_yaml(config_dir / f"{name}.yaml")
    local = config_dir / f"{name}.local.yaml"
    return deep_merge(data, load_yaml(local)) if local.exists() else data


def validate_focus(focus: dict[str, Any]) -> None:
    w = focus.get("weights", {})
    total = sum(float(v) for v in w.values())
    if w and abs(total - 100) > 0.01:
        raise ValueError(f"focus.yaml: weights must sum to 100 (got {total:g}).")


@lru_cache(maxsize=1)
def taxonomy_data() -> dict[str, Any]:
    return load_yaml(RESOURCES / "skills.yaml")
