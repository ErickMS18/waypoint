"""Project paths and configuration loading.

The project root is the folder that contains ``config/targets.yaml``. It is found by
walking up from the current directory, or set explicitly with the ``WAYPOINT_HOME``
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
    env = os.environ.get("WAYPOINT_HOME")
    if env:
        return Path(env).expanduser().resolve()
    here = (start or Path.cwd()).resolve()
    for p in [here, *here.parents]:
        if (p / "config" / "targets.yaml").exists():
            return p
    raise FileNotFoundError(
        "Could not find config/targets.yaml. Run waypoint from the project folder "
        "or set WAYPOINT_HOME to it."
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
        return self.data / "waypoint.db"

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
    def all_roles(self) -> dict[str, dict[str, Any]]:
        """Every known role: catalog + custom (or a legacy explicit `roles:` block)."""
        if self.targets.get("roles"):
            return dict(self.targets["roles"])
        out = dict(roles_catalog())
        out.update(self.targets.get("custom_roles") or {})
        return out

    @property
    def roles(self) -> dict[str, dict[str, Any]]:
        """Enabled roles, in catalog order (custom roles last)."""
        if self.targets.get("roles"):
            return dict(self.targets["roles"])
        enabled = list(self.targets.get("roles_enabled") or [])
        return {rid: r for rid, r in self.all_roles.items() if rid in enabled}

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
def roles_catalog() -> dict[str, dict[str, Any]]:
    return dict(load_yaml(RESOURCES / "roles_catalog.yaml").get("roles", {}))


def save_local(config_dir: Path, name: str, updates: dict[str, Any]) -> Path:
    """Merge `updates` into config/<name>.local.yaml (git-ignored) and write it back."""
    path = config_dir / f"{name}.local.yaml"
    current = load_yaml(path) if path.exists() else {}
    for k, v in updates.items():
        current[k] = v
    header = "# Configuração só desta máquina (fora do Git). Editada pela interface do Waypoint.\n"
    path.write_text(header + yaml.safe_dump(current, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def make_custom_role(name: str) -> tuple[str, dict[str, Any]]:
    """Build a role definition from a free-text title (e.g. 'Prompt Engineer')."""
    import re
    import unicodedata
    folded = unicodedata.normalize("NFKD", name.lower()).encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9+#]+", folded)
    if not words:
        raise ValueError("Nome de cargo vazio.")
    rid = "custom_" + "_".join(words)[:40]
    pattern = r"\b" + r".{0,15}".join(re.escape(w) for w in words)
    return rid, {
        "label": name.strip(),
        "summary": "Cargo personalizado criado por você.",
        "description": "Cargo personalizado: o Waypoint procura vagas cujo título contém estas palavras, nesta ordem.",
        "day_to_day": [],
        "typical_skills": [],
        "search_terms": [name.strip().lower()],
        "title_include": [pattern],
        "title_exclude": [r"\b(director|diretor[a]?|vp|head of)\b"],
        "custom": True,
    }


@lru_cache(maxsize=1)
def taxonomy_data() -> dict[str, Any]:
    return load_yaml(RESOURCES / "skills.yaml")
