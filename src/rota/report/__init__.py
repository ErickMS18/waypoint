"""Markdown report, chart for LinkedIn and the numbers for the post."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd
from jinja2 import Environment, FileSystemLoader

from ..analysis.gap import STATUS_PT, market_fit
from ..analysis.plan import Plan
from ..models import REGION_PT, SENIORITY_ORDER, SENIORITY_PT
from ..settings import RESOURCES

# Reference palette (validated categorical slots 1-2) for a light surface.
SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
C_REQUIRED, C_NICE = "#2a78d6", "#eb6834"


def pct(x: float) -> str:
    return f"{x:.0%}"


def chart_top_skills(tbl: pd.DataFrame, path: Path, title: str, subtitle: str, top: int = 15) -> Path:
    """Horizontal stacked bars: % of postings asking for each skill (required vs nice-to-have)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = tbl[~tbl["skill_id"].str.startswith("other:")].head(top).iloc[::-1]
    fig, ax = plt.subplots(figsize=(10, 0.42 * len(t) + 1.9), dpi=160)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    y = range(len(t))
    ax.barh(y, t["share_required"] * 100, color=C_REQUIRED, height=0.62, label="Obrigatória",
            edgecolor=SURFACE, linewidth=2)
    ax.barh(y, t["share_nice"] * 100, left=t["share_required"] * 100, color=C_NICE, height=0.62,
            label="Diferencial", edgecolor=SURFACE, linewidth=2)
    for i, (_, r) in enumerate(t.iterrows()):
        ax.text(r["share_any"] * 100 + 1, i, f"{r['share_any']:.0%}", va="center", fontsize=9, color=INK_2)
    ax.set_yticks(list(y), t["name"], fontsize=10, color=INK)
    ax.set_xlim(0, min(100, t["share_any"].max() * 100 + 12))
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.tick_params(axis="x", colors=INK_2, labelsize=8)
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ax.spines.values():
        s.set_visible(False)
    h = fig.get_figheight()
    fig.text(0.01, 1 - 0.28 / h, title, ha="left", va="top", fontsize=14, fontweight="bold", color=INK)
    fig.text(0.01, 1 - 0.62 / h, subtitle, ha="left", va="top", fontsize=9.5, color=INK_2)
    ax.legend(loc="lower left", bbox_to_anchor=(0, 1.0), ncol=2, frameon=False, fontsize=9, labelcolor=INK_2,
              handlelength=1.2, borderaxespad=0.3)
    fig.tight_layout(rect=(0, 0, 1, 1 - 0.85 / h))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


def post_numbers(jobs_df: pd.DataFrame, tbl_by_role: dict[str, pd.DataFrame], roles_cfg: dict) -> dict[str, Any]:
    """Facts that can go straight into a LinkedIn post (no personal data)."""
    out: dict[str, Any] = {
        "n_jobs": int(len(jobs_df)),
        "n_companies": int(jobs_df["company"].nunique()) if len(jobs_df) else 0,
        "sources": sorted(jobs_df["source"].unique().tolist()) if len(jobs_df) else [],
        "by_region": {REGION_PT.get(k, k): int(v) for k, v in jobs_df["region"].value_counts().items()} if len(jobs_df) else {},
        "roles": {},
    }
    for rid, tbl in tbl_by_role.items():
        j = jobs_df[jobs_df["role"] == rid]
        sen = j["seniority"].value_counts(normalize=True)
        t = tbl[~tbl["skill_id"].str.startswith("other:")]
        out["roles"][rid] = {
            "label": roles_cfg.get(rid, {}).get("label", rid),
            "n_jobs": int(len(j)),
            "top_required": [(r["name"], round(r["share_required"] * 100)) for _, r in
                             t.sort_values("share_required", ascending=False).head(5).iterrows()],
            "top_nice": [(r["name"], round(r["share_nice"] * 100)) for _, r in
                         t.sort_values("share_nice", ascending=False).head(5).iterrows()],
            "senior_or_above_pct": round(float(sen.get("senior", 0) + sen.get("staff_plus", 0)) * 100),
            "entry_pct": round(float(sen.get("intern", 0) + sen.get("junior", 0)) * 100),
            "english_required_pct": round(float(t.loc[t["skill_id"] == "english", "share_required"].sum()) * 100),
        }
    return out


def render_report(ctx: dict[str, Any], public: bool = False) -> str:
    env = Environment(loader=FileSystemLoader(RESOURCES / "templates"), trim_blocks=True, lstrip_blocks=True)
    env.filters["pct"] = pct
    env.globals.update(SENIORITY_PT=SENIORITY_PT, REGION_PT=REGION_PT, STATUS_PT=STATUS_PT,
                       SENIORITY_ORDER=SENIORITY_ORDER)
    return env.get_template("report.md.j2").render(**ctx, public=public)


def write_report(out_dir: Path, *, jobs_df: pd.DataFrame, tables: dict[str, pd.DataFrame], roles_cfg: dict,
                 seniority: pd.DataFrame, regions: pd.DataFrame, region_cmp: pd.DataFrame, trends: pd.DataFrame,
                 gap: Optional[pd.DataFrame], plan: Optional[Plan], extractor_model: str,
                 public: bool = False) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    files: dict[str, Path] = {}
    numbers = post_numbers(jobs_df, tables, roles_cfg)
    for rid, tbl in tables.items():
        n = numbers["roles"][rid]["n_jobs"]
        if n:
            files[f"chart_{rid}"] = chart_top_skills(
                tbl, out_dir / f"top_skills_{rid}.png",
                title=f"O que as vagas de {roles_cfg.get(rid, {}).get('label', rid)} pedem",
                subtitle=f"% de {n} vagas reais que citam cada skill · coletadas em {stamp} · Rota")
    dates = jobs_df["published_at"].dropna()
    ctx = {
        "stamp": stamp, "numbers": numbers,
        "tables": {k: t[~t["skill_id"].str.startswith("other:")].head(20) for k, t in tables.items()}, "roles_cfg": roles_cfg,
        "seniority": seniority, "regions": regions, "region_cmp": region_cmp, "trends": trends,
        "gap": None if public else gap, "fit": None if (public or gap is None) else market_fit(gap),
        "plan": None if public else plan, "extractor_model": extractor_model,
        "date_min": dates.min().strftime("%Y-%m-%d") if len(dates) else "?",
        "date_max": dates.max().strftime("%Y-%m-%d") if len(dates) else "?",
        "charts": {k: v.name for k, v in files.items()},
    }
    name = "market_report.md" if public else "rota_report.md"
    files["report"] = out_dir / name
    files["report"].write_text(render_report(ctx, public=public), encoding="utf-8")
    files["numbers"] = out_dir / "post_numbers.json"
    files["numbers"].write_text(json.dumps(numbers, ensure_ascii=False, indent=2), encoding="utf-8")
    return files


def linkedin_post_draft(numbers: dict[str, Any]) -> str:
    """A factual first draft of the post (Portuguese). Edit before posting."""
    lines = [f"Analisei {numbers['n_jobs']} vagas reais de {numbers['n_companies']} empresas para entender "
             "o que o mercado pede de quem quer trabalhar com IA e dados.", ""]
    for r in numbers["roles"].values():
        if not r["n_jobs"]:
            continue
        top = ", ".join(f"{n} ({p}%)" for n, p in r["top_required"][:5])
        nice = ", ".join(f"{n}" for n, _ in r["top_nice"][:3])
        lines += [f"📌 {r['label']} ({r['n_jobs']} vagas)",
                  f"• Mais pedidas como obrigatórias: {top}",
                  f"• Diferenciais que mais aparecem: {nice}",
                  f"• Só {r['entry_pct']}% eram para estágio/júnior; {r['senior_or_above_pct']}% para sênior ou acima.", ""]
    lines += ["Como fiz: um pipeline em Python que coleta vagas de APIs públicas (Greenhouse, Lever, Ashby…), "
              "usa um LLM para extrair as skills de cada vaga e compara com o meu currículo. "
              "Medi a extração contra um conjunto rotulado à mão — os números estão no README.", "",
              "Código aberto: <link do GitHub>", "", "#dados #machinelearning #ia #carreira"]
    return "\n".join(lines)
