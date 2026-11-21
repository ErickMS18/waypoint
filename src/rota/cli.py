"""Command-line interface: `rota --help`."""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Optional

import typer

from . import __version__
from .collect import add_manual, collect, make_http
from .db import DB
from .extract import extract_baseline, extract_llm, run_extraction
from .llm import LLMNotConfigured, make_client
from .settings import Config, load_config

app = typer.Typer(add_completion=False, help="Rota — radar de carreira pessoal (v1).", no_args_is_help=True)
eval_app = typer.Typer(help="Avaliação da extração de skills (conjunto rotulado).", no_args_is_help=True)
boards_app = typer.Typer(help="Empresas/boards configurados em config/sources.yaml.", no_args_is_help=True)
app.add_typer(eval_app, name="eval")
app.add_typer(boards_app, name="boards")


def _setup(verbose: bool = False) -> tuple[Config, DB]:
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    cfg.paths.ensure()
    return cfg, DB(cfg.paths.db)


def _client(db: DB, required: bool = False):
    try:
        return make_client(db)
    except LLMNotConfigured as e:
        if required:
            typer.secho(f"LLM não configurado: {e}", fg="red")
            raise typer.Exit(1)
        typer.secho(f"Aviso: {e} Usando o extrator por dicionário (baseline).", fg="yellow")
        return None


def _resolve_extractor(db: DB, extractor: str) -> str:
    if extractor != "auto":
        return extractor
    n_llm = db.conn.execute("SELECT COUNT(*) FROM extractions WHERE extractor='llm'").fetchone()[0]
    return "llm" if n_llm else "baseline"


@app.callback()
def main(version: bool = typer.Option(False, "--version", help="Mostra a versão.")):
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@app.command()
def init():
    """Cria pastas locais (data/, profile/, reports/) e o .env a partir do exemplo."""
    cfg, db = _setup()
    env = cfg.paths.root / ".env"
    if not env.exists():
        shutil.copy(cfg.paths.root / ".env.example", env)
        typer.echo("Criei .env — coloque sua chave de LLM nele.")
    typer.echo(f"Pronto. Banco local: {cfg.paths.db}")


@boards_app.command("check")
def boards_check():
    """Confere se cada empresa configurada existe e quantas vagas tem."""
    from .sources import Ashby, Greenhouse, Lever
    cfg, _ = _setup()
    http = make_http(cfg)
    for cls in (Greenhouse, Lever, Ashby):
        src = cls(http, cfg.sources.get(cls.name, {}))
        for board, n in src.check():
            mark = typer.style("ok", fg="green") if n is not None else typer.style("NÃO ENCONTRADO", fg="red")
            typer.echo(f"{cls.name:11s} {board:20s} {mark} {'' if n is None else f'{n} vagas'}")


@app.command("collect")
def collect_cmd(source: Optional[list[str]] = typer.Option(None, "--source", "-s", help="Só estas fontes."),
                verbose: bool = typer.Option(False, "-v")):
    """Coleta vagas dos cargos-alvo nas fontes habilitadas."""
    cfg, db = _setup(verbose)
    st = collect(cfg, db, only=source, progress=lambda m: typer.echo(m))
    typer.secho(f"Novas: {st.new} · já vistas: {st.seen} · duplicadas: {st.duplicate} · "
                f"removidas (fora dos cargos-alvo: {st.pruned}, quase duplicadas: {st.near_duplicates_removed}) · "
                f"total no banco: {db.count_jobs()}", fg="green")
    if st.skipped_empty:
        typer.echo(f"  ignoradas por texto curto demais (<200 caracteres): {st.skipped_empty}")
    for name, n in st.by_source.most_common():
        typer.echo(f"  {name}: +{n}")
    for e in st.errors:
        typer.secho(f"  erro: {e}", fg="red")


@app.command()
def add(file: Optional[Path] = typer.Option(None, "--file", "-f", help="Arquivo .txt/.md com a vaga."),
        title: str = typer.Option("", help="Título da vaga."), company: str = typer.Option(""),
        url: str = typer.Option("")):
    """Adiciona uma vaga colada manualmente (arquivo ou stdin)."""
    cfg, db = _setup()
    raw = file.read_text(encoding="utf-8") if file else sys.stdin.read()
    status, job = add_manual(cfg, db, raw, title=title, company=company, url=url)
    typer.echo(f"{status}: {job.title} → cargo '{job.role}' ({job.job_key})")


@app.command()
def extract(extractor: str = typer.Option("llm", help="llm | baseline"),
            limit: Optional[int] = typer.Option(None, help="Máximo de vagas (útil para testar)."),
            force: bool = typer.Option(False, help="Reprocessa mesmo se já extraído."),
            verbose: bool = typer.Option(False, "-v")):
    """Extrai skills, senioridade e modelo de trabalho de cada vaga."""
    cfg, db = _setup(verbose)
    client = _client(db, required=True) if extractor == "llm" else None
    jobs = db.jobs()[: limit or None]
    res = run_extraction(db, jobs, extractor, client, force=force,
                         progress=lambda i, n, j: typer.echo(f"[{i}/{n}] {j.company} — {j.title}"))
    typer.secho(f"{res}", fg="green")
    if client:
        typer.echo(f"Chamadas ao LLM: {client.calls} · cache: {client.cache_hits}")


@app.command()
def profile(resume: Path = typer.Argument(..., exists=True, help="Seu currículo (.pdf, .docx, .md, .txt)."),
            no_llm: bool = typer.Option(False, "--no-llm", help="Não envia nada ao LLM (só dicionário)."),
            redact: Optional[list[str]] = typer.Option(None, "--redact", help="Termos extras a remover antes do LLM.")):
    """Lê seu currículo e monta o perfil de skills (salvo em profile/, fora do Git)."""
    from .profile import build_profile
    cfg, db = _setup()
    client = None if no_llm else _client(db)
    prof = build_profile(resume, cfg.paths.profile, client=client, extra_redact=redact)
    typer.secho(f"Perfil com {len(prof.skills)} skills ({prof.method}) salvo em {cfg.paths.profile}", fg="green")
    for s in prof.skills[:30]:
        typer.echo(f"  {'●' * s.level}{'○' * (3 - s.level)}  {s.name}")
    typer.echo("Ajuste níveis na interface (rota ui) ou em profile/overrides.yaml.")


@app.command()
def analyze(extractor: str = typer.Option("auto", help="auto | llm | baseline"), top: int = 15):
    """Mostra as skills mais pedidas por cargo."""
    from .pipeline import analyze as run_analyze
    cfg, db = _setup()
    a = run_analyze(cfg, db, _resolve_extractor(db, extractor))
    typer.echo(f"{len(a.jobs_df)} vagas analisadas (extrator: {a.extractor})")
    for rid, t in a.tables.items():
        n = int((a.jobs_df["role"] == rid).sum())
        typer.secho(f"\n{cfg.roles[rid].get('label', rid)} — {n} vagas", bold=True)
        for _, r in t[~t["skill_id"].str.startswith("other:")].head(top).iterrows():
            bar = "█" * round(r["share_any"] * 30)
            typer.echo(f"  {r['name'][:32]:32s} {r['share_any']:>4.0%} {bar}  (obrig. {r['share_required']:.0%})")


@app.command()
def report(public: bool = typer.Option(False, help="Só dados de mercado, sem seu perfil (para publicar)."),
           extractor: str = typer.Option("auto"), no_llm: bool = typer.Option(False, "--no-llm")):
    """Gera o relatório (Markdown + gráficos + números para o post)."""
    from .pipeline import analyze as run_analyze, compute_gap, make_plan, make_report
    cfg, db = _setup()
    ex = _resolve_extractor(db, extractor)
    a = run_analyze(cfg, db, ex)
    if a.jobs_df.empty:
        typer.secho("Nenhuma vaga extraída ainda. Rode `rota collect` e `rota extract`.", fg="red")
        raise typer.Exit(1)
    gap = plan = None
    if not public:
        gap = compute_gap(cfg, a)
        plan = make_plan(cfg, a, gap, client=None if no_llm else _client(db))
    model = db.conn.execute("SELECT model FROM extractions WHERE extractor=? LIMIT 1", (ex,)).fetchone()
    files = make_report(cfg, a, gap=gap, plan=plan, model=model[0] if model else ex, public=public)
    for k, p in files.items():
        typer.echo(f"{k}: {p}")


@app.command()
def run(no_llm: bool = typer.Option(False, "--no-llm", help="Usa só o extrator por dicionário.")):
    """Tudo de uma vez: coleta → extração → relatório."""
    collect_cmd(source=None, verbose=False)
    if no_llm:
        extract(extractor="baseline", limit=None, force=False, verbose=False)
    else:
        cfg, db = _setup()
        ex = "llm" if _client(db) else "baseline"
        extract(extractor=ex, limit=None, force=False, verbose=False)
    report(public=False, extractor="auto", no_llm=no_llm)


@app.command()
def ui():
    """Abre a interface web local (Streamlit)."""
    cfg, _ = _setup()
    app_file = Path(__file__).parent / "ui" / "app.py"
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_file), "--server.headless", "false"],
                   cwd=cfg.paths.root, check=False)


# ----------------------------------------------------------------------------- eval
@eval_app.command("sample")
def eval_sample(n: int = typer.Option(40, help="Quantas vagas sortear."), seed: int = 42):
    """Sorteia vagas reais do seu banco (balanceadas por cargo e idioma) para rotular."""
    from .eval import stratified_sample, write_jsonl
    cfg, db = _setup()
    picked = stratified_sample(db.jobs(), n, list(cfg.roles), seed=seed)
    rows = [{"job_key": j.job_key, "title": j.title, "company": j.company, "url": j.url, "role": j.role,
             "lang": j.lang, "location": j.location, "source": j.source, "board": j.board,
             "external_id": j.external_id, "text": j.text} for j in picked]
    out = cfg.paths.eval_data / "texts.jsonl"
    write_jsonl(out, rows)
    typer.secho(f"{len(rows)} vagas salvas em {out}", fg="green")
    typer.echo("Esse arquivo fica só no seu computador (data/ está no .gitignore).")


@eval_app.command("fetch")
def eval_fetch():
    """Baixa de novo, pelas APIs públicas, o texto das vagas do eval/gold.jsonl que faltam localmente."""
    from .eval import load_gold, load_jsonl, write_jsonl
    from .sources import REGISTRY
    cfg, db = _setup()
    gold = load_gold(cfg.paths.eval_dir / "gold.jsonl")
    path = cfg.paths.eval_data / "texts.jsonl"
    have = {r["job_key"]: r for r in load_jsonl(path)}
    http = make_http(cfg)
    got = missing = 0
    for g in gold:
        if g.job_key in have:
            continue
        job = db.job(g.job_key)
        if job:
            have[g.job_key] = {"job_key": job.job_key, "title": job.title, "company": job.company, "url": job.url,
                               "role": job.role, "lang": job.lang, "text": job.text}
            got += 1
            continue
        src_name, board, ext_id = g.job_key.split(":", 2)
        cls = REGISTRY.get(src_name)
        p = cls(http, {}).fetch_one(board, ext_id) if cls and cls.refetchable else None
        if p:
            have[g.job_key] = {"job_key": g.job_key, "title": p.title, "company": p.company, "url": p.url,
                               "role": g.role, "lang": g.lang, "text": p.text}
            got += 1
        else:
            missing += 1
    write_jsonl(path, have.values())
    typer.echo(f"Baixadas: {got} · indisponíveis (vaga encerrada?): {missing} · total local: {len(have)}")


@eval_app.command("run")
def eval_run(extractor: str = typer.Option("both", help="both | llm | baseline"),
             update_readme: bool = typer.Option(False, "--update-readme")):
    """Mede precisão/recall/F1 da extração contra eval/gold.jsonl."""
    from .eval import evaluate, load_gold, load_jsonl, results_markdown, run_extractor, update_readme as upd
    from .models import Job
    from .settings import taxonomy_data
    cfg, db = _setup()
    gold = load_gold(cfg.paths.eval_dir / "gold.jsonl")
    texts = {r["job_key"]: Job(job_key=r["job_key"], source=r["job_key"].split(":")[0], external_id=r["job_key"],
                               company=r.get("company", ""), title=r.get("title", ""), text=r["text"],
                               lang=r.get("lang", "en"), role=r.get("role", ""))
             for r in load_jsonl(cfg.paths.eval_data / "texts.jsonl")}
    if not texts:
        typer.secho("Sem textos locais. Rode `rota eval fetch` antes.", fg="red")
        raise typer.Exit(1)
    results, out_dir = {}, cfg.paths.eval_dir / "results"
    out_dir.mkdir(exist_ok=True)
    if extractor in ("both", "baseline"):
        preds = run_extractor(gold, texts, extract_baseline)
        results["Dictionary baseline"] = evaluate(gold, preds)
    if extractor in ("both", "llm"):
        client = _client(db, required=True)
        preds = run_extractor(gold, texts, lambda j: extract_llm(j, client),
                              progress=lambda i, n: typer.echo(f"  LLM {i}/{n}"))
        results[f"LLM ({client.model_id})"] = evaluate(gold, preds)
    for name, r in results.items():
        slug = "baseline" if name.startswith("Dictionary") else "llm"
        (out_dir / f"{slug}.json").write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
        if r.get("n_jobs"):
            typer.echo(f"{name}: F1={r['skills']['f1']:.3f} P={r['skills']['precision']:.3f} "
                       f"R={r['skills']['recall']:.3f} (n={r['n_jobs']})")
    roles = {}
    for g in gold:
        roles[g.role] = roles.get(g.role, 0) + 1
    langs = {}
    for g in gold:
        langs[g.lang] = langs.get(g.lang, 0) + 1
    meta = {"n_gold": len(gold), "n_labels": sum(len(g.skills) for g in gold),
            "n_taxonomy": len(taxonomy_data()["skills"]), "date": date.today().isoformat(),
            "composition": ", ".join(f"{v} {cfg.roles.get(k, {}).get('label', k)}" for k, v in roles.items())
            + "; " + ", ".join(f"{v} {k.upper()}" for k, v in langs.items())}
    md = results_markdown(results, meta)
    (cfg.paths.eval_dir / "RESULTS.md").write_text("# Evaluation results\n\n" + md, encoding="utf-8")
    if update_readme and upd(cfg.paths.root / "README.md", md):
        typer.echo("README atualizado.")


if __name__ == "__main__":
    app()
