"""Rota — local web UI. Start with `rota ui` (or `streamlit run src/rota/ui/app.py`)."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from rota.analysis.gap import STATUS_PT, market_fit
from rota.collect import add_manual, collect
from rota.db import DB
from rota.extract import run_extraction
from rota.llm import LLMNotConfigured, config_from_env, make_client
from rota.models import REGION_PT, SENIORITY_PT
from rota.pipeline import analyze, compute_gap, make_plan, make_report
from rota.profile import build_profile, effective_levels, load_profile, save_overrides
from rota.report import chart_top_skills, linkedin_post_draft, post_numbers
from rota.settings import load_config

st.set_page_config(page_title="Rota", page_icon="🧭", layout="wide")

cfg = load_config()
cfg.paths.ensure()
db = DB(cfg.paths.db)


def llm_client():
    try:
        return make_client(db)
    except LLMNotConfigured:
        return None


def llm_status() -> str:
    try:
        c = config_from_env()
        return f"LLM: {c.provider}/{c.model}"
    except LLMNotConfigured as e:
        return f"LLM não configurado — {e}"


def current_extractor() -> str:
    n = db.conn.execute("SELECT COUNT(*) FROM extractions WHERE extractor='llm'").fetchone()[0]
    return "llm" if n else "baseline"


st.title("🧭 Rota")
st.caption(f"{db.count_jobs()} vagas no banco local · {llm_status()} · extrator em uso: {current_extractor()}")

tab_market, tab_gap, tab_plan, tab_jobs, tab_update, tab_post = st.tabs(
    ["Mercado", "Meu perfil e gap", "Plano", "Vagas", "Atualizar dados", "Relatório e post"])

a = analyze(cfg, db, current_extractor()) if db.count_jobs() else None

# ------------------------------------------------------------------ Mercado
with tab_market:
    if a is None or a.jobs_df.empty:
        st.info("Ainda não há vagas extraídas. Vá em **Atualizar dados**.")
    else:
        c1, c2, c3 = st.columns(3)
        role = c1.selectbox("Cargo", ["(todos)"] + list(cfg.roles),
                            format_func=lambda r: cfg.roles.get(r, {}).get("label", r) if r != "(todos)" else r)
        region = c2.selectbox("Região", ["(todas)"] + sorted(a.jobs_df["region"].unique()),
                              format_func=lambda r: REGION_PT.get(r, r))
        sens = c3.multiselect("Senioridade", list(SENIORITY_PT), format_func=SENIORITY_PT.get)
        from rota.analysis import market
        j, s = market.filter_frames(a.jobs_df, a.skills_df, role=None if role == "(todos)" else role,
                                    region=None if region == "(todas)" else region, seniorities=sens or None)
        tbl = market.skill_table(j, s)
        m1, m2, m3 = st.columns(3)
        m1.metric("Vagas", len(j))
        m2.metric("Empresas", j["company"].nunique())
        m3.metric("Skills distintas", tbl["skill_id"].nunique())
        if len(j):
            with tempfile.TemporaryDirectory() as td:
                p = chart_top_skills(tbl, Path(td) / "c.png", title="Skills mais pedidas",
                                     subtitle=f"% de {len(j)} vagas que citam cada skill")
                st.image(str(p))
            show = tbl.head(40).assign(**{c: (tbl.head(40)[c] * 100).round(0) for c in
                                          ("share_any", "share_required", "share_nice")})
            st.dataframe(show[["name", "category", "share_any", "share_required", "share_nice", "n_any"]].rename(columns={
                "name": "Skill", "category": "Categoria", "share_any": "% vagas", "share_required": "% obrigatória",
                "share_nice": "% diferencial", "n_any": "nº vagas"}), hide_index=True, use_container_width=True)
            cA, cB = st.columns(2)
            cA.subheader("Senioridade")
            cA.bar_chart(market.distribution(j, "seniority").assign(
                nivel=lambda d: d["seniority"].map(SENIORITY_PT)).set_index("nivel")["n"])
            cB.subheader("Tendências")
            if a.trends.empty:
                cB.caption("Precisa de ≥10 vagas recentes e ≥10 antigas com data de publicação.")
            else:
                cB.dataframe(a.trends.head(10)[["name", "share_recent", "share_older", "delta_pp"]], hide_index=True)
        st.subheader("Brasil × internacional")
        st.dataframe(a.region_cmp.rename(columns=REGION_PT), hide_index=True, use_container_width=True)

# ------------------------------------------------------------------ Perfil e gap
with tab_gap:
    st.subheader("Seu currículo")
    st.caption("O arquivo fica em profile/ (fora do Git). Nome, e-mail, telefone e links são removidos antes de ir ao LLM.")
    up = st.file_uploader("Currículo (.pdf, .docx, .md, .txt)", type=["pdf", "docx", "md", "txt"])
    use_llm = st.checkbox("Usar LLM para avaliar níveis", value=llm_client() is not None)
    if up and st.button("Ler currículo"):
        dest = cfg.paths.profile / up.name
        dest.write_bytes(up.getvalue())
        with st.spinner("Lendo…"):
            prof = build_profile(dest, cfg.paths.profile, client=llm_client() if use_llm else None)
        st.success(f"{len(prof.skills)} skills encontradas ({prof.method}).")

    prof = load_profile(cfg.paths.profile)
    levels = effective_levels(cfg.paths.profile)
    if prof:
        st.subheader("Níveis (edite se algo estiver errado)")
        st.caption("0 = não tenho · 1 = exposição · 2 = usei em projeto/trabalho · 3 = forte")
        df = pd.DataFrame([{"skill_id": s.skill_id, "Skill": s.name, "Nível": levels.get(s.skill_id, s.level),
                            "Evidência": s.evidence or ""} for s in prof.skills])
        if a is not None:
            known = set(df["skill_id"])
            extra = a.focus_table[~a.focus_table["skill_id"].isin(known) & ~a.focus_table["skill_id"].str.startswith("other:")].head(15)
            df = pd.concat([df, pd.DataFrame([{"skill_id": r.skill_id, "Skill": r.name, "Nível": levels.get(r.skill_id, 0),
                                               "Evidência": "(pedida pelo mercado)"} for r in extra.itertuples()])])
        edited = st.data_editor(df, hide_index=True, column_config={
            "skill_id": None, "Nível": st.column_config.NumberColumn(min_value=0, max_value=3, step=1)},
            disabled=["Skill", "Evidência"], use_container_width=True, key="levels")
        if st.button("Salvar níveis"):
            base = prof.levels()
            ov = {r["skill_id"]: int(r["Nível"]) for _, r in edited.iterrows() if base.get(r["skill_id"], 0) != int(r["Nível"])}
            save_overrides(cfg.paths.profile, ov)
            st.success("Salvo em profile/overrides.yaml")
            st.rerun()
    if a is not None and not a.jobs_df.empty and (prof or levels):
        gap = compute_gap(cfg, a)
        st.subheader("Gap em relação ao mercado")
        st.caption(a.focus_note)
        st.metric("Aderência às skills mais pedidas (ponderada)", f"{market_fit(gap):.0%}")
        st.dataframe(gap.assign(Status=gap["status"].map(STATUS_PT), Demanda=(gap["demand"] * 100).round(0))[
            ["name", "Demanda", "level", "Status", "priority", "effort_hours"]].rename(columns={
                "name": "Skill", "level": "Seu nível", "priority": "Prioridade", "effort_hours": "Horas estimadas"}),
            hide_index=True, use_container_width=True)

# ------------------------------------------------------------------ Plano
with tab_plan:
    st.subheader("Focos e pesos")
    f = cfg.focus
    w = f.get("weights", {})
    c1, c2, c3, c4 = st.columns(4)
    hours = c1.number_input("Horas/semana", 1.0, 80.0, float(f.get("weekly_hours", 10)), 0.5)
    wc = c2.slider("Carreira", 0, 100, int(w.get("carreira", 50)))
    we = c3.slider("Exploração", 0, 100, int(w.get("exploracao", 30)))
    wi = c4.slider("Interesses", 0, 100, int(w.get("interesses", 20)))
    topics = st.text_input("Tópicos de exploração (separados por vírgula)", ", ".join(f.get("exploration", {}).get("topics") or []))
    interests = st.text_input("Interesses pessoais (separados por vírgula)", ", ".join(f.get("interests") or []))
    protected = st.checkbox("Proteger horas de exploração", value=bool(f.get("exploration", {}).get("protected", True)))
    if wc + we + wi != 100:
        st.warning(f"Os pesos somam {wc + we + wi}; precisam somar 100.")
    elif st.button("Salvar focos"):
        new = {"weekly_hours": hours, "weights": {"carreira": wc, "exploracao": we, "interesses": wi},
               "exploration": {"protected": protected, "topics": [t.strip() for t in topics.split(",") if t.strip()],
                               "include_emerging": f.get("exploration", {}).get("include_emerging", True)},
               "interests": [t.strip() for t in interests.split(",") if t.strip()]}
        (cfg.paths.config / "focus.yaml").write_text(
            "# Focos e pesos (editado pela interface). Veja o README para o significado de cada campo.\n"
            + yaml.safe_dump(new, allow_unicode=True, sort_keys=False), encoding="utf-8")
        st.success("Focos salvos.")
        st.rerun()

    if a is None or a.jobs_df.empty:
        st.info("O plano precisa de vagas extraídas.")
    else:
        ideas = st.checkbox("Pedir ideias de projetos e pontes ao LLM", value=llm_client() is not None)
        if st.button("Gerar plano", type="primary"):
            with st.spinner("Montando o plano…"):
                plan = make_plan(cfg, a, compute_gap(cfg, a), client=llm_client() if ideas else None)
            st.session_state["plan"] = plan
        plan = st.session_state.get("plan")
        if plan:
            st.markdown(f"**{plan.weekly_hours:g}h/semana** → carreira {plan.hours.get('carreira', 0)}h · "
                        f"exploração {plan.hours.get('exploracao', 0)}h{' (protegida)' if plan.protected_exploration else ''} · "
                        f"interesses {plan.hours.get('interesses', 0)}h")
            st.subheader("Esta semana")
            st.table(pd.DataFrame(plan.this_week).rename(columns={"foco": "Foco", "item": "O quê", "horas": "Horas"}))
            st.subheader("Prioridades de carreira")
            for i, c in enumerate(plan.career, 1):
                st.markdown(f"{i}. **{c.name}** ({STATUS_PT[c.status].lower()}) — {c.why}; ~{c.effort_hours}h"
                            + (f"; costuma vir junto com {', '.join(c.pairs_with)}" if c.pairs_with else ""))
            st.subheader("Projetos sugeridos")
            for p in plan.projects:
                with st.expander(p.title):
                    st.write(p.description)
                    if p.deliverable:
                        st.caption(f"Entrega: {p.deliverable}")
                    st.caption(", ".join(p.skills) + (f" · ponte com {p.bridge_interest}" if p.bridge_interest else ""))
            cA, cB = st.columns(2)
            cA.subheader("Exploração")
            for e in plan.exploration or [{"name": "(adicione tópicos acima)", "why": ""}]:
                cA.markdown(f"- **{e['name']}** — {e['why']}")
            cB.subheader("Interesses e pontes")
            for b in plan.bridges:
                cB.markdown(f"- **{b.interest}** → {b.idea}")
            if not plan.bridges:
                for i in plan.interests:
                    cB.markdown(f"- {i['name']} — {i['horas']}h/semana")
            st.subheader("Trade-offs (você decide)")
            for t in plan.tradeoffs:
                st.markdown(f"- {t}")
            for n in plan.notes:
                st.info(n)

# ------------------------------------------------------------------ Vagas
with tab_jobs:
    jobs = db.jobs()
    if jobs:
        jdf = pd.DataFrame([{"Empresa": j.company, "Título": j.title, "Cargo": cfg.roles.get(j.role, {}).get("label", j.role),
                             "Região": REGION_PT.get(j.region, j.region), "Fonte": j.source, "Publicada": (j.published_at or "")[:10],
                             "Link": j.url} for j in jobs])
        st.dataframe(jdf, hide_index=True, use_container_width=True,
                     column_config={"Link": st.column_config.LinkColumn()})
    st.subheader("Colar uma vaga")
    with st.form("manual"):
        t = st.text_input("Título")
        c = st.text_input("Empresa")
        u = st.text_input("Link (opcional)")
        body = st.text_area("Texto completo da vaga", height=220)
        if st.form_submit_button("Adicionar") and body.strip():
            status, job = add_manual(cfg, db, body, title=t, company=c, url=u)
            st.success(f"{status}: {job.title} → {cfg.roles.get(job.role, {}).get('label', job.role)}. "
                       "Rode a extração em Atualizar dados.")

# ------------------------------------------------------------------ Atualizar
with tab_update:
    st.write("Fontes habilitadas:", ", ".join(k for k, v in cfg.sources.items() if isinstance(v, dict) and v.get("enabled")))
    if st.button("1. Coletar vagas"):
        log = st.empty()
        with st.spinner("Coletando (pode levar alguns minutos)…"):
            stats = collect(cfg, db, progress=lambda m: log.write(m))
        st.success(f"Novas: {stats.new} · já vistas: {stats.seen} · duplicadas: {stats.duplicate}")
        for e in stats.errors:
            st.error(e)
    ex = st.radio("Extrator", ["llm", "baseline"], horizontal=True, index=0 if llm_client() else 1)
    if st.button("2. Extrair skills"):
        client = llm_client() if ex == "llm" else None
        if ex == "llm" and client is None:
            st.error("Configure a chave do LLM no arquivo .env.")
        else:
            bar = st.progress(0.0)
            res = run_extraction(db, db.jobs(), ex, client, progress=lambda i, n, j: bar.progress(i / n, f"{j.company} — {j.title}"))
            st.success(str(res))
            st.rerun()

# ------------------------------------------------------------------ Relatório e post
with tab_post:
    if a is None or a.jobs_df.empty:
        st.info("Gere dados primeiro.")
    else:
        numbers = post_numbers(a.jobs_df, a.tables, cfg.roles)
        st.subheader("Rascunho do post (edite antes de publicar)")
        st.text_area("Post", linkedin_post_draft(numbers), height=360)
        st.subheader("Números")
        st.json(numbers, expanded=False)
        cA, cB = st.columns(2)
        if cA.button("Gerar relatório público (sem dados pessoais)"):
            files = make_report(cfg, a, gap=None, plan=None, model=current_extractor(), public=True)
            st.success(f"Salvo em {files['report'].parent}")
            for k, p in files.items():
                if p.suffix == ".png":
                    st.image(str(p))
        if cB.button("Gerar relatório completo (privado)"):
            gap = compute_gap(cfg, a)
            files = make_report(cfg, a, gap=gap, plan=st.session_state.get("plan"), model=current_extractor())
            st.success(f"Salvo em {files['report']}")
