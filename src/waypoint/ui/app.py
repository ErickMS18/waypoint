"""Waypoint — interface local.

Abra pelo atalho "Waypoint" na Área de Trabalho, ou com `waypoint ui`.
Tudo roda no seu computador; nada daqui vai para o Git.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Optional

import altair as alt
import pandas as pd
import streamlit as st

from waypoint import pipeline as pl
from waypoint import updater
from waypoint.analysis import market
from waypoint.analysis.gap import STATUS_PT, gap_table, market_fit
from waypoint.collect import add_manual, reassign_roles
from waypoint.db import DB
from waypoint.llm import LLMNotConfigured, config_from_env, make_client
from waypoint.models import REGION_PT, SENIORITY_PT
from waypoint.profile import build_profile, effective_levels, load_profile, save_overrides
from waypoint.report import linkedin_post_draft, post_numbers
from waypoint.settings import load_config, make_custom_role, save_local

_ICON = Path(__file__).resolve().parents[3] / "assets" / "waypoint_icon.png"
st.set_page_config(page_title="Waypoint", page_icon=str(_ICON) if _ICON.exists() else "🧭", layout="wide",
                   initial_sidebar_state="expanded")

# ----------------------------------------------------------------------------- look & feel
# Validated categorical palette (fixed order; color follows the role, never its rank).
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
C_REQUIRED, C_NICE = "#2a78d6", "#eb6834"
INK, INK_2, GRID = "#0b0b0b", "#52514e", "#e4e3df"
MIN_ROLE_JOBS = 10  # below this, per-role percentages are too unstable to show as facts

st.markdown("""
<style>
  .block-container {padding-top: 2rem; max-width: 1250px;}
  .wp-hero {font-size: 2.0rem; font-weight: 700; margin-bottom: .1rem;}
  .wp-sub {color: #52514e; margin-bottom: 1.2rem;}
  .wp-pill {display:inline-block; padding:2px 10px; margin:2px 4px 2px 0; border-radius:999px;
            border:1px solid #e4e3df; font-size:.82rem; color:#0b0b0b; background:#fcfcfb;}
  .wp-pill.req {border-color:#2a78d6;} .wp-pill.nice {border-color:#eb6834;}
  .wp-muted {color:#52514e; font-size:.88rem;}
  div[data-testid="stMetricValue"] {font-size: 1.7rem;}
</style>
""", unsafe_allow_html=True)

PAGES = ["🏠 Início", "📊 Mercado", "⚖️ Comparar cargos", "👤 Meu perfil", "🗺️ Plano", "🎯 Cargos", "💼 Vagas",
         "📝 Relatório e post"]

cfg = load_config()
cfg.paths.ensure()
db = DB(cfg.paths.db)


def go(page: str) -> None:
    st.session_state["page"] = page


def role_label(rid: str) -> str:
    return cfg.all_roles.get(rid, {}).get("label", rid)


# Fixed color per role (never by rank), skipping yellow for the catalog roles for contrast on light surfaces.
ROLE_COLORS = {"ai_ml_engineer": SERIES[0], "data_scientist": SERIES[1], "bi_analyst": SERIES[2],
               "analytics_engineer": SERIES[6], "mlops_engineer": SERIES[4], "data_analyst": SERIES[5],
               "data_engineer": SERIES[7]}


def role_color(rid: str) -> str:
    if rid in ROLE_COLORS:
        return ROLE_COLORS[rid]
    custom = [r for r in cfg.all_roles if r not in ROLE_COLORS]
    return SERIES[3] if rid not in custom else [SERIES[3], *SERIES][custom.index(rid) % (len(SERIES) + 1)]


def llm_client():
    try:
        return make_client(db)
    except LLMNotConfigured:
        return None


def llm_label() -> Optional[str]:
    try:
        c = config_from_env()
        return f"{c.provider} · {c.model}"
    except LLMNotConfigured:
        return None


def pills(items: list[str], cls: str = "") -> str:
    return " ".join(f'<span class="wp-pill {cls}">{i}</span>' for i in items)


def pct(x: float) -> str:
    return f"{x:.0%}"


def _stamp() -> tuple:
    files = [*cfg.paths.data.glob("waypoint.db*"), *cfg.paths.config.glob("*.yaml"),
             cfg.paths.profile / "profile.json", cfg.paths.profile / "overrides.yaml"]
    return (str(cfg.paths.root),) + tuple((f.name, f.stat().st_mtime_ns) for f in files if f.exists())


@st.cache_data(show_spinner="Analisando o mercado…", max_entries=4)
def get_analysis(stamp: tuple, extractor: str):
    c = load_config()
    d = DB(c.paths.db)
    try:
        return pl.analyze(c, d, extractor)
    finally:
        d.conn.close()


EXTRACTOR = pl.resolve_extractor(db)
A = get_analysis(_stamp(), EXTRACTOR) if db.count_jobs() else None
HAS_DATA = A is not None and not A.jobs_df.empty
PROFILE = load_profile(cfg.paths.profile)
LEVELS = effective_levels(cfg.paths.profile)


def base_chart(data: pd.DataFrame) -> alt.Chart:
    return alt.Chart(data).configure_axis(labelColor=INK_2, titleColor=INK_2, gridColor=GRID, domainColor=GRID,
                                          labelFontSize=12, titleFontSize=12) \
        .configure_view(strokeWidth=0).configure_legend(labelColor=INK_2, titleColor=INK_2, orient="top")


def skills_chart(tbl: pd.DataFrame, top: int, select: bool = False):
    t = tbl[~tbl["skill_id"].str.startswith("other:")].head(top).copy()
    rows = []
    for r in t.itertuples():
        rows.append({"Skill": r.name, "skill_id": r.skill_id, "Tipo": "Obrigatória", "share": r.share_required,
                     "total": r.share_any, "n": int(r.n_any)})
        rows.append({"Skill": r.name, "skill_id": r.skill_id, "Tipo": "Diferencial", "share": r.share_nice,
                     "total": r.share_any, "n": int(r.n_any)})
    d = pd.DataFrame(rows)
    order = t["name"].tolist()
    sel = alt.selection_point(fields=["skill_id"], name="skill", on="click", empty=True)
    ch = alt.Chart(d).mark_bar(cornerRadiusEnd=4, height={"band": 0.72}, stroke="#fcfcfb", strokeWidth=1).encode(
        y=alt.Y("Skill:N", sort=order, title=None, axis=alt.Axis(labelLimit=220, labelOverlap=False)),
        x=alt.X("share:Q", stack="zero", title="% das vagas que pedem", axis=alt.Axis(format="%", tickCount=5)),
        color=alt.Color("Tipo:N", scale=alt.Scale(domain=["Obrigatória", "Diferencial"], range=[C_REQUIRED, C_NICE]),
                        legend=alt.Legend(title=None)),
        order=alt.Order("Tipo:N", sort="descending"),
        tooltip=[alt.Tooltip("Skill:N"), alt.Tooltip("Tipo:N"), alt.Tooltip("share:Q", format=".0%", title="% vagas"),
                 alt.Tooltip("total:Q", format=".0%", title="% total (obrig.+dif.)"), alt.Tooltip("n:Q", title="nº vagas")],
        opacity=alt.condition(sel, alt.value(1.0), alt.value(0.35)) if select else alt.value(1.0),
    ).properties(height=max(260, 26 * len(order)))
    if select:
        ch = ch.add_params(sel)
    return ch.configure_axis(labelColor=INK_2, titleColor=INK_2, gridColor=GRID, domainColor=GRID, labelFontSize=12) \
        .configure_view(strokeWidth=0).configure_legend(labelColor=INK_2, orient="top")


def jobs_asking(skill_id: str, jobs_df: pd.DataFrame, skills_df: pd.DataFrame) -> pd.DataFrame:
    s = skills_df[skills_df["skill_id"] == skill_id][["job_key", "requirement"]].drop_duplicates("job_key")
    j = jobs_df.merge(s, on="job_key")
    return pd.DataFrame({
        "Empresa": j["company"], "Título": j["title"], "Cargo": j["role"].map(role_label),
        "Como pede": j["requirement"].map({"required": "Obrigatória", "nice_to_have": "Diferencial"}),
        "Região": j["region"].map(lambda r: REGION_PT.get(r, r)), "Link": j["url"]})


# ============================================================================= sidebar
def _update_panel_body() -> None:
    s = updater.read_status(cfg)
    if s.get("state") == "running":
        st.session_state["_was_running"] = True
        st.progress(min(max(float(s.get("frac") or 0), 0.0), 1.0), text=s.get("msg") or "Atualizando…")
        st.caption(f"Começou {s.get('started', '')}. Pode fechar o navegador: a atualização continua sozinha.")
        return
    if st.session_state.pop("_was_running", False):
        st.cache_data.clear()
        st.rerun(scope="app")
    st.caption(f"Última atualização: **{pl.last_update(cfg) or 'nunca'}**")
    if s.get("state") == "failed":
        st.error(f"A última atualização falhou: {s.get('error')}. Detalhes em data/logs/update.log.")
    elif s.get("state") == "done" and (s.get("result") or {}).get("aviso"):
        st.caption(s["result"]["aviso"])
    if st.button("🔄 Atualizar tudo", type="primary", width="stretch",
                 help="Coleta vagas novas, extrai as skills, refaz o plano e os relatórios. Roda em segundo plano."):
        updater.start_background_update(cfg)
        st.rerun(scope="app")


def update_panel() -> None:
    running = updater.is_running(cfg)
    st.fragment(_update_panel_body, run_every=2 if running else None)()


def shutdown() -> None:
    threading.Timer(1.0, lambda: os._exit(0)).start()


with st.sidebar:
    st.markdown("### 🧭 Waypoint")
    st.caption("Seu radar de carreira em IA e dados")
    if "page" not in st.session_state:
        st.session_state["page"] = PAGES[0]
    st.radio("Navegação", PAGES, key="page", label_visibility="collapsed")
    st.divider()
    update_panel()
    st.divider()
    n_jobs = len(A.jobs_df) if HAS_DATA else 0
    st.caption(f"{n_jobs} vagas analisadas · {len(cfg.roles)} cargos ativos")
    st.caption(f"IA: {llm_label() or 'sem chave (usando dicionário)'}")
    with st.expander("Opções"):
        s = updater.load_ui_settings(cfg)
        auto = st.toggle("Atualizar sozinho ao abrir pelo atalho", value=bool(s["auto_update_on_open"]),
                         help="Se a última atualização tiver mais de ~1 dia.")
        if auto != s["auto_update_on_open"]:
            updater.save_ui_settings(cfg, auto_update_on_open=auto)
        if st.button("⏻ Encerrar Waypoint", width="stretch",
                     help="Desliga a interface. Para abrir de novo, use o atalho."):
            st.success("Waypoint encerrado. Pode fechar esta aba.")
            shutdown()

page = st.session_state["page"]


# ============================================================================= pages
def page_home() -> None:
    st.markdown('<div class="wp-hero">Olá! Este é o seu radar de carreira.</div>', unsafe_allow_html=True)
    st.markdown('<div class="wp-sub">O que o mercado está pedindo, onde você está e o que estudar nesta semana.</div>',
                unsafe_allow_html=True)

    steps = [("Chave de IA no arquivo .env", llm_label() is not None,
              "Opcional, mas melhora muito a leitura das vagas. Crie uma chave gratuita do Gemini em "
              "aistudio.google.com e coloque `GEMINI_API_KEY=...` no arquivo `.env` da pasta do Waypoint."),
             ("Seu currículo", PROFILE is not None, "Envie em **👤 Meu perfil**. Fica só no seu computador."),
             ("Primeira atualização", HAS_DATA, "Clique em **🔄 Atualizar tudo** na barra lateral (leva alguns minutos).")]
    if not all(ok for _, ok, _ in steps):
        with st.container(border=True):
            st.subheader("Primeiros passos")
            for title, ok, how in steps:
                st.markdown(f"{'✅' if ok else '⬜'} **{title}**" + ("" if ok else f" — {how}"))
            if PROFILE is None:
                st.button("Enviar meu currículo", on_click=go, args=(PAGES[3],))
    if not HAS_DATA:
        st.info("Ainda não há vagas analisadas. Clique em **🔄 Atualizar tudo** na barra lateral.")
        return

    gap = pl.compute_gap(cfg, A)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Vagas analisadas", len(A.jobs_df))
    k2.metric("Empresas", A.jobs_df["company"].nunique())
    k3.metric("Cargos ativos", len(cfg.roles))
    k4.metric("Sua aderência", pct(market_fit(gap)) if LEVELS else "—",
              help="Quanto das skills mais pedidas (ponderadas pela demanda) você já cobre. Nível 2 = cobre.")

    left, right = st.columns([1.15, 1])
    with left:
        with st.container(border=True):
            st.subheader("🎯 Missão da semana")
            plan = pl.load_plan(cfg)
            if plan is None:
                st.caption("Você ainda não gerou um plano.")
                if st.button("Gerar meu plano agora", type="primary"):
                    with st.spinner("Montando o plano…"):
                        pl.save_plan(cfg, pl.make_plan(cfg, A, gap, client=llm_client()))
                    st.rerun()
            else:
                render_week(plan, key_prefix="home")
                st.button("Ver plano completo", on_click=go, args=(PAGES[4],))
    with right:
        with st.container(border=True):
            st.subheader("Onde você está em cada cargo")
            if not LEVELS:
                st.caption("Envie seu currículo para ver a aderência por cargo.")
            else:
                render_role_fit()
        with st.container(border=True):
            st.subheader("Maiores lacunas")
            top = gap[gap["status"] != "has"].sort_values("priority", ascending=False).head(5)
            for r in top.itertuples():
                st.markdown(f"**{r.name}** · pedida em {r.share_any:.0%} das vagas · "
                            f"você: {STATUS_PT[r.status].lower()} · ~{r.effort_hours}h")
            if top.empty:
                st.caption("Você já cobre as skills mais pedidas. 🎉")

    if not A.trends.empty:
        with st.container(border=True):
            st.subheader("📈 Em alta nas vagas recentes")
            up = A.trends[A.trends["delta_pp"] > 0].head(5)
            st.markdown(" ".join(f'<span class="wp-pill">{r.name} +{r.delta_pp:.0f} p.p.</span>' for r in up.itertuples()),
                        unsafe_allow_html=True)


def render_role_fit() -> None:
    fit = pl.role_fit(cfg, A)
    d = pd.DataFrame([{"Cargo": role_label(r), "rid": r, "Aderência": v,
                       "Vagas": int((A.jobs_df["role"] == r).sum())} for r, v in fit.items()],
                     columns=["Cargo", "rid", "Aderência", "Vagas"])
    few = d[d["Vagas"] < MIN_ROLE_JOBS]
    d = d[d["Vagas"] >= MIN_ROLE_JOBS].sort_values("Aderência", ascending=False)
    if d.empty:
        st.caption("Ainda há poucas vagas por cargo. Atualize para coletar mais.")
    else:
        ch = alt.Chart(d).mark_bar(cornerRadiusEnd=4, color=C_REQUIRED, height={"band": 0.65}).encode(
            y=alt.Y("Cargo:N", sort="-x", title=None, axis=alt.Axis(labelLimit=200)),
            x=alt.X("Aderência:Q", axis=alt.Axis(format="%", tickCount=5), scale=alt.Scale(domain=[0, 1.1]), title=None),
            tooltip=["Cargo", alt.Tooltip("Aderência:Q", format=".0%"), "Vagas"]).properties(height=46 * len(d))
        text = ch.mark_text(align="left", dx=4, color=INK).encode(text=alt.Text("Aderência:Q", format=".0%"))
        st.altair_chart((ch + text).configure_axis(labelColor=INK_2, gridColor=GRID, domainColor=GRID)
                        .configure_view(strokeWidth=0), width="stretch", height=46 * len(d) + 40)
        best = d.iloc[0]
        st.caption(f"Mais perto hoje: **{best['Cargo']}** ({best['Aderência']:.0%}).")
    if len(few):
        st.caption("Poucas vagas ainda (menos de %d): %s. Atualize para coletar mais."
                   % (MIN_ROLE_JOBS, ", ".join(f"{r.Cargo} ({r.Vagas})" for r in few.itertuples())))


def render_week(plan: dict[str, Any], key_prefix: str) -> None:
    done = pl.load_done(cfg)
    items = plan.get("this_week") or []
    total = sum(float(i.get("horas") or 0) for i in items) or 1.0
    got = sum(float(i.get("horas") or 0) for i in items if f"{i['foco']}:{i['item']}" in done)
    st.progress(min(got / total, 1.0), text=f"{got:g}h de {total:g}h feitas nesta semana")
    icon = {"carreira": "💼", "exploração": "🧪", "interesses": "🎸"}
    for i, it in enumerate(items):
        iid = f"{it['foco']}:{it['item']}"
        val = st.checkbox(f"{icon.get(it['foco'], '•')} **{it['item']}** — {it['horas']:g}h ({it['foco']})",
                          value=iid in done, key=f"{key_prefix}_wk_{i}")
        if val != (iid in done):
            pl.set_done(cfg, iid, val)
            st.rerun()
    st.caption("As marcações recomeçam toda segunda-feira.")


def page_market() -> None:
    st.header("📊 Mercado")
    if not HAS_DATA:
        st.info("Ainda não há vagas analisadas. Clique em **🔄 Atualizar tudo** na barra lateral.")
        return
    opts = ["Todos"] + list(cfg.roles)
    role = st.pills("Cargo", opts, default="Todos", format_func=lambda r: r if r == "Todos" else role_label(r),
                    key="mk_role") or "Todos"
    if role != "Todos":
        r = cfg.roles[role]
        st.markdown(f'<span class="wp-muted">{r.get("summary", "")}</span>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 1.4, 1])
    regions = sorted(A.jobs_df["region"].dropna().unique())
    region = c1.selectbox("Região", ["(todas)"] + regions, format_func=lambda x: REGION_PT.get(x, x))
    sens = c2.multiselect("Senioridade", list(SENIORITY_PT), format_func=SENIORITY_PT.get, placeholder="todas")
    top = c3.slider("Quantas skills mostrar", 10, 40, 20)
    j, s = market.filter_frames(A.jobs_df, A.skills_df, role=None if role == "Todos" else role,
                                region=None if region == "(todas)" else region, seniorities=sens or None)
    tbl = market.skill_table(j, s)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Vagas", len(j))
    m2.metric("Empresas", j["company"].nunique())
    m3.metric("Skills distintas", tbl["skill_id"].nunique())
    m4.metric("Remoto", pct((j["work_model"] == "remote").mean()) if len(j) else "—")
    if len(j) == 0:
        st.warning("Nenhuma vaga com esses filtros.")
        return
    st.subheader("Skills mais pedidas")
    st.caption("Clique numa barra para ver as vagas que pedem aquela skill. Azul = obrigatória, laranja = diferencial.")
    n_rows = len(tbl[~tbl["skill_id"].str.startswith("other:")].head(top))
    ev = st.altair_chart(skills_chart(tbl, top, select=True), width="stretch", on_select="rerun",
                         height=max(260, 26 * n_rows) + 70,
                         key=f"mk_chart_{role}_{region}_{'-'.join(sens)}_{top}")
    picked = None
    try:
        sel = (ev or {}).get("selection", {}).get("skill") or []
        picked = sel[0].get("skill_id") if sel else None
    except (AttributeError, IndexError, TypeError):
        picked = None
    names = dict(zip(tbl["skill_id"], tbl["name"]))
    ids = [i for i in tbl["skill_id"] if not i.startswith("other:")][:top]
    picked = st.selectbox("Ver vagas que pedem", ids, index=ids.index(picked) if picked in ids else 0,
                          format_func=names.get)
    if picked:
        rows = jobs_asking(picked, j, s)
        st.dataframe(rows, hide_index=True, width="stretch", height=min(38 * (len(rows) + 1), 320),
                     column_config={"Link": st.column_config.LinkColumn(display_text="abrir")})
        pairs = market.cooccurrence(s, picked, top=5)
        if pairs:
            st.caption(f"Costuma vir junto com: {', '.join(pairs)}")

    cA, cB = st.columns(2)
    with cA:
        st.subheader("Senioridade")
        d = market.distribution(j, "seniority")
        d["Nível"] = d["seniority"].map(lambda x: SENIORITY_PT.get(x, "não informado"))
        ch = alt.Chart(d).mark_bar(cornerRadiusEnd=4, color=C_REQUIRED).encode(
            y=alt.Y("Nível:N", sort=[SENIORITY_PT[k] for k in SENIORITY_PT] + ["não informado"], title=None),
            x=alt.X("n:Q", title="vagas"),
            tooltip=["Nível", alt.Tooltip("n:Q", title="vagas"), alt.Tooltip("share:Q", format=".0%", title="%")])
        st.altair_chart(ch.configure_axis(labelColor=INK_2, gridColor=GRID, domainColor=GRID).configure_view(strokeWidth=0),
                        width="stretch")
    with cB:
        st.subheader("Tendências")
        if A.trends.empty:
            st.caption("Precisa de pelo menos 10 vagas recentes e 10 antigas com data de publicação. "
                       "Conforme você atualiza ao longo das semanas, isto aparece.")
        else:
            t = A.trends.head(10)
            st.dataframe(pd.DataFrame({"Skill": t["name"], "Recentes": (t["share_recent"] * 100).round(0),
                                       "Antigas": (t["share_older"] * 100).round(0), "Δ p.p.": t["delta_pp"].round(1)}),
                         hide_index=True, width="stretch")
    with st.expander("Brasil × internacional"):
        rc = A.region_cmp
        show = rc[["name"] + [c for c in rc.columns if c in REGION_PT]].rename(columns={"name": "Skill", **REGION_PT})
        st.dataframe(show.style.format({c: "{:.0%}" for c in show.columns if c != "Skill"}), hide_index=True,
                     width="stretch")
    with st.expander("Tabela completa"):
        st.dataframe(pd.DataFrame({"Skill": tbl["name"], "Categoria": tbl["category"],
                                   "% vagas": (tbl["share_any"] * 100).round(0),
                                   "% obrigatória": (tbl["share_required"] * 100).round(0),
                                   "% diferencial": (tbl["share_nice"] * 100).round(0), "nº vagas": tbl["n_any"]}),
                     hide_index=True, width="stretch")


def page_compare() -> None:
    st.header("⚖️ Comparar cargos")
    if not HAS_DATA:
        st.info("Ainda não há vagas analisadas.")
        return
    counts = A.jobs_df["role"].value_counts()
    with_data = sorted([r for r in cfg.roles if counts.get(r, 0)], key=lambda r: -counts[r])
    if len(with_data) < 2:
        st.info("Precisa de vagas de pelo menos dois cargos. Ative mais cargos em **🎯 Cargos** e atualize.")
        return
    chosen = st.multiselect("Cargos (até 3)", with_data, default=with_data[:3], max_selections=3, format_func=role_label,
                            placeholder="Escolha os cargos")
    if len(chosen) < 2:
        st.caption("Escolha pelo menos dois.")
        return
    tables = {r: A.tables[r] for r in chosen}
    cols = st.columns(len(chosen))
    for c, r in zip(cols, chosen):
        jr = A.jobs_df[A.jobs_df["role"] == r]
        with c.container(border=True):
            st.markdown(f"<span style='color:{role_color(r)};font-size:1.2rem'>■</span> **{role_label(r)}**",
                        unsafe_allow_html=True)
            st.caption(cfg.all_roles[r].get("summary", ""))
            if len(jr) < MIN_ROLE_JOBS:
                st.warning(f"Só {len(jr)} vaga(s): os números deste cargo ainda são instáveis.", icon="⚠️")
            a1, a2 = st.columns(2)
            a1.metric("Vagas", len(jr))
            entry = jr["seniority"].isin(["intern", "junior"]).mean() if len(jr) else 0
            a2.metric("Estágio/júnior", pct(entry))
            if LEVELS:
                st.metric("Sua aderência", pct(market_fit(gap_table(tables[r], LEVELS))))
            others = set().union(*[set(tables[o]["skill_id"].head(25)) for o in chosen if o != r])
            own = tables[r][~tables[r]["skill_id"].isin(others) & ~tables[r]["skill_id"].str.startswith("other:")].head(5)
            st.markdown("**Mais típicas deste cargo:**<br>" + pills(own["name"].tolist()), unsafe_allow_html=True)

    union: list[str] = []
    names: dict[str, str] = {}
    for r in chosen:
        t = tables[r][~tables[r]["skill_id"].str.startswith("other:")]
        names.update(zip(t["skill_id"], t["name"]))
        for sid in t["skill_id"].head(10):
            if sid not in union:
                union.append(sid)
    rows = []
    for r in chosen:
        share = tables[r].set_index("skill_id")["share_any"]
        for sid in union:
            rows.append({"Cargo": role_label(r), "Skill": names[sid], "share": float(share.get(sid, 0.0))})
    d = pd.DataFrame(rows)
    order = d.groupby("Skill")["share"].max().sort_values(ascending=False).index.tolist()
    st.subheader("Mesmas skills, cargos diferentes")
    st.caption("Cada ponto é a % das vagas daquele cargo que citam a skill. Quanto mais longe os pontos, "
               "mais a skill diferencia os cargos.")
    labels = [role_label(r) for r in chosen]
    enc_y = alt.Y("Skill:N", sort=order, title=None, axis=alt.Axis(labelLimit=220, labelOverlap=False))
    rng = alt.Chart(d).mark_rule(color=GRID, strokeWidth=2).encode(
        y=enc_y, x=alt.X("min(share):Q", title="% das vagas", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
        x2="max(share):Q")
    dots = alt.Chart(d).mark_point(filled=True, size=110, opacity=1, stroke="#fcfcfb", strokeWidth=2).encode(
        y=enc_y, x="share:Q",
        color=alt.Color("Cargo:N", scale=alt.Scale(domain=labels, range=[role_color(r) for r in chosen]),
                        legend=alt.Legend(title=None, labelLimit=320)),
        tooltip=["Cargo", "Skill", alt.Tooltip("share:Q", format=".0%", title="% vagas")])
    h = 28 * len(order) + 20
    st.altair_chart((rng + dots).properties(height=h).configure_axis(labelColor=INK_2, gridColor=GRID, domainColor=GRID)
                    .configure_view(strokeWidth=0).configure_legend(labelColor=INK_2, orient="top"),
                    width="stretch", height=h + 70)
    with st.expander("Ver como tabela"):
        wide = d.pivot_table(index="Skill", columns="Cargo", values="share").reindex(order)
        st.dataframe(wide.style.format("{:.0%}"), width="stretch")


def page_profile() -> None:
    st.header("👤 Meu perfil")
    with st.container(border=True):
        st.subheader("Currículo")
        st.caption("O arquivo fica em profile/ (fora do Git). Nome, e-mail, telefone, links e CPF são removidos "
                   "antes de qualquer envio à IA.")
        c1, c2 = st.columns([2, 1])
        up = c1.file_uploader("Currículo (.pdf, .docx, .md, .txt)", type=["pdf", "docx", "md", "txt"])
        use_llm = c2.checkbox("Usar IA para avaliar os níveis", value=llm_client() is not None)
        if PROFILE:
            c2.caption(f"Perfil atual: {len(PROFILE.skills)} skills ({PROFILE.method}).")
        if up and c2.button("Ler currículo", type="primary"):
            dest = cfg.paths.profile / up.name
            dest.write_bytes(up.getvalue())
            with st.spinner("Lendo o currículo…"):
                prof = build_profile(dest, cfg.paths.profile, client=llm_client() if use_llm else None)
            st.success(f"{len(prof.skills)} skills encontradas ({prof.method}).")
            st.rerun()

    if HAS_DATA and LEVELS:
        st.subheader("Aderência e lacunas")
        opts = ["foco"] + [r for r in cfg.roles if len(A.tables.get(r, []))]
        which = st.pills("Comparar com", opts, default="foco", key="pf_role",
                         format_func=lambda r: "Todos os cargos (seu nível-alvo)" if r == "foco" else role_label(r)) or "foco"
        tbl = A.focus_table if which == "foco" else A.tables[which]
        gap = gap_table(tbl, LEVELS)
        a1, a2, a3 = st.columns(3)
        a1.metric("Aderência", pct(market_fit(gap)))
        a2.metric("Skills que você já cobre", int((gap["status"] == "has").sum()), help="Entre as 40 mais pedidas.")
        a3.metric("Lacunas", int((gap["status"] != "has").sum()))
        if which == "foco":
            st.caption(A.focus_note)
        st.dataframe(pd.DataFrame({
            "Skill": gap["name"], "Pedida em": (gap["share_any"] * 100).round(0).astype(int).astype(str) + "%",
            "Seu nível": gap["level"], "Status": gap["status"].map(STATUS_PT),
            "Prioridade": gap["priority"].round(3), "Horas estimadas": gap["effort_hours"]}),
            hide_index=True, width="stretch", height=380,
            column_config={"Prioridade": st.column_config.ProgressColumn(min_value=0, max_value=float(max(gap["priority"].max(), 0.01)), format="%.2f")})

    if PROFILE:
        st.subheader("Seus níveis")
        st.caption("Corrija o que a leitura do currículo errou. 0 = não tenho · 1 = já vi/estudei · "
                   "2 = usei em projeto ou trabalho · 3 = domino")
        df = pd.DataFrame([{"skill_id": s.skill_id, "Skill": s.name, "Nível": LEVELS.get(s.skill_id, s.level),
                            "Evidência": s.evidence or ""} for s in PROFILE.skills])
        if HAS_DATA:
            known = set(df["skill_id"])
            extra = A.focus_table[~A.focus_table["skill_id"].isin(known)
                                  & ~A.focus_table["skill_id"].str.startswith("other:")].head(15)
            df = pd.concat([df, pd.DataFrame([{"skill_id": r.skill_id, "Skill": r.name, "Nível": LEVELS.get(r.skill_id, 0),
                                               "Evidência": "(pedida pelo mercado)"} for r in extra.itertuples()])])
        edited = st.data_editor(df, hide_index=True, width="stretch", key="levels", column_config={
            "skill_id": None, "Nível": st.column_config.NumberColumn(min_value=0, max_value=3, step=1)},
            disabled=["Skill", "Evidência"])
        if st.button("Salvar níveis"):
            base = PROFILE.levels()
            ov = {r["skill_id"]: int(r["Nível"]) for _, r in edited.iterrows() if base.get(r["skill_id"], 0) != int(r["Nível"])}
            save_overrides(cfg.paths.profile, ov)
            st.success("Salvo em profile/overrides.yaml (fora do Git).")
            st.rerun()


def page_plan() -> None:
    st.header("🗺️ Plano de estudos")
    f = cfg.focus
    w = f.get("weights", {})
    with st.expander("Focos e pesos", expanded=pl.load_plan(cfg) is None):
        st.caption("Os pesos dividem suas horas. A exploração é protegida: o plano nunca a corta para encaixar carreira.")
        c1, c2, c3, c4 = st.columns(4)
        hours = c1.number_input("Horas por semana", 1.0, 80.0, float(f.get("weekly_hours", 10)), 0.5)
        wc = c2.slider("Carreira", 0, 100, int(w.get("carreira", 50)))
        we = c3.slider("Exploração", 0, 100, int(w.get("exploracao", 30)))
        wi = c4.slider("Interesses", 0, 100, int(w.get("interesses", 20)))
        topics = st.text_input("O que você quer explorar (vírgulas)", ", ".join(f.get("exploration", {}).get("topics") or []))
        interests = st.text_input("Interesses pessoais (vírgulas)", ", ".join(f.get("interests") or []),
                                  help="Ex.: violão, astrologia. O plano procura pontes entre eles e a carreira.")
        protected = st.checkbox("Proteger as horas de exploração", value=bool(f.get("exploration", {}).get("protected", True)))
        if wc + we + wi != 100:
            st.warning(f"Os pesos somam {wc + we + wi}; precisam somar 100.")
        elif st.button("Salvar focos"):
            save_local(cfg.paths.config, "focus", {
                "weekly_hours": hours, "weights": {"carreira": wc, "exploracao": we, "interesses": wi},
                "exploration": {"protected": protected, "topics": [t.strip() for t in topics.split(",") if t.strip()],
                                "include_emerging": f.get("exploration", {}).get("include_emerging", True)},
                "interests": [t.strip() for t in interests.split(",") if t.strip()]})
            st.success("Focos salvos (config/focus.local.yaml, fora do Git). Gere o plano de novo para aplicar.")

    if not HAS_DATA:
        st.info("O plano precisa de vagas analisadas. Clique em **🔄 Atualizar tudo**.")
        return
    c1, c2 = st.columns([1, 2])
    ideas = c2.checkbox("Pedir ideias de projetos e pontes à IA", value=llm_client() is not None)
    if c1.button("Gerar plano", type="primary"):
        with st.spinner("Montando o plano…"):
            pl.save_plan(cfg, pl.make_plan(cfg, A, pl.compute_gap(cfg, A), client=llm_client() if ideas else None))
        st.rerun()
    plan = pl.load_plan(cfg)
    if plan is None:
        st.caption("Clique em **Gerar plano**.")
        return
    h = plan.get("hours", {})
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Horas/semana", f"{plan.get('weekly_hours', 0):g}h")
    m2.metric("💼 Carreira", f"{h.get('carreira', 0):g}h")
    m3.metric("🧪 Exploração", f"{h.get('exploracao', 0):g}h", "protegida" if plan.get("protected_exploration") else None,
              delta_color="off")
    m4.metric("🎸 Interesses", f"{h.get('interesses', 0):g}h")
    st.caption(f"Gerado em {str(plan.get('generated_at', ''))[:16].replace('T', ' ')}. "
               "O plano é refeito a cada atualização.")

    with st.container(border=True):
        st.subheader("Esta semana")
        render_week(plan, key_prefix="plan")

    st.subheader("Prioridades de carreira")
    st.caption("Ordem = quanto o mercado pede × quanto falta para você.")
    career = plan.get("career") or []
    for row in range(0, len(career), 3):
        cols = st.columns(3)
        for c, item in zip(cols, career[row:row + 3]):
            with c.container(border=True):
                st.markdown(f"**{item['name']}**")
                st.caption(f"Você: {STATUS_PT.get(item['status'], item['status']).lower()} · ~{item['effort_hours']}h de estudo")
                st.write(item["why"])
                if item.get("pairs_with"):
                    st.caption("Vem junto com: " + ", ".join(item["pairs_with"]))

    if plan.get("projects"):
        st.subheader("Projetos sugeridos")
        st.caption("Um projeto bem feito cobre várias lacunas de uma vez e vira portfólio.")
        for p in plan["projects"]:
            with st.expander(p["title"]):
                st.write(p["description"])
                if p.get("deliverable"):
                    st.markdown(f"**Entrega:** {p['deliverable']}")
                st.markdown(pills(p.get("skills") or []), unsafe_allow_html=True)
                if p.get("bridge_interest"):
                    st.caption(f"Ponte com: {p['bridge_interest']}")
    cA, cB = st.columns(2)
    with cA.container(border=True):
        st.subheader("🧪 Exploração")
        for e in plan.get("exploration") or [{"name": "Adicione tópicos em Focos e pesos", "why": ""}]:
            st.markdown(f"- **{e['name']}**" + (f" — {e['why']}" if e.get("why") else ""))
    with cB.container(border=True):
        st.subheader("🎸 Interesses e pontes")
        for b in plan.get("bridges") or []:
            st.markdown(f"- **{b['interest']}** → {b['idea']}")
        if not plan.get("bridges"):
            for i in plan.get("interests") or []:
                st.markdown(f"- {i['name']} — {i['horas']:g}h/semana")
            if not plan.get("interests"):
                st.caption("Adicione interesses em Focos e pesos.")
    if plan.get("tradeoffs"):
        with st.container(border=True):
            st.subheader("⚖️ Trade-offs (você decide)")
            for t in plan["tradeoffs"]:
                st.markdown(f"- {t}")
    for n in plan.get("notes") or []:
        st.info(n)


def page_roles() -> None:
    st.header("🎯 Cargos")
    st.caption("Ligue os cargos que quer acompanhar. Desligar um cargo só esconde as vagas dele: nada é apagado. "
               "Depois de ligar um cargo novo, clique em **🔄 Atualizar tudo** para buscar vagas dele.")
    counts = pd.Series([j.role for j in db.jobs()]).value_counts().to_dict() if db.count_jobs() else {}
    enabled_now = set(cfg.roles)
    custom = dict(cfg.targets.get("custom_roles") or {})
    for rid, r in cfg.all_roles.items():
        with st.container(border=True):
            c1, c2 = st.columns([5, 1])
            with c1:
                st.markdown(f"<span style='color:{role_color(rid)};font-size:1.1rem'>■</span> "
                            f"**{r.get('label', rid)}** <span class='wp-muted'>· {counts.get(rid, 0)} vagas no banco</span>",
                            unsafe_allow_html=True)
                st.caption(r.get("summary", ""))
            c2.toggle("Ativo", value=rid in enabled_now, key=f"role_on_{rid}")
            with st.expander("O que esse profissional faz"):
                st.write(r.get("description", ""))
                if r.get("day_to_day"):
                    st.markdown("**No dia a dia:**\n" + "\n".join(f"- {d}" for d in r["day_to_day"]))
                if r.get("typical_skills"):
                    st.markdown("**Skills típicas:** " + pills(r["typical_skills"]), unsafe_allow_html=True)
                st.caption("Busca por: " + ", ".join(r.get("search_terms") or []))
                if rid in custom and st.button("Remover este cargo personalizado", key=f"rm_{rid}"):
                    custom.pop(rid)
                    save_local(cfg.paths.config, "targets", {"custom_roles": custom,
                                                             "roles_enabled": [x for x in cfg.roles if x != rid]})
                    st.rerun()
    if st.button("Salvar cargos", type="primary"):
        chosen = [rid for rid in cfg.all_roles if st.session_state.get(f"role_on_{rid}")]
        if not chosen:
            st.error("Deixe pelo menos um cargo ativo.")
        else:
            save_local(cfg.paths.config, "targets", {"roles_enabled": chosen})
            n = reassign_roles(load_config(), db)
            st.success(f"Cargos salvos ({len(chosen)} ativos). {n} vagas reclassificadas. "
                       "Clique em 🔄 Atualizar tudo para buscar vagas dos cargos novos.")
            st.cache_data.clear()
    with st.container(border=True):
        st.subheader("Criar um cargo personalizado")
        st.caption("Ex.: Prompt Engineer, Quant Analyst. O Waypoint procura vagas cujo título tenha essas palavras.")
        with st.form("new_role", clear_on_submit=True):
            name = st.text_input("Nome do cargo")
            if st.form_submit_button("Adicionar cargo") and name.strip():
                rid, role = make_custom_role(name)
                custom[rid] = role
                save_local(cfg.paths.config, "targets", {"custom_roles": custom, "roles_enabled": [*cfg.roles, rid]})
                st.success(f"Cargo '{name}' criado e ativado. Clique em 🔄 Atualizar tudo para buscar vagas.")
                st.rerun()


def page_jobs() -> None:
    st.header("💼 Vagas")
    if not HAS_DATA:
        st.info("Ainda não há vagas analisadas.")
    else:
        j, s = A.jobs_df, A.skills_df
        c1, c2, c3, c4 = st.columns([1.6, 1.2, 1, 1])
        q = c1.text_input("Buscar no título ou empresa", placeholder="ex.: júnior, Nubank, LLM")
        roles = c2.multiselect("Cargo", list(cfg.roles), format_func=role_label, placeholder="todos")
        region = c3.selectbox("Região", ["(todas)"] + sorted(j["region"].dropna().unique()),
                              format_func=lambda x: REGION_PT.get(x, x), key="jb_region")
        sens = c4.multiselect("Senioridade", list(SENIORITY_PT), format_func=SENIORITY_PT.get, placeholder="todas",
                              key="jb_sen")
        tax_names = s[~s["skill_id"].str.startswith("other:")].drop_duplicates("skill_id").set_index("skill_id")["name"]
        need = st.multiselect("Que pedem as skills", tax_names.index.tolist(), format_func=tax_names.get,
                              placeholder="qualquer")
        m = pd.Series(True, index=j.index)
        if q:
            m &= j["title"].str.contains(q, case=False, regex=False) | j["company"].str.contains(q, case=False, regex=False)
        if roles:
            m &= j["role"].isin(roles)
        if region != "(todas)":
            m &= j["region"] == region
        if sens:
            m &= j["seniority"].isin(sens)
        for sid in need:
            m &= j["job_key"].isin(s.loc[s["skill_id"] == sid, "job_key"])
        jj = j[m].sort_values("published_at", ascending=False, na_position="last").reset_index(drop=True)
        st.caption(f"{len(jj)} vagas · clique numa linha para ver os detalhes")
        view = pd.DataFrame({
            "Empresa": jj["company"], "Título": jj["title"], "Cargo": jj["role"].map(role_label),
            "Nível": jj["seniority"].map(lambda x: SENIORITY_PT.get(x, "—")),
            "Região": jj["region"].map(lambda r: REGION_PT.get(r, r)),
            "Publicada": jj["published_at"].dt.strftime("%d/%m/%Y").fillna("—"), "Link": jj["url"]})
        ev = st.dataframe(view, hide_index=True, width="stretch", height=380, on_select="rerun",
                          selection_mode="single-row", key="jobs_table",
                          column_config={"Link": st.column_config.LinkColumn(display_text="abrir")})
        rows = (ev or {}).get("selection", {}).get("rows", []) if ev else []
        if rows and rows[0] < len(jj):
            job_row = jj.iloc[rows[0]]
            job = db.job(job_row["job_key"])
            js = s[s["job_key"] == job_row["job_key"]]
            with st.container(border=True):
                st.subheader(f"{job_row['title']} — {job_row['company']}")
                st.caption(f"{role_label(job_row['role'])} · {SENIORITY_PT.get(job_row['seniority'], 'nível não informado')} · "
                           f"{REGION_PT.get(job_row['region'], job_row['region'])} · fonte: {job_row['source']}")
                req = js[js["requirement"] == "required"]["name"].tolist()
                nice = js[js["requirement"] == "nice_to_have"]["name"].tolist()
                if req:
                    st.markdown("**Obrigatórias:** " + pills(req, "req"), unsafe_allow_html=True)
                if nice:
                    st.markdown("**Diferenciais:** " + pills(nice, "nice"), unsafe_allow_html=True)
                if LEVELS:
                    miss = [n for sid, n in zip(js["skill_id"], js["name"])
                            if not sid.startswith("other:") and LEVELS.get(sid, 0) < 2]
                    st.caption("Você ainda não cobre: " + (", ".join(miss) if miss else "nada — candidate-se! 🚀"))
                if job_row["url"]:
                    st.link_button("Abrir a vaga", job_row["url"])
                if job:
                    with st.expander("Texto completo"):
                        st.text(job.text[:8000])
    with st.expander("➕ Colar uma vaga manualmente (ex.: do LinkedIn ou InfoJobs)"):
        with st.form("manual", clear_on_submit=True):
            c1, c2 = st.columns(2)
            t = c1.text_input("Título")
            c = c2.text_input("Empresa")
            u = st.text_input("Link (opcional)")
            body = st.text_area("Texto completo da vaga", height=200)
            if st.form_submit_button("Adicionar") and body.strip():
                status, job = add_manual(cfg, db, body, title=t, company=c, url=u)
                st.success(f"Vaga adicionada ({status}): {job.title}. Ela entra na análise na próxima atualização.")


def page_report() -> None:
    st.header("📝 Relatório e post")
    if not HAS_DATA:
        st.info("Gere dados primeiro.")
        return
    numbers = post_numbers(A.jobs_df, A.tables, cfg.roles)
    st.caption("Rascunho com números reais do seu banco. Revise antes de publicar.")
    st.text_area("Post", linkedin_post_draft(numbers), height=320)
    c1, c2 = st.columns(2)
    model = db.conn.execute("SELECT model FROM extractions WHERE extractor=? LIMIT 1", (A.extractor,)).fetchone()
    model = model[0] if model else A.extractor
    if c1.button("Gerar relatório público (sem dados pessoais)"):
        files = pl.make_report(cfg, A, gap=None, plan=None, model=model, public=True)
        st.success(f"Salvo em {files['report'].parent}")
        for p in files.values():
            if Path(p).suffix == ".png":
                st.image(str(p))
    if c2.button("Gerar relatório completo (privado)"):
        gap = pl.compute_gap(cfg, A)
        files = pl.make_report(cfg, A, gap=gap, plan=pl.make_plan(cfg, A, gap), model=model)
        st.success(f"Salvo em {files['report']}")
    with st.expander("Números (JSON)"):
        st.json(numbers, expanded=False)


{
    PAGES[0]: page_home, PAGES[1]: page_market, PAGES[2]: page_compare, PAGES[3]: page_profile,
    PAGES[4]: page_plan, PAGES[5]: page_roles, PAGES[6]: page_jobs, PAGES[7]: page_report,
}[page]()
