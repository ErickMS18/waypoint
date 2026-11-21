// Waypoint — local interface. Vanilla JS, no build step: everything here is served from disk.
import { STR, WEEKDAYS, WEEKDAYS_SHORT, MONTHS } from "./i18n.js";

// ============================================================================ state & helpers
const S = {
  shell: null, lang: "pt", theme: "dark", skipped: new Set(), partial: false, lastLog: null, polling: null,
  market: { role: "", region: "", seniority: [], top: 20, picked: null },
  compare: [], jobs: { q: "", role: "", region: "", seniority: "", skill: "", sel: null },
  profileRole: "", newProject: false, editing: null, confirmDel: null, capture: null, routine: null,
};
const $ = (sel, root = document) => root.querySelector(sel);
const main = () => $("#main");

export function t(key, vars = {}) {
  const s = (STR[S.lang] && STR[S.lang][key]) ?? STR.pt[key] ?? key;
  return s.replace(/\{(\w+)\}/g, (_, k) => (vars[k] ?? `{${k}}`));
}
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fh = (h) => { const x = Math.round((+h || 0) * 2) / 2; const s = String(x); return (S.lang === "pt" ? s.replace(".", ",") : s) + " h"; };
const pct = (x) => (x == null ? "—" : Math.round(x * 100) + "%");
const isoDate = (s) => { const [y, m, d] = s.slice(0, 10).split("-").map(Number); return new Date(y, m - 1, d); };
const todayDate = () => isoDate(S.shell?.today || new Date().toISOString().slice(0, 10));
const wd = (d) => (d.getDay() + 6) % 7; // Monday = 0
function longDate(d) {
  const w = WEEKDAYS[S.lang][wd(d)], m = MONTHS[S.lang][d.getMonth()];
  return S.lang === "pt" ? `${w[0].toUpperCase() + w.slice(1)}, ${d.getDate()} de ${m}` : `${w}, ${m} ${d.getDate()}`;
}
const shortDate = (d) => (S.lang === "pt" ? `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}` : `${MONTHS.en[d.getMonth()].slice(0, 3)} ${d.getDate()}`);
function dueInfo(iso) {
  if (!iso) return null;
  const n = Math.round((isoDate(iso) - todayDate()) / 86400000);
  if (n < 0) return { text: t("due_late", { n: -n }), urgent: true };
  if (n === 0) return { text: t("due_today"), urgent: true };
  if (n === 1) return { text: t("due_tomorrow"), urgent: true };
  if (n <= 7) return { text: t("due_in", { n }), urgent: false };
  return { text: t("due_on", { date: shortDate(isoDate(iso)) }), urgent: false };
}
const dueHtml = (iso) => { const d = dueInfo(iso); return d ? `<span class="due ${d.urgent ? "urgent" : ""}">${esc(d.text)}</span>` : ""; };
const seniorityLabel = (k) => t("sen_" + (k || "unknown"));
const regionLabel = (k) => t("reg_" + k);
const areaLabel = (a) => t("area_" + a);

async function api(path, { method = "GET", body } = {}) {
  const opts = { method, headers: {} };
  if (body instanceof FormData) opts.body = body;
  else if (body !== undefined) { opts.body = JSON.stringify(body); opts.headers["Content-Type"] = "application/json"; }
  const r = await fetch(path, opts);
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail || detail; } catch (_) { /* keep statusText */ }
    throw new Error(detail);
  }
  return r.json();
}

// ============================================================================ icons & glyphs
const ICON = {
  check: '<path d="M5 12.5 10 17 19 7"/>', plus: '<path d="M12 5v14M5 12h14"/>', minus: '<path d="M5 12h14"/>',
  refresh: '<path d="M20 12a8 8 0 1 1-2.3-5.6"/><path d="M20 4v5h-5"/>',
  moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>', out: '<path d="M14 5h5v5M19 5l-8 8"/><path d="M18 14v5H5V6h5"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>',
};
const icon = (name) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICON[name]}</svg>`;
const GLYPH = {
  faculdade: 'M8 1.8 L14.6 13.6 H1.4 Z', estagio: 'M2.4 2.4 H13.6 V13.6 H2.4 Z', pessoal: 'M8 1.2 L14.8 8 L8 14.8 L1.2 8 Z',
  carreira: 'M8 1 L9.7 6.3 L15 8 L9.7 9.7 L8 15 L6.3 9.7 L1 8 L6.3 6.3 Z', interesses: 'M1.5 11 C4 3.5 6.5 3.5 8 8 S12 12.5 14.5 5',
};
function glyph(area, filled = false, cls = "glyph-lg", color = null) {
  const c = color || `var(--a-${area}, var(--muted))`;
  let shape;
  if (area === "pesquisa") shape = `<circle cx="8" cy="8" r="5.8" fill="${filled ? c : "none"}" stroke="${c}" stroke-width="1.6"/>`;
  else if (area === "exploracao") shape = `<circle cx="8" cy="8" r="5.8" fill="${filled ? c : "none"}" stroke="${c}" stroke-width="1.6" stroke-dasharray="2.6 2.1"/>`;
  else if (area === "interesses") shape = `<path d="${GLYPH.interesses}" fill="none" stroke="${c}" stroke-width="${filled ? 2.6 : 1.7}" stroke-linecap="round"/>`;
  else shape = `<path d="${GLYPH[area] || GLYPH.pessoal}" fill="${filled ? c : "none"}" stroke="${c}" stroke-width="1.6" stroke-linejoin="round"/>`;
  return `<svg class="${cls}" viewBox="0 0 16 16" aria-hidden="true">${shape}</svg>`;
}
const ROLE_COLOR = { ai_ml_engineer: "var(--a-faculdade)", data_scientist: "var(--a-estagio)", bi_analyst: "var(--a-pesquisa)",
  analytics_engineer: "var(--a-pessoal)", mlops_engineer: "var(--a-carreira)", data_analyst: "var(--a-exploracao)", data_engineer: "var(--a-interesses)" };
const roleColor = (id) => ROLE_COLOR[id] || "var(--ink)";

// ============================================================================ toasts
function toast(msg, { action, onAction, error = false, ms = 5200 } = {}) {
  const box = $("#toasts");
  const el = document.createElement("div");
  el.className = "toast" + (error ? " err" : "");
  el.innerHTML = `<span>${esc(msg)}</span>${action ? `<button type="button">${esc(action)}</button>` : ""}`;
  if (action) el.querySelector("button").addEventListener("click", () => { el.remove(); onAction && onAction(); });
  box.appendChild(el);
  setTimeout(() => el.remove(), ms);
}
const fail = (e) => toast(t("error_prefix") + " " + (e.message || e), { error: true, ms: 8000 });

// ============================================================================ shell
const NAV = [["hoje", "nav_today"], ["semana", "nav_week"], ["projetos", "nav_projects"], ["estudos", "nav_study"],
  ["mercado", "nav_market"], ["vagas", "nav_jobs"], ["perfil", "nav_profile"]];

function route() {
  const parts = (location.hash.replace(/^#\/?/, "") || "hoje").split("/");
  return { page: parts[0] || "hoje", sub: parts[1] || "" };
}

async function loadShell() {
  S.shell = await api("/api/shell");
  S.lang = S.shell.settings.lang || "pt";
  S.theme = S.shell.settings.theme || "dark";
  document.documentElement.dataset.theme = S.theme;
  document.documentElement.lang = S.lang === "pt" ? "pt-BR" : "en";
}

function renderTop() {
  const { page } = route();
  const sh = S.shell;
  const st = sh.update || {};
  const running = st.state === "running";
  const upd = running ? t("updating_pct", { p: Math.round((st.frac || 0) * 100) })
    : (sh.last_update ? t("market_at", { when: sh.last_update.slice(0, 5) }) : t("market_never"));
  $("#top").innerHTML = `
    <a class="brand" href="#/hoje" aria-label="Waypoint, ${esc(t("nav_today"))}">${glyph("faculdade", true, "", "var(--accent)")}Waypoint</a>
    <nav class="nav" aria-label="${esc(t("nav_label"))}">
      ${NAV.map(([k, key]) => `<a href="#/${k}" ${page === k ? 'aria-current="page"' : ""}>${esc(t(key))}${k === "hoje" && sh.alerts ? `<span class="dot" title="${esc(t("alerts_title"))}"></span>` : ""}</a>`).join("")}
    </nav>
    <div class="tools">
      <button class="btn sm" type="button" data-act="capture-open" title="Ctrl+K">${icon("plus")}${esc(t("add"))}</button>
      <button class="btn sm ghost" type="button" data-act="update" ${running ? "disabled" : ""} title="${esc(t("update_help"))}${sh.last_update ? " (" + esc(sh.last_update) + ")" : ""}">${icon("refresh")}<span class="small">${esc(upd)}</span></button>
      <div class="seg" role="group" aria-label="${esc(t("theme"))}">
        <button type="button" data-act="theme" data-v="dark" aria-pressed="${S.theme === "dark"}" aria-label="${esc(t("theme_dark"))}">${icon("moon")}</button>
        <button type="button" data-act="theme" data-v="light" aria-pressed="${S.theme === "light"}" aria-label="${esc(t("theme_light"))}">${icon("sun")}</button>
      </div>
      <div class="seg" role="group" aria-label="${esc(t("language"))}">
        <button type="button" data-act="lang" data-v="pt" aria-pressed="${S.lang === "pt"}">PT</button>
        <button type="button" data-act="lang" data-v="en" aria-pressed="${S.lang === "en"}">EN</button>
      </div>
    </div>`;
  const pl = $("#progress");
  pl.hidden = !running;
  if (running) pl.querySelector("span").style.width = Math.round((st.frac || 0) * 100) + "%";
}

function head(title, sub = "", right = "") {
  return `<div class="page-head"><div><h1 class="h1">${esc(title)}</h1>${sub ? `<p class="muted">${esc(sub)}</p>` : ""}</div>${right}</div>`;
}
function tabs(base, items, current) {
  return `<nav class="tabs" aria-label="${esc(t("subnav"))}">${items.map(([k, key]) => `<a href="#/${base}/${k}" ${current === k ? 'aria-current="page"' : ""}>${esc(t(key))}</a>`).join("")}</nav>`;
}
const skeleton = () => `<div class="stack" style="margin-top:40px">${'<div class="skel"></div>'.repeat(4)}</div>`;

async function render() {
  const { page, sub } = route();
  renderTop();
  const fn = PAGES[page] || PAGES.hoje;
  main().innerHTML = skeleton();
  try { main().innerHTML = await fn(sub); } catch (e) { main().innerHTML = `<div class="empty"><h1 class="h1">${esc(t("error_title"))}</h1><p class="muted">${esc(e.message)}</p></div>`; }
  document.title = `Waypoint — ${t((NAV.find(([k]) => k === page) || NAV[0])[1])}`;
}

// ============================================================================ page: today
const NOW_FOR = { faculdade: "now_faculdade", estagio: "now_estagio", pesquisa: "now_pesquisa", pessoal: "now_pessoal",
  carreira: "now_carreira", exploracao: "now_exploracao", interesses: "now_interesses" };

async function pageToday() {
  const d = await api("/api/today");
  S.today = d;
  const sh = S.shell;
  if (d.empty) {
    const steps = [
      [sh.has_routine, "ob_routine", "ob_routine_how", `<a class="btn sm" href="#/perfil/rotina">${esc(t("ob_routine_cta"))}</a>`],
      [sh.counts.projects > 0, "ob_projects", "ob_projects_how", `<button class="btn sm accent" type="button" data-act="capture-open">${esc(t("ob_projects_cta"))}</button>`],
      [sh.has_plan, "ob_plan", "ob_plan_how", `<a class="btn sm" href="#/estudos">${esc(t("ob_plan_cta"))}</a>`],
      [sh.counts.jobs > 0 && sh.has_profile, "ob_market", "ob_market_how", `<a class="btn sm" href="#/perfil/voce">${esc(t("ob_market_cta"))}</a>`],
    ];
    return `<section class="empty">
      <p class="muted">${esc(longDate(todayDate()))}</p>
      <h1 class="display">${esc(t("empty_title"))}</h1>
      <p class="muted" style="max-width:60ch">${esc(t("empty_body"))}</p>
      <ol class="steps">${steps.map(([ok, k, how, cta]) => `<li class="${ok ? "ok" : ""}"><div class="stack" style="gap:6px;flex:1"><span class="t" style="font-weight:600">${esc(t(k))}</span><span class="muted small">${esc(t(how))}</span></div>${ok ? "" : cta}</li>`).join("")}</ol>
    </section>`;
  }

  const queue = [...d.blocks.filter((b) => !S.skipped.has(b.item)), ...d.blocks.filter((b) => S.skipped.has(b.item))];
  const now = queue[0];
  const rest = queue.slice(1);
  const greeting = (() => { const h = new Date().getHours(); return t(h < 12 ? "greet_morning" : h < 18 ? "greet_afternoon" : "greet_evening"); })();
  const doneLine = t("today_line", { free: fh(d.free), done: fh(d.done_hours) });

  let slab;
  if (now) {
    const meta = [now.project && `<span>${esc(now.project)}</span>`, `<span>${esc(fh(now.hours))}</span>`, now.due && dueHtml(now.due)].filter(Boolean).join("");
    slab = `<section class="slab" aria-label="${esc(t("now"))}">
      <div class="eyebrow">${glyph(now.area, true, "glyph-lg", "var(--on-accent)")}${esc(t(NOW_FOR[now.area] || "now_pessoal"))}</div>
      <h1 class="display">${esc(now.title)}</h1>
      <div class="meta">${meta}</div>
      ${S.partial ? `<form class="row" data-form="partial" style="margin-top:8px">
          <label class="row" style="gap:10px"><span>${esc(t("partial_q"))}</span>
          <input type="number" name="hours" min="0.5" max="12" step="0.5" value="${Math.min(1, now.hours)}" style="width:100px;background:transparent;border-color:var(--on-accent);color:var(--on-accent)"></label>
          <button class="btn primary" type="submit">${esc(t("partial_save"))}</button>
          <button class="btn ghost" type="button" data-act="partial-toggle">${esc(t("cancel"))}</button></form>`
      : `<div class="row" style="margin-top:8px">
          <button class="btn primary" type="button" data-act="done" data-item="${esc(now.item)}" data-hours="${now.hours}" data-title="${esc(now.title)}">${icon("check")}${esc(t("done_block"))}</button>
          <button class="btn" type="button" data-act="partial-toggle">${esc(t("partial"))}</button>
          <button class="btn ghost" type="button" data-act="skip" data-item="${esc(now.item)}" ${queue.length < 2 ? "disabled" : ""}>${esc(t("next"))}</button>
        </div>`}
    </section>`;
  } else {
    const finished = d.logged.length > 0;
    slab = `<section class="slab"><div class="eyebrow">${esc(finished ? t("day_done_eyebrow") : t("free_day_eyebrow"))}</div>
      <h1 class="display">${esc(finished ? t("day_done_title") : t("free_day_title"))}</h1>
      <div class="row"><button class="btn primary" type="button" data-act="capture-open">${icon("plus")}${esc(t("add"))}</button>
      <a class="btn" href="#/semana">${esc(t("see_week"))}</a></div></section>`;
  }

  const choices = [
    ...d.risks.map((r) => `<div class="row" style="gap:14px 18px">
      <span class="tag pink">${esc(t("choice_tag"))}</span>
      <p style="flex:1 1 360px">${t("risk_text", { task: `<strong>${esc(r.title)}</strong>`, project: esc(r.project), due: esc((dueInfo(r.due) || {}).text || ""), h: esc(fh(r.missing)) })}</p>
      ${Object.entries(r.borrowable).map(([foco, h]) => `<button class="btn sm" type="button" data-act="borrow" data-foco="${foco}" data-hours="${Math.min(h, r.missing)}" data-task="${esc(r.title)}" title="${esc(t("borrow_help"))}">${esc(t("borrow_btn", { h: fh(Math.min(h, r.missing)), foco: areaLabel(foco).toLowerCase() }))}</button>`).join("")}
      <a class="btn sm ghost" href="#/perfil/rotina">${esc(t("risk_time"))}</a>
      <a class="btn sm ghost" href="#/projetos">${esc(t("risk_scope"))}</a></div>`),
    ...d.overdue.map((o) => `<div class="row" style="gap:14px 18px"><span class="tag pink">${esc(t("overdue_tag"))}</span>
      <p style="flex:1 1 360px">${t("overdue_text", { task: `<strong>${esc(o.title)}</strong>`, project: esc(o.project) })}</p>
      <a class="btn sm" href="#/projetos">${esc(t("risk_scope"))}</a></div>`),
  ].join("");

  const slipped = d.slipped.length ? `<p class="muted">${esc(t("slipped", { items: d.slipped.slice(0, 3).map((s) => `${s.title} (${fh(s.missing)})`).join(", ") }))}</p>` : "";
  const p = d.pulse;
  const pulse = p ? (p.fit != null
      ? `<div><p class="big-num">${pct(p.fit)}</p><p class="muted" style="margin-top:10px;max-width:34ch">${esc(t("pulse_fit", { jobs: p.jobs, roles: p.roles }))}${p.top_gap ? " " + esc(t("pulse_gap", { name: p.top_gap.name, share: pct(p.top_gap.share) })) : ""}</p></div>`
      : `<div><p class="big-num">${p.jobs}</p><p class="muted" style="margin-top:10px;max-width:34ch">${esc(t("pulse_jobs", { roles: p.roles }))}</p><a class="btn sm" style="margin-top:14px" href="#/perfil/voce">${esc(t("pulse_send_cv"))}</a></div>`)
    : `<div><p class="h3">${esc(t("pulse_none_title"))}</p><p class="muted" style="margin-top:8px">${esc(t("pulse_none"))}</p><button class="btn sm" style="margin-top:14px" type="button" data-act="update">${icon("refresh")}${esc(t("update_market"))}</button></div>`;
  const maxH = Math.max(1, ...d.week.map((w) => w.hours));
  const week = `<div><p class="muted" style="margin-bottom:14px">${esc(t("your_week"))}</p>
    <div class="week-dots" role="img" aria-label="${esc(t("week_dots_label"))}">${d.week.map((w) => {
      const sz = Math.round(12 + (w.hours / maxH) * 34);
      return `<div><span class="d ${w.today ? "on" : ""}" style="width:${sz}px;height:${sz}px" title="${esc(fh(w.hours))}"></span><span class="tiny ${w.today ? "" : "muted"}" style="${w.today ? "font-weight:700" : ""}">${esc(WEEKDAYS_SHORT[S.lang][wd(isoDate(w.date))])}</span></div>`;
    }).join("")}</div><a class="btn sm ghost" style="margin-top:10px;padding:0" href="#/semana">${esc(t("see_week"))}</a></div>`;

  const total = Math.max(d.total_hours, 0.01);
  const stripParts = [...d.logged.map((l) => ({ h: l.hours, area: l.area, done: true })), ...queue.map((b) => ({ h: b.hours, area: b.area }))];
  const strip = `<div class="strip" role="img" aria-label="${esc(t("strip_label"))}">${stripParts.map((s) => `<span style="flex:${s.h};background:var(--a-${s.area});opacity:${s.done ? 0.4 : 1}"></span>`).join("")}</div>`;
  const items = [
    ...d.logged.map((l) => `<div class="item done">${glyph(l.area, true)}<div class="body"><div class="title">${esc(l.title)}</div><div class="muted small">${esc(t("done_word"))}${l.project && l.project !== l.title ? " · " + esc(l.project) : ""}</div></div><span class="muted small num">${esc(fh(l.hours))}</span></div>`),
    ...rest.map((b) => `<div class="item">${glyph(b.area)}<div class="body"><div class="title">${esc(b.title)}</div><div class="muted small">${esc(b.project || areaLabel(b.area))}${b.due ? " " : ""}${dueHtml(b.due)}</div></div><span class="muted small num">${esc(fh(b.hours))}</span>
      <button class="check" type="button" data-act="done" data-item="${esc(b.item)}" data-hours="${b.hours}" data-title="${esc(b.title)}" aria-label="${esc(t("done_aria", { title: b.title }))}">${icon("check")}</button></div>`),
  ].join("");

  return `<div class="split">
    <div class="main">
      <p class="muted">${esc(longDate(todayDate()))}. ${esc(greeting)}. ${esc(doneLine)}</p>
      ${slipped}
      ${slab}
      ${choices ? `<div class="stack" style="gap:18px">${choices}</div>` : ""}
      <div class="grid cols-2 rule" style="padding-top:28px;gap:40px">${pulse}${week}</div>
    </div>
    <aside class="side" aria-label="${esc(t("rest_of_day"))}">
      <div class="row between"><span class="muted">${esc(t("free_today"))}</span>
        <div class="stepper" role="group" aria-label="${esc(t("free_today"))}">
          <button type="button" data-act="free" data-delta="-0.5" aria-label="${esc(t("less"))}">${icon("minus")}</button>
          <output>${esc(fh(d.free))}</output>
          <button type="button" data-act="free" data-delta="0.5" aria-label="${esc(t("more"))}">${icon("plus")}</button></div></div>
      <h2 class="h2" style="margin-top:8px">${esc(t("rest_of_day"))}</h2>
      ${strip}
      <p class="muted small">${esc(t("progress_line", { done: fh(d.done_hours), total: fh(total) }))}</p>
      <div class="list">${items || `<p class="muted">${esc(t("nothing_else"))}</p>`}</div>
    </aside>
  </div>`;
}

// ============================================================================ page: week
async function pageWeek(sub) {
  const offset = sub === "proxima" ? 1 : 0;
  const w = await api(`/api/week?offset=${offset}`);
  const days = w.days.map((d) => {
    const dt = isoDate(d.date);
    const planned = d.blocks.reduce((s, b) => s + b.hours, 0) + d.done.reduce((s, x) => s + x.hours, 0);
    const cap = d.today ? d.capacity : d.capacity;
    return `<section class="day ${d.today ? "today" : ""} ${d.past ? "past" : ""}" aria-label="${esc(longDate(dt))}">
      <div class="row between" style="align-items:baseline"><span class="dnum">${dt.getDate()}</span><span class="dname">${esc(WEEKDAYS_SHORT[S.lang][wd(dt)])}</span></div>
      ${d.past ? "" : `<div class="bar" title="${esc(t("planned_of", { p: fh(planned), c: fh(cap) }))}"><span style="width:${Math.min(100, (planned / Math.max(cap, 0.01)) * 100)}%"></span></div><span class="tiny muted">${esc(t("planned_of", { p: fh(planned), c: fh(cap) }))}</span>`}
      ${d.done.map((x) => `<div class="blk done">${glyph(x.area, true, "glyph")}<div><div class="t">${esc(x.title)}</div><div class="h">${esc(fh(x.hours))}</div></div></div>`).join("")}
      ${d.blocks.map((b) => `<div class="blk">${glyph(b.area, false, "glyph")}<div><div class="t">${esc(b.title)}</div><div class="h">${esc(fh(b.hours))}${b.project ? " · " + esc(b.project) : ""}</div></div></div>`).join("")}
      ${!d.blocks.length && !d.done.length ? `<span class="muted small">${esc(d.past ? t("past_day") : t("free_day"))}</span>` : ""}
    </section>`;
  }).join("");
  const load = Object.entries(w.week_load || {});
  return `${head(t("week_title"), t("week_sub"), `<div class="row"><a class="btn sm" href="#/perfil/rotina">${esc(t("adjust_time"))}</a></div>`)}
    ${tabs("semana", [["esta", "this_week"], ["proxima", "next_week"]], offset ? "proxima" : "esta")}
    <div class="week">${days}</div>
    ${offset ? `<p class="muted small" style="margin-top:22px">${esc(t("next_week_note"))}</p>` : ""}
    ${w.unscheduled_study > 0 ? `<p class="row" style="margin-top:22px"><span class="tag pink">${esc(t("heads_up"))}</span><span>${esc(t("unscheduled", { h: fh(w.unscheduled_study) }))}</span></p>` : ""}
    ${load.length && !offset ? `<div class="rule" style="margin-top:34px;padding-top:26px"><h2 class="h3" style="margin-bottom:16px">${esc(t("load_by_area"))}</h2>
      <div class="legend">${load.map(([a, h]) => `<span class="row" style="gap:8px">${glyph(a, true, "glyph")}${esc(areaLabel(a))} <strong class="num">${esc(fh(h))}</strong></span>`).join("")}</div></div>` : ""}`;
}

// ============================================================================ page: projects
const AREAS = ["faculdade", "estagio", "pesquisa", "carreira", "pessoal"];
const areaOptions = (sel) => AREAS.map((a) => `<option value="${a}" ${a === sel ? "selected" : ""}>${esc(areaLabel(a))}</option>`).join("");
const prioOptions = (sel) => [1, 2, 3].map((p) => `<option value="${p}" ${p === sel ? "selected" : ""}>${esc(t("prio_" + p))}</option>`).join("");

function projectForm(p, formName) {
  return `<form class="grid cols-3" data-form="${formName}" ${p.id ? `data-id="${esc(p.id)}"` : ""} style="gap:16px;margin-top:6px">
    <label class="field" style="grid-column:1/-1"><span>${esc(t("p_name"))}</span><input type="text" name="name" required value="${esc(p.name || "")}" placeholder="${esc(t("p_name_ph"))}"></label>
    <label class="field"><span>${esc(t("p_area"))}</span><select name="area">${areaOptions(p.area || "faculdade")}</select></label>
    <label class="field"><span>${esc(t("p_deadline"))}</span><input type="date" name="deadline" value="${esc(p.deadline || "")}"></label>
    <label class="field"><span>${esc(t("p_priority"))}</span><select name="priority">${prioOptions(p.priority || 2)}</select></label>
    <label class="field"><span>${esc(t("p_hours"))}</span><input type="number" name="hours" min="0" max="400" step="0.5" value="${p.hours ?? 8}"></label>
    <label class="field" style="grid-column:span 2"><span>${esc(t("p_notes"))}</span><input type="text" name="notes" value="${esc(p.notes || "")}" placeholder="${esc(t("p_notes_ph"))}"></label>
    ${p.id ? "" : `<label class="row" style="grid-column:1/-1;gap:10px"><input type="checkbox" name="breakdown" checked><span>${esc(t("p_breakdown"))}</span></label>`}
    <div class="row" style="grid-column:1/-1"><button class="btn primary" type="submit">${esc(p.id ? t("save") : t("p_create"))}</button>
      <button class="btn ghost" type="button" data-act="${p.id ? "edit-cancel" : "new-cancel"}">${esc(t("cancel"))}</button></div>
  </form>`;
}

function tasksEditor(p) {
  const rows = p.tasks.map((tk) => `<tr data-task="${esc(tk.id)}">
    <td style="width:44px"><input type="checkbox" name="done" ${tk.done ? "checked" : ""} aria-label="${esc(t("t_done"))}"></td>
    <td><input type="text" name="title" value="${esc(tk.title)}" aria-label="${esc(t("t_title"))}"></td>
    <td style="width:110px"><input type="number" name="hours" min="0.5" max="200" step="0.5" value="${tk.hours}" aria-label="${esc(t("t_hours"))}"></td>
    <td style="width:170px"><input type="date" name="due" value="${esc(tk.due || "")}" aria-label="${esc(t("t_due"))}"></td>
    <td class="muted small num" style="width:90px">${esc(fh(tk.logged))}</td>
    <td style="width:48px"><button class="btn icon ghost" type="button" data-act="task-remove" aria-label="${esc(t("remove"))}">${icon("x")}</button></td></tr>`).join("");
  return `<form data-form="tasks" data-id="${esc(p.id)}"><div class="table-wrap"><table>
    <thead><tr><th></th><th>${esc(t("t_title"))}</th><th>${esc(t("t_hours"))}</th><th>${esc(t("t_due"))}</th><th>${esc(t("t_logged"))}</th><th></th></tr></thead>
    <tbody>${rows}</tbody></table></div>
    <div class="row" style="margin-top:14px"><button class="btn sm" type="button" data-act="task-add">${icon("plus")}${esc(t("t_add"))}</button>
    <button class="btn sm primary" type="submit">${esc(t("p_save_tasks"))}</button></div></form>`;
}

function projectBlock(p) {
  const frac = p.total_hours ? p.done_hours / p.total_hours : 0;
  if (S.editing === p.id) return `<article class="proj">${projectForm(p, "edit-project")}</article>`;
  const delBtn = S.confirmDel === p.id
    ? `<button class="btn sm" type="button" data-act="delete-confirm" data-id="${esc(p.id)}" style="border-color:var(--accent-2);color:var(--accent-2)">${esc(t("delete_confirm"))}</button>`
    : `<button class="btn sm ghost" type="button" data-act="delete" data-id="${esc(p.id)}">${esc(t("delete"))}</button>`;
  return `<article class="proj" aria-label="${esc(p.name)}">
    <div class="row between"><span class="row" style="gap:10px">${glyph(p.area, true)}<span class="muted">${esc(areaLabel(p.area))}</span>
      <span class="tag line">${esc(t("prio_" + p.priority))}</span></span>${p.deadline ? dueHtml(p.deadline) : `<span class="muted small">${esc(t("no_deadline"))}</span>`}</div>
    <h2 class="name">${esc(p.name)}</h2>
    ${p.notes ? `<p class="muted" style="max-width:70ch">${esc(p.notes)}</p>` : ""}
    <div class="row" style="gap:16px"><div class="bar" style="flex:1 1 260px;max-width:520px"><span style="width:${Math.round(frac * 100)}%"></span></div>
      <span class="muted small num">${esc(t("p_progress", { done: fh(p.done_hours), total: fh(p.total_hours) }))}</span></div>
    <details class="more" ${S.openProject === p.id ? "open" : ""} data-id="${esc(p.id)}"><summary>${esc(t("p_tasks", { done: p.tasks.filter((x) => x.done).length, n: p.tasks.length }))}</summary><div>${tasksEditor(p)}</div></details>
    <div class="row"><button class="btn sm" type="button" data-act="edit" data-id="${esc(p.id)}">${esc(t("edit"))}</button>
      <button class="btn sm ghost" type="button" data-act="archive" data-id="${esc(p.id)}">${esc(t("archive"))}</button>${delBtn}</div>
  </article>`;
}

async function pageProjects() {
  const { projects } = await api("/api/projects");
  S.projects = projects;
  const active = projects.filter((p) => !p.archived), archived = projects.filter((p) => p.archived);
  return `${head(t("projects_title"), t("projects_sub"), `<div class="row"><button class="btn accent" type="button" data-act="capture-open">${icon("plus")}${esc(t("add_with_ai"))}</button>
      <button class="btn" type="button" data-act="new-open">${esc(t("new_manual"))}</button></div>`)}
    ${S.newProject ? `<div class="panel" style="margin-bottom:26px">${projectForm({}, "new-project")}</div>` : ""}
    ${active.length ? `<div>${active.map(projectBlock).join("")}</div>` : `<div class="empty" style="padding-top:10px"><h2 class="h2">${esc(t("p_empty_title"))}</h2><p class="muted">${esc(t("p_empty"))}</p>
      <div class="row"><button class="btn accent" type="button" data-act="capture-open">${icon("plus")}${esc(t("add_with_ai"))}</button></div></div>`}
    ${archived.length ? `<details class="more" style="margin-top:28px"><summary>${esc(t("archived", { n: archived.length }))}</summary><div class="list">
      ${archived.map((p) => `<div class="item">${glyph(p.area)}<div class="body"><div class="title">${esc(p.name)}</div><div class="muted small">${esc(areaLabel(p.area))}</div></div>
      <button class="btn sm" type="button" data-act="unarchive" data-id="${esc(p.id)}">${esc(t("restore"))}</button></div>`).join("")}</div></details>` : ""}`;
}

// ============================================================================ page: study plan
async function pagePlan() {
  const d = await api("/api/plan");
  const f = d.focus || {}, w = f.weights || {}, plan = d.plan;
  const ex = f.exploration || {};
  const slider = (k, label) => `<label class="field"><span class="row between">${esc(label)}<output class="num" data-out="${k}">${w[k] ?? 0}</output></span>
    <input type="range" min="0" max="100" step="5" name="${k}" value="${w[k] ?? 0}" data-live="${k}"></label>`;
  const focusForm = `<form class="grid cols-3" data-form="focus" style="gap:22px">
      <label class="field"><span>${esc(t("study_hours"))}</span><input type="number" name="weekly_hours" min="1" max="80" step="0.5" value="${f.weekly_hours ?? 10}"></label>
      ${slider("carreira", areaLabel("carreira"))}${slider("exploracao", areaLabel("exploracao"))}${slider("interesses", areaLabel("interesses"))}
      <label class="field" style="grid-column:span 2"><span>${esc(t("explore_topics"))}</span><input type="text" name="topics" value="${esc((ex.topics || []).join(", "))}" placeholder="${esc(t("explore_ph"))}"></label>
      <label class="field" style="grid-column:span 2"><span>${esc(t("interests_label"))}</span><input type="text" name="interests" value="${esc((f.interests || []).join(", "))}" placeholder="${esc(t("interests_ph"))}"></label>
      <label class="row" style="gap:12px;grid-column:1/-1"><span class="switch"><input type="checkbox" name="protected" ${ex.protected !== false ? "checked" : ""}><span></span></span>${esc(t("protect"))}</label>
      <p class="muted small" style="grid-column:1/-1">${esc(t("weights_note"))}</p>
      <div class="row" style="grid-column:1/-1"><button class="btn primary" type="submit">${esc(t("save_focus"))}</button></div></form>`;
  const top = head(t("study_title"), t("study_sub"), `<div class="row"><label class="row" style="gap:10px"><input type="checkbox" id="ideas" ${S.shell.llm ? "checked" : ""}><span class="small">${esc(t("ai_ideas"))}</span></label>
    <button class="btn accent" type="button" data-act="plan-generate">${esc(plan ? t("plan_regen") : t("plan_gen"))}</button></div>`);
  const focusBlock = `<details class="more" ${plan ? "" : "open"} style="margin-bottom:30px"><summary>${esc(t("focus_title"))}</summary><div>${focusForm}</div></details>`;
  if (!plan) return top + focusBlock + `<p class="muted">${esc(S.shell.counts.jobs ? t("plan_none") : t("plan_needs_market"))}</p>`;
  const h = plan.hours || {};
  const kpis = [["carreira", h.carreira], ["exploracao", h.exploracao], ["interesses", h.interesses]].map(([a, v]) =>
    `<div class="kpi"><div class="row" style="gap:8px">${glyph(a, true)}<span class="muted">${esc(areaLabel(a))}${a === "exploracao" && plan.protected_exploration ? " · " + esc(t("protected")) : ""}</span></div><div class="v" style="margin-top:10px">${esc(fh(v || 0))}</div></div>`).join("");
  const studyWeek = plan.this_week.map((it) => `<div class="item">${glyph(it.area, it.logged >= it.horas)}<div class="body"><div class="title">${esc(it.item)}</div><div class="muted small">${esc(areaLabel(it.area))}</div></div>
    <div style="width:180px"><div class="bar"><span style="width:${Math.min(100, (it.logged / Math.max(it.horas, 0.01)) * 100)}%"></span></div><div class="tiny muted num" style="margin-top:4px">${esc(fh(it.logged))} / ${esc(fh(it.horas))}</div></div></div>`).join("");
  const career = (plan.career || []).map((c) => `<div class="rule" style="padding-top:16px"><h3 class="h3">${esc(c.name)}</h3>
    <p class="muted small" style="margin:6px 0 8px">${esc(t("you_status", { s: t("status_" + c.status), h: fh(c.effort_hours) }))}</p><p>${esc(c.why)}</p>
    ${c.pairs_with && c.pairs_with.length ? `<p class="muted small" style="margin-top:8px">${esc(t("pairs", { x: c.pairs_with.join(", ") }))}</p>` : ""}</div>`).join("");
  const existing = new Set(d.existing_projects || []);
  const projects = (plan.projects || []).map((p, i) => `<details class="more rule" style="padding-top:16px"><summary><span class="h3" style="color:var(--ink)">${esc(p.title)}</span></summary><div class="stack">
    <p>${esc(p.description)}</p>${p.deliverable ? `<p><strong>${esc(t("deliverable"))}:</strong> ${esc(p.deliverable)}</p>` : ""}
    <div>${(p.skills || []).map((s) => `<span class="pill">${esc(s)}</span>`).join("")}</div>
    ${p.bridge_interest ? `<p class="muted small">${esc(t("bridge_with", { x: p.bridge_interest }))}</p>` : ""}
    <div><button class="btn sm" type="button" data-act="plan-project" data-i="${i}" ${existing.has(p.title) ? "disabled" : ""}>${icon("plus")}${esc(existing.has(p.title) ? t("already_added") : t("add_to_projects"))}</button></div></div></details>`).join("");
  S.planProjects = plan.projects || [];
  return `${top}${focusBlock}
    ${plan.lang && plan.lang !== S.lang ? `<p class="row" style="margin-bottom:22px"><span class="tag line">${esc(t("plan_lang"))}</span></p>` : ""}
    <div class="grid cols-3" style="margin-bottom:34px">${kpis}</div>
    <div class="split">
      <div class="main">
        <section><h2 class="h2" style="margin-bottom:6px">${esc(t("career_title"))}</h2><p class="muted" style="margin-bottom:12px">${esc(t("career_sub"))}</p>
          <div class="grid cols-2" style="gap:26px 34px">${career}</div></section>
        ${projects ? `<section><h2 class="h2" style="margin-bottom:6px">${esc(t("projects_suggested"))}</h2><p class="muted" style="margin-bottom:8px">${esc(t("projects_suggested_sub"))}</p>${projects}</section>` : ""}
        ${(plan.tradeoffs || []).length ? `<section class="rule" style="padding-top:22px"><h2 class="h3" style="margin-bottom:12px">${esc(t("tradeoffs"))}</h2><div class="stack">${plan.tradeoffs.map((x) => `<p>${esc(x)}</p>`).join("")}</div></section>` : ""}
        ${(plan.notes || []).map((n) => `<p class="muted small">${esc(n)}</p>`).join("")}
      </div>
      <aside class="side">
        <h2 class="h2">${esc(t("study_week"))}</h2><p class="muted small">${esc(t("study_week_sub"))}</p><div class="list">${studyWeek}</div>
        <h2 class="h3" style="margin-top:18px">${esc(areaLabel("exploracao"))}</h2>
        <div class="stack">${(plan.exploration || []).map((e) => `<p><strong>${esc(e.name)}</strong>${e.why ? ` <span class="muted">— ${esc(e.why)}</span>` : ""}</p>`).join("") || `<p class="muted">${esc(t("explore_empty"))}</p>`}</div>
        <h2 class="h3" style="margin-top:18px">${esc(t("bridges_title"))}</h2>
        <div class="stack">${(plan.bridges || []).map((b) => `<p><strong>${esc(b.interest)}</strong> <span class="muted">— ${esc(b.idea)}</span></p>`).join("") || `<p class="muted">${esc(t("interests_empty"))}</p>`}</div>
      </aside>
    </div>`;
}

// ============================================================================ page: market (panorama, compare, roles, report)
const MARKET_TABS = [["panorama", "tab_overview"], ["comparar", "tab_compare"], ["cargos", "tab_roles"], ["relatorio", "tab_report"]];

async function pageMarket(sub) {
  const tab = MARKET_TABS.some(([k]) => k === sub) ? sub : "panorama";
  const body = await ({ panorama: marketOverview, comparar: marketCompare, cargos: marketRoles, relatorio: marketReport })[tab]();
  return head(t("market_title"), t("market_sub")) + tabs("mercado", MARKET_TABS, tab) + body;
}

function noMarket() {
  return `<div class="empty" style="padding-top:10px"><h2 class="h2">${esc(t("no_market_title"))}</h2><p class="muted">${esc(t("no_market"))}</p>
    <div class="row"><button class="btn accent" type="button" data-act="update">${icon("refresh")}${esc(t("update_market"))}</button></div></div>`;
}

async function marketOverview() {
  const m = S.market;
  const q = new URLSearchParams({ role: m.role, region: m.region, seniority: m.seniority.join(","), top: m.top });
  const d = await api(`/api/market?${q}`);
  if (d.empty) return noMarket();
  const roleBtns = [["", t("all")], ...d.roles.map((r) => [r.id, r.label])].map(([id, label]) =>
    `<button type="button" data-act="mk-role" data-v="${esc(id)}" aria-pressed="${m.role === id}">${esc(label)}</button>`).join("");
  const roleObj = d.roles.find((r) => r.id === m.role);
  const max = Math.max(0.01, ...d.skills.map((s) => s.share_any));
  const bars = d.skills.map((s) => `<button class="lab" type="button" data-act="mk-skill" data-v="${esc(s.skill_id)}" aria-pressed="${m.picked === s.skill_id}" title="${esc(s.name)}">${esc(s.name)}</button>
    <div class="track"><span class="seg-r" style="width:${(s.share_required / max) * 88}%"></span><span class="seg-n" style="width:${(s.share_nice / max) * 88}%"></span><span class="val">${pct(s.share_any)}</span></div>`).join("");
  let picked = "";
  if (m.picked) {
    const sk = await api(`/api/market/skill/${encodeURIComponent(m.picked)}?${new URLSearchParams({ role: m.role, region: m.region, seniority: m.seniority.join(",") })}`);
    const name = (d.skills.find((s) => s.skill_id === m.picked) || {}).name || m.picked;
    picked = `<section class="panel" style="margin-top:24px"><div class="row between"><h3 class="h3">${esc(t("jobs_asking", { skill: name, n: sk.jobs.length }))}</h3>
      <button class="btn sm ghost" type="button" data-act="mk-skill" data-v="">${esc(t("close"))}</button></div>
      ${sk.pairs.length ? `<p class="muted small" style="margin:6px 0 10px">${esc(t("pairs", { x: sk.pairs.join(", ") }))}</p>` : ""}
      <div class="table-wrap"><table><thead><tr><th>${esc(t("company"))}</th><th>${esc(t("title_col"))}</th><th>${esc(t("asked_as"))}</th><th>${esc(t("region"))}</th><th></th></tr></thead><tbody>
      ${sk.jobs.slice(0, 60).map((j) => `<tr><td>${esc(j.company)}</td><td>${esc(j.title)}</td><td>${esc(j.requirement === "required" ? t("required") : t("nice"))}</td><td>${esc(regionLabel(j.region))}</td>
      <td>${j.url ? `<a class="btn sm ghost" href="${esc(j.url)}" target="_blank" rel="noopener">${icon("out")}${esc(t("open"))}</a>` : ""}</td></tr>`).join("")}</tbody></table></div></section>`;
  }
  const sen = d.seniority;
  const senMax = Math.max(1, ...sen.map((s) => s.n));
  const order = ["intern", "junior", "mid", "senior", "staff_plus", "unknown"];
  const senBars = order.map((k) => sen.find((s) => s.key === k)).filter(Boolean).map((s) => `<span class="lab">${esc(seniorityLabel(s.key))}</span>
    <div class="track"><span class="seg-1" style="width:${(s.n / senMax) * 88}%"></span><span class="val">${s.n}</span></div>`).join("");
  const regs = (d.region_compare[0] ? Object.keys(d.region_compare[0]).filter((k) => ["BR", "REMOTE_BR_OK", "INTL"].includes(k)) : []);
  return `<div class="stack" style="gap:18px;margin-bottom:28px">
      <div class="seg" role="group" aria-label="${esc(t("role"))}" style="flex-wrap:wrap;border-radius:22px">${roleBtns}</div>
      ${roleObj ? `<p class="muted">${esc(S.lang === "en" ? roleObj.summary_en || roleObj.summary : roleObj.summary)}</p>` : ""}
      <div class="row">
        <label class="field" style="width:240px"><span>${esc(t("region"))}</span><select data-change="mk-region"><option value="">${esc(t("all_regions"))}</option>${d.regions.map((r) => `<option value="${r}" ${m.region === r ? "selected" : ""}>${esc(regionLabel(r))}</option>`).join("")}</select></label>
        <div class="field"><span>${esc(t("seniority"))}</span><div class="seg" role="group" style="flex-wrap:wrap">${["intern", "junior", "mid", "senior", "staff_plus"].map((k) => `<button type="button" data-act="mk-sen" data-v="${k}" aria-pressed="${m.seniority.includes(k)}">${esc(seniorityLabel(k))}</button>`).join("")}</div></div>
        <label class="field" style="width:150px"><span>${esc(t("how_many"))}</span><select data-change="mk-top">${[10, 20, 30, 40].map((n) => `<option ${m.top === n ? "selected" : ""}>${n}</option>`).join("")}</select></label>
      </div></div>
    <div class="grid cols-3" style="grid-template-columns:repeat(auto-fit,minmax(170px,1fr));margin-bottom:30px">
      ${[["jobs", d.kpis.jobs], ["companies", d.kpis.companies], ["distinct_skills", d.kpis.skills], ["remote", pct(d.kpis.remote)]].map(([k, v]) => `<div class="kpi"><div class="v">${esc(v)}</div><div class="l">${esc(t("kpi_" + k))}</div></div>`).join("")}
    </div>
    ${d.small_sample ? `<p class="row" style="margin-bottom:20px"><span class="tag pink">${esc(t("heads_up"))}</span>${esc(t("small_sample", { n: d.kpis.jobs }))}</p>` : ""}
    <div class="row between" style="margin-bottom:16px"><h2 class="h2">${esc(t("top_skills"))}</h2>
      <div class="legend"><span><i style="background:var(--accent)"></i>${esc(t("required"))}</span><span><i style="background:color-mix(in srgb,var(--accent) 38%,transparent)"></i>${esc(t("nice"))}</span></div></div>
    <p class="muted small" style="margin-bottom:18px">${esc(t("top_skills_help"))}</p>
    ${d.kpis.jobs ? `<div class="hbars">${bars}</div>` : `<p class="muted">${esc(t("no_jobs_filter"))}</p>`}
    ${picked}
    <div class="grid cols-2" style="margin-top:44px;gap:44px">
      <section><h2 class="h3" style="margin-bottom:16px">${esc(t("seniority"))}</h2><div class="hbars">${senBars}</div></section>
      <section><h2 class="h3" style="margin-bottom:16px">${esc(t("trends"))}</h2>${d.trends.length ? `<div class="table-wrap"><table><thead><tr><th>Skill</th><th>${esc(t("recent"))}</th><th>${esc(t("older"))}</th><th>Δ</th></tr></thead><tbody>
        ${d.trends.map((r) => `<tr><td>${esc(r.name)}</td><td class="num">${pct(r.share_recent)}</td><td class="num">${pct(r.share_older)}</td><td class="num">${r.delta_pp > 0 ? "+" : ""}${Math.round(r.delta_pp)} p.p.</td></tr>`).join("")}</tbody></table></div>` : `<p class="muted">${esc(t("trends_empty"))}</p>`}</section>
    </div>
    ${regs.length ? `<details class="more" style="margin-top:36px"><summary>${esc(t("br_vs_intl"))}</summary><div class="table-wrap"><table><thead><tr><th>Skill</th>${regs.map((r) => `<th>${esc(regionLabel(r))}</th>`).join("")}</tr></thead><tbody>
      ${d.region_compare.map((r) => `<tr><td>${esc(r.name)}</td>${regs.map((g) => `<td class="num">${pct(r[g])}</td>`).join("")}</tr>`).join("")}</tbody></table></div></details>` : ""}`;
}

async function marketCompare() {
  const d = await api(`/api/compare?roles=${encodeURIComponent(S.compare.join(","))}`);
  if (d.empty) return noMarket();
  if (d.available.length < 2) return `<p class="muted">${esc(t("compare_need2"))}</p>`;
  S.compare = d.chosen;
  const toggles = d.available.map((r) => `<button type="button" data-act="cmp-role" data-v="${esc(r.id)}" aria-pressed="${d.chosen.includes(r.id)}">${esc(r.label)} <span class="muted">${r.n}</span></button>`).join("");
  const cards = d.cards.map((c) => `<section class="rule" style="padding-top:18px;border-top:3px solid ${roleColor(c.id)}">
    <h2 class="h3">${esc(c.label)}</h2><p class="muted small" style="margin:6px 0 16px">${esc(S.lang === "en" ? c.summary_en || c.summary : c.summary)}</p>
    ${c.small ? `<p class="small" style="margin-bottom:12px"><span class="tag pink">${esc(t("heads_up"))}</span> ${esc(t("small_sample", { n: c.n }))}</p>` : ""}
    <div class="row" style="gap:28px"><div class="kpi"><div class="v">${c.n}</div><div class="l">${esc(t("kpi_jobs"))}</div></div>
    <div class="kpi"><div class="v">${pct(c.entry)}</div><div class="l">${esc(t("entry_level"))}</div></div>
    ${c.fit != null ? `<div class="kpi"><div class="v">${pct(c.fit)}</div><div class="l">${esc(t("your_fit"))}</div></div>` : ""}</div>
    <p class="muted small" style="margin:16px 0 8px">${esc(t("typical"))}</p><div>${c.typical.map((x) => `<span class="pill">${esc(x)}</span>`).join("")}</div></section>`).join("");
  const dots = d.rows.map((r) => {
    const vals = d.chosen.map((id) => r.shares[id] || 0);
    const lo = Math.min(...vals), hi = Math.max(...vals);
    return `<span class="lab" title="${esc(r.name)}">${esc(r.name)}</span><div class="track"><span class="range" style="left:${lo * 100}%;width:${(hi - lo) * 100}%"></span>
      ${d.chosen.map((id) => { const c = d.cards.find((x) => x.id === id); return `<span class="pt" style="left:${(r.shares[id] || 0) * 100}%;background:${roleColor(id)}" title="${esc(c.label)}: ${pct(r.shares[id] || 0)}"></span>`; }).join("")}</div>`;
  }).join("");
  return `<div class="seg" role="group" aria-label="${esc(t("compare_pick"))}" style="flex-wrap:wrap;border-radius:22px;margin-bottom:10px">${toggles}</div>
    <p class="muted small" style="margin-bottom:28px">${esc(t("compare_hint"))}</p>
    <div class="grid cols-3" style="gap:30px;margin-bottom:44px">${cards}</div>
    <div class="row between" style="margin-bottom:8px"><h2 class="h2">${esc(t("same_skills"))}</h2>
      <div class="legend">${d.cards.map((c) => `<span><i style="background:${roleColor(c.id)};border-radius:99px"></i>${esc(c.label)}</span>`).join("")}</div></div>
    <p class="muted small" style="margin-bottom:18px">${esc(t("same_skills_help"))}</p>
    <div class="dots">${dots}</div><div class="axis" style="margin-top:6px"><div></div><div><span>0%</span><span>50%</span><span>100%</span></div></div>`;
}

async function marketRoles() {
  const { roles } = await api("/api/roles");
  const L = (r, k) => (S.lang === "en" && r[k + "_en"]) || r[k] || (Array.isArray(r[k]) ? [] : "");
  return `<p class="muted" style="max-width:70ch;margin-bottom:22px">${esc(t("roles_sub"))}</p>
    <form data-form="roles"><div class="list">${roles.map((r) => `<div class="item"><span style="width:12px;height:12px;border-radius:3px;background:${roleColor(r.id)};margin-top:7px;flex:none"></span>
      <div class="body"><div class="row" style="gap:10px"><span class="title">${esc(r.label)}</span><span class="muted small">${esc(t("in_db", { n: r.n }))}</span></div>
      <p class="muted small" style="margin-top:2px">${esc(r.custom ? t("custom_summary") : L(r, "summary"))}</p>
      ${r.custom ? "" : `<details class="more" style="margin-top:8px"><summary class="small">${esc(t("what_they_do"))}</summary><div class="stack" style="max-width:70ch">
        <p>${esc(L(r, "description"))}</p>
        <div><p class="small" style="font-weight:600;margin-bottom:6px">${esc(t("day_to_day"))}</p>${(L(r, "day_to_day") || []).map((x) => `<p class="small muted">${esc(x)}</p>`).join("")}</div>
        <div>${(L(r, "typical_skills") || []).map((x) => `<span class="pill">${esc(x)}</span>`).join("")}</div>
        <p class="tiny muted">${esc(t("searches_for", { x: (r.search_terms || []).join(", ") }))}</p></div></details>`}
      ${r.custom ? `<button class="btn sm ghost" type="button" data-act="role-remove" data-id="${esc(r.id)}" style="margin-top:6px;padding:0">${esc(t("remove"))}</button>` : ""}</div>
      <label class="switch" title="${esc(t("active"))}"><input type="checkbox" name="${esc(r.id)}" ${r.enabled ? "checked" : ""} aria-label="${esc(r.label)}"><span></span></label></div>`).join("")}</div>
    <div class="row" style="margin-top:20px"><button class="btn primary" type="submit">${esc(t("save_roles"))}</button></div></form>
    <form class="row" data-form="custom-role" style="margin-top:36px;align-items:flex-end"><label class="field" style="flex:1 1 320px"><span>${esc(t("custom_role"))}</span>
      <input type="text" name="name" placeholder="${esc(t("custom_role_ph"))}" required></label><button class="btn" type="submit">${icon("plus")}${esc(t("add_role"))}</button></form>`;
}

async function marketReport() {
  const d = await api("/api/report");
  if (d.empty) return noMarket();
  return `<div class="split"><div class="main"><p class="muted">${esc(t("post_help"))}</p>
      <textarea id="post" rows="16" style="font-size:16px">${esc(d.post)}</textarea>
      <div class="row"><button class="btn" type="button" data-act="copy-post">${icon("copy")}${esc(t("copy"))}</button></div></div>
    <aside class="side"><h2 class="h3">${esc(t("reports"))}</h2><p class="muted small">${esc(t("reports_help"))}</p>
      <button class="btn" type="button" data-act="report" data-public="1">${esc(t("report_public"))}</button>
      <button class="btn ghost" type="button" data-act="report" data-public="0">${esc(t("report_private"))}</button></aside></div>`;
}

// ============================================================================ page: jobs
async function pageJobs() {
  const j = S.jobs;
  const q = new URLSearchParams({ q: j.q, roles: j.role, region: j.region, seniority: j.seniority, skills: j.skill });
  const [d, roles] = await Promise.all([api(`/api/jobs?${q}`), api("/api/market")]);
  const filters = `<form class="row" data-form="jobs-filter" style="align-items:flex-end;margin-bottom:24px">
    <label class="field" style="flex:2 1 260px"><span>${esc(t("search"))}</span><input type="search" name="q" value="${esc(j.q)}" placeholder="${esc(t("search_ph"))}"></label>
    <label class="field" style="flex:1 1 200px"><span>${esc(t("role"))}</span><select name="role"><option value="">${esc(t("all"))}</option>${(roles.roles || []).map((r) => `<option value="${r.id}" ${j.role === r.id ? "selected" : ""}>${esc(r.label)}</option>`).join("")}</select></label>
    <label class="field" style="flex:1 1 170px"><span>${esc(t("region"))}</span><select name="region"><option value="">${esc(t("all_regions"))}</option>${(roles.regions || []).map((r) => `<option value="${r}" ${j.region === r ? "selected" : ""}>${esc(regionLabel(r))}</option>`).join("")}</select></label>
    <label class="field" style="flex:1 1 150px"><span>${esc(t("seniority"))}</span><select name="seniority"><option value="">${esc(t("any"))}</option>${["intern", "junior", "mid", "senior", "staff_plus"].map((k) => `<option value="${k}" ${j.seniority === k ? "selected" : ""}>${esc(seniorityLabel(k))}</option>`).join("")}</select></label>
    <label class="field" style="flex:1 1 200px"><span>${esc(t("asking_for"))}</span><select name="skill"><option value="">${esc(t("any_skill"))}</option>${d.skills.map((s) => `<option value="${esc(s.skill_id)}" ${j.skill === s.skill_id ? "selected" : ""}>${esc(s.name)}</option>`).join("")}</select></label>
    <button class="btn primary" type="submit">${esc(t("filter"))}</button></form>`;
  let detail = "";
  if (j.sel) {
    try {
      const x = await api(`/api/jobs/${encodeURIComponent(j.sel)}`);
      detail = `<aside class="side"><div class="panel stack" style="gap:14px;position:sticky;top:18px">
        <div class="row between"><span class="muted small">${esc(x.company)}</span><button class="btn icon ghost" type="button" data-act="job-close" aria-label="${esc(t("close"))}">${icon("x")}</button></div>
        <h2 class="h3">${esc(x.title)}</h2>
        <p class="muted small">${esc([seniorityLabel(x.seniority), regionLabel(x.region), x.source].join(" · "))}</p>
        ${x.required.length ? `<div><p class="small" style="font-weight:600;margin-bottom:6px">${esc(t("required_pl"))}</p>${x.required.map((s) => `<span class="pill">${esc(s)}</span>`).join("")}</div>` : ""}
        ${x.nice.length ? `<div><p class="small" style="font-weight:600;margin-bottom:6px">${esc(t("nice_pl"))}</p>${x.nice.map((s) => `<span class="pill">${esc(s)}</span>`).join("")}</div>` : ""}
        ${x.missing ? `<p class="small">${x.missing.length ? esc(t("you_miss", { x: x.missing.join(", ") })) : esc(t("you_miss_none"))}</p>` : ""}
        ${x.url ? `<a class="btn accent" href="${esc(x.url)}" target="_blank" rel="noopener">${icon("out")}${esc(t("open_job"))}</a>` : ""}
        <details class="more"><summary>${esc(t("full_text"))}</summary><div><p class="small" style="white-space:pre-wrap;max-height:420px;overflow:auto">${esc(x.text)}</p></div></details></div></aside>`;
    } catch (_) { j.sel = null; }
  }
  const rows = d.jobs.map((r) => `<tr class="clickable ${j.sel === r.job_key ? "sel" : ""}" data-act="job-open" data-key="${esc(r.job_key)}" tabindex="0">
    <td>${esc(r.company)}</td><td style="font-weight:550">${esc(r.title)}</td><td class="muted">${esc(seniorityLabel(r.seniority))}</td><td class="muted">${esc(regionLabel(r.region))}</td>
    <td class="muted num">${r.published_at ? esc(shortDate(isoDate(r.published_at))) : "—"}</td></tr>`).join("");
  return `${head(t("jobs_title"), t("jobs_sub", { n: d.total }))}${filters}
    <div class="split"><div class="main"><div class="table-wrap"><table><thead><tr><th>${esc(t("company"))}</th><th>${esc(t("title_col"))}</th><th>${esc(t("level"))}</th><th>${esc(t("region"))}</th><th>${esc(t("published"))}</th></tr></thead>
      <tbody>${rows || `<tr><td colspan="5" class="muted">${esc(S.shell.counts.jobs ? t("no_jobs_filter") : t("no_market"))}</td></tr>`}</tbody></table></div></div>${detail}</div>
    <details class="more" style="margin-top:34px"><summary>${esc(t("paste_job"))}</summary><div><form class="grid cols-3" data-form="paste-job" style="gap:16px">
      <label class="field"><span>${esc(t("title_col"))}</span><input type="text" name="title"></label>
      <label class="field"><span>${esc(t("company"))}</span><input type="text" name="company"></label>
      <label class="field"><span>${esc(t("link_opt"))}</span><input type="text" name="url"></label>
      <label class="field" style="grid-column:1/-1"><span>${esc(t("job_text"))}</span><textarea name="text" rows="8" required></textarea></label>
      <div><button class="btn primary" type="submit">${esc(t("add"))}</button></div></form></div></details>`;
}

// ============================================================================ page: profile (you, routine, preferences)
const PROFILE_TABS = [["voce", "tab_you"], ["rotina", "tab_routine"], ["preferencias", "tab_prefs"]];

async function pageProfile(sub) {
  const tab = PROFILE_TABS.some(([k]) => k === sub) ? sub : "voce";
  const body = await ({ voce: profileYou, rotina: profileRoutine, preferencias: profilePrefs })[tab]();
  return head(t("profile_title"), t("profile_sub")) + tabs("perfil", PROFILE_TABS, tab) + body;
}

async function profileYou() {
  const d = await api(`/api/profile?role=${encodeURIComponent(S.profileRole)}`);
  const resume = `<section class="panel stack" style="gap:14px"><h2 class="h3">${esc(t("resume"))}</h2>
    <p class="muted small">${esc(t("resume_privacy"))}</p>
    <form class="row" data-form="resume" style="align-items:flex-end"><label class="field" style="flex:1 1 280px"><span>${esc(t("resume_file"))}</span><input type="file" name="file" accept=".pdf,.docx,.md,.txt" required style="padding:9px"></label>
      <label class="row" style="gap:10px"><span class="switch"><input type="checkbox" name="use_ai" ${d.llm ? "checked" : ""}><span></span></span><span class="small">${esc(t("use_ai_levels"))}</span></label>
      <button class="btn primary" type="submit">${esc(t("read_resume"))}</button></form>
    ${d.has_profile ? `<p class="muted small">${esc(t("profile_current", { n: d.skills.length, m: d.method }))}</p>` : ""}</section>`;
  const fitMax = 1;
  const fit = d.fit.length ? `<section><h2 class="h2" style="margin-bottom:16px">${esc(t("fit_by_role"))}</h2><div class="hbars">${d.fit.sort((a, b) => b.fit - a.fit).map((f) => `<span class="lab">${esc(f.label)}</span>
    <div class="track"><span class="seg-1" style="width:${(f.fit / fitMax) * 88}%;${f.small ? "opacity:.45" : ""}"></span><span class="val">${pct(f.fit)}${f.small ? " · " + esc(t("few", { n: f.n })) : ""}</span></div>`).join("")}</div>
    <p class="muted small" style="margin-top:12px">${esc(t("fit_help"))}</p></section>` : "";
  const roleOpts = [["", t("all_roles_focus")], ...d.fit.map((f) => [f.id, f.label])];
  const gap = d.gap.length ? `<section><div class="row between" style="margin-bottom:12px"><h2 class="h2">${esc(t("gaps_title"))}</h2>
      <select data-change="pf-role" style="width:260px">${roleOpts.map(([id, l]) => `<option value="${esc(id)}" ${S.profileRole === id ? "selected" : ""}>${esc(l)}</option>`).join("")}</select></div>
    <p class="muted small" style="margin-bottom:14px">${esc(t("gaps_sub", { fit: pct(d.market_fit) }))}</p>
    <div class="table-wrap"><table><thead><tr><th>Skill</th><th>${esc(t("asked_in"))}</th><th>${esc(t("your_level"))}</th><th>${esc(t("status"))}</th><th>${esc(t("study_h"))}</th></tr></thead><tbody>
    ${d.gap.slice(0, 25).map((g) => `<tr><td style="font-weight:550">${esc(g.name)}</td><td class="num">${pct(g.share_any)}</td><td class="num">${g.level}</td>
      <td>${g.status === "has" ? `<span class="muted">${esc(t("status_has"))}</span>` : esc(t("status_" + g.status))}</td><td class="num muted">${esc(fh(g.effort_hours))}</td></tr>`).join("")}</tbody></table></div></section>` : "";
  const lvlRows = [...d.skills, ...(d.market_extra || []).map((x) => ({ ...x, evidence: t("asked_by_market") }))];
  const levels = d.has_profile ? `<section><h2 class="h2" style="margin-bottom:6px">${esc(t("levels_title"))}</h2><p class="muted small" style="margin-bottom:14px">${esc(t("levels_help"))}</p>
    <form data-form="levels"><div class="table-wrap"><table><thead><tr><th>Skill</th><th>${esc(t("level"))}</th><th>${esc(t("evidence"))}</th></tr></thead><tbody>
    ${lvlRows.map((s) => `<tr><td style="font-weight:550">${esc(s.name)}</td><td><div class="seg" role="group" aria-label="${esc(s.name)}">${[0, 1, 2, 3].map((n) => `<button type="button" data-act="lvl" data-skill="${esc(s.skill_id)}" data-v="${n}" aria-pressed="${s.level === n}">${n}</button>`).join("")}</div></td>
      <td class="muted small">${esc(s.evidence || "")}</td></tr>`).join("")}</tbody></table></div>
    <div class="row" style="margin-top:16px"><button class="btn primary" type="submit">${esc(t("save_levels"))}</button></div></form></section>` : "";
  return `<div class="stack" style="gap:44px">${resume}${fit}${gap}${levels}${!d.has_profile && !d.fit.length ? `<p class="muted">${esc(t("profile_empty"))}</p>` : ""}</div>`;
}

async function profileRoutine() {
  const d = await api("/api/routine");
  S.routine = d;
  const days = [0, 1, 2, 3, 4, 5, 6].map((i) => `<div class="item" style="align-items:center"><span class="body" style="font-weight:550">${esc(WEEKDAYS[S.lang][i][0].toUpperCase() + WEEKDAYS[S.lang][i].slice(1))}</span>
    <div class="stepper"><button type="button" data-act="rt-step" data-k="${i}" data-delta="-0.5" aria-label="${esc(t("less"))}">${icon("minus")}</button><output data-rt="${i}">${esc(fh(d.availability[String(i)] || 0))}</output>
    <button type="button" data-act="rt-step" data-k="${i}" data-delta="0.5" aria-label="${esc(t("more"))}">${icon("plus")}</button></div></div>`).join("");
  const total = Object.values(d.availability).reduce((a, b) => a + (+b || 0), 0);
  return `<div class="split"><div class="main">
      <section><h2 class="h2">${esc(t("routine_title"))}</h2><p class="muted" style="margin:8px 0 14px;max-width:62ch">${esc(t("routine_sub"))}</p>
        <div class="list">${days}</div><p class="muted small" style="margin-top:12px" data-rt-total>${esc(t("routine_total", { h: fh(total) }))}</p></section>
      <section><h2 class="h3">${esc(t("exceptions"))}</h2><p class="muted small" style="margin:6px 0 12px">${esc(t("exceptions_sub"))}</p>
        <div class="list">${d.overrides.map((o, i) => `<div class="item" style="align-items:center"><span class="body">${esc(longDate(isoDate(o.date)))}</span><span class="num">${esc(fh(o.hours))}</span>
          <button class="btn icon ghost" type="button" data-act="rt-ex-remove" data-i="${i}" aria-label="${esc(t("remove"))}">${icon("x")}</button></div>`).join("") || `<p class="muted small">${esc(t("no_exceptions"))}</p>`}</div>
        <form class="row" data-form="exception" style="align-items:flex-end;margin-top:14px"><label class="field" style="width:200px"><span>${esc(t("day"))}</span><input type="date" name="date" required min="${esc(S.shell.today)}"></label>
          <label class="field" style="width:150px"><span>${esc(t("free_hours"))}</span><input type="number" name="hours" min="0" max="16" step="0.5" value="0"></label>
          <button class="btn" type="submit">${icon("plus")}${esc(t("add_exception"))}</button></form></section>
    </div>
    <aside class="side"><div class="panel stack" style="gap:16px"><h2 class="h3">${esc(t("blocks_title"))}</h2><p class="muted small">${esc(t("blocks_sub"))}</p>
      <div class="row between"><span>${esc(t("max_block"))}</span><div class="stepper"><button type="button" data-act="rt-max" data-delta="-0.5" aria-label="${esc(t("less"))}">${icon("minus")}</button>
      <output data-rt-max>${esc(fh(d.max_block))}</output><button type="button" data-act="rt-max" data-delta="0.5" aria-label="${esc(t("more"))}">${icon("plus")}</button></div></div>
      <button class="btn primary" type="button" data-act="rt-save">${esc(t("save_routine"))}</button>
      <p class="muted small">${esc(t("study_hours_where", { h: fh((d.focus || {}).weekly_hours || 10) }))} <a href="#/estudos">${esc(t("nav_study"))}</a>.</p></div></aside></div>`;
}

async function profilePrefs() {
  const s = S.shell.settings;
  return `<div class="grid cols-2" style="gap:44px">
    <section class="stack" style="gap:22px"><h2 class="h2">${esc(t("prefs_title"))}</h2>
      <div class="row between"><span>${esc(t("theme"))}</span><div class="seg"><button type="button" data-act="theme" data-v="dark" aria-pressed="${S.theme === "dark"}">${esc(t("theme_dark"))}</button><button type="button" data-act="theme" data-v="light" aria-pressed="${S.theme === "light"}">${esc(t("theme_light"))}</button></div></div>
      <div class="row between"><span>${esc(t("language"))}</span><div class="seg"><button type="button" data-act="lang" data-v="pt" aria-pressed="${S.lang === "pt"}">Português</button><button type="button" data-act="lang" data-v="en" aria-pressed="${S.lang === "en"}">English</button></div></div>
      <label class="row between"><span>${esc(t("auto_update"))}<br><span class="muted small">${esc(t("auto_update_help"))}</span></span><span class="switch"><input type="checkbox" data-change="auto-update" ${s.auto_update_on_open ? "checked" : ""}><span></span></span></label>
      <div class="row between"><span>${esc(t("ai_status"))}</span><span class="muted">${esc(S.shell.llm || t("no_key"))}</span></div>
      ${S.shell.llm ? "" : `<p class="muted small">${esc(t("no_key_help"))}</p>`}
    </section>
    <section class="stack" style="gap:16px"><h2 class="h2">${esc(t("shortcuts"))}</h2>
      ${[["Ctrl K", "sc_capture"], ["C", "sc_done"], ["N", "sc_next"], ["?", "sc_help"]].map(([k, key]) => `<div class="row between"><span>${esc(t(key))}</span><span class="kbd">${esc(k)}</span></div>`).join("")}
      <div class="rule" style="padding-top:20px;margin-top:10px"><button class="btn" type="button" data-act="quit">${esc(t("quit"))}</button><p class="muted small" style="margin-top:10px">${esc(t("quit_help"))}</p></div>
    </section></div>`;
}

const PAGES = { hoje: pageToday, semana: pageWeek, projetos: pageProjects, estudos: pagePlan, mercado: pageMarket, vagas: pageJobs, perfil: pageProfile };

// ============================================================================ capture dialog (plain language → project draft)
function renderCapture() {
  const dlg = $("#capture");
  const c = S.capture || { step: "write", text: "" };
  if (c.step === "write" || c.step === "loading") {
    dlg.innerHTML = `<form class="dlg" data-form="capture-text">
      <h2 class="h2" id="capture-title">${esc(t("capture_title"))}</h2>
      <p class="muted">${esc(t("capture_sub"))}</p>
      <textarea name="text" required placeholder="${esc(t("capture_ph"))}" ${c.step === "loading" ? "disabled" : ""}>${esc(c.text)}</textarea>
      <p class="muted small">${esc(S.shell.llm ? t("capture_ai") : t("capture_rules"))}</p>
      <div class="row"><button class="btn accent" type="submit" ${c.step === "loading" ? "disabled" : ""}>${esc(c.step === "loading" ? t("capture_loading") : t("capture_go"))}</button>
      <button class="btn ghost" type="button" data-act="capture-close">${esc(t("cancel"))}</button><span class="muted tiny" style="margin-left:auto">Esc</span></div></form>`;
  } else {
    const p = c.draft;
    dlg.innerHTML = `<form class="dlg" data-form="capture-save">
      <h2 class="h2" id="capture-title">${esc(t("capture_review"))}</h2>
      <p class="muted small">${esc(p.method === "llm" ? t("capture_by_ai") : t("capture_by_rules"))}</p>
      <label class="field"><span>${esc(t("p_name"))}</span><input type="text" name="name" value="${esc(p.name)}" required></label>
      <div class="grid cols-3" style="gap:14px;grid-template-columns:repeat(auto-fit,minmax(150px,1fr))">
        <label class="field"><span>${esc(t("p_area"))}</span><select name="area">${areaOptions(p.area)}</select></label>
        <label class="field"><span>${esc(t("p_deadline"))}</span><input type="date" name="deadline" value="${esc(p.deadline || "")}"></label>
        <label class="field"><span>${esc(t("p_priority"))}</span><select name="priority">${prioOptions(p.priority)}</select></label></div>
      <div><p class="small" style="font-weight:600;margin-bottom:8px">${esc(t("p_tasks_plain"))}</p>
        <div class="stack" style="gap:8px" data-draft-tasks>${p.tasks.map((tk) => `<div class="row" style="flex-wrap:nowrap" data-dt><input type="text" name="tt" value="${esc(tk.title)}" aria-label="${esc(t("t_title"))}">
          <input type="number" name="th" min="0.5" max="200" step="0.5" value="${tk.hours}" style="width:96px" aria-label="${esc(t("t_hours"))}"><button class="btn icon ghost" type="button" data-act="dt-remove" aria-label="${esc(t("remove"))}">${icon("x")}</button></div>`).join("")}</div>
        <button class="btn sm ghost" type="button" data-act="dt-add" style="margin-top:8px;padding:0">${icon("plus")}${esc(t("t_add"))}</button></div>
      <div class="row"><button class="btn accent" type="submit">${esc(t("capture_save"))}</button><button class="btn ghost" type="button" data-act="capture-back">${esc(t("back"))}</button></div></form>`;
  }
}
function openCapture(text = "") {
  S.capture = { step: "write", text };
  renderCapture();
  const dlg = $("#capture");
  if (!dlg.open) dlg.showModal();
  setTimeout(() => dlg.querySelector("textarea")?.focus(), 30);
}

// ============================================================================ actions
async function refresh(keepScroll = true) {
  const y = window.scrollY;
  await loadShell();
  await render();
  if (keepScroll) window.scrollTo(0, y);
}

async function logBlock(item, hours, title) {
  await api("/api/log", { method: "POST", body: { item, hours } });
  S.lastLog = item; S.partial = false; S.skipped.delete(item);
  await refresh();
  toast(t("logged", { h: fh(hours), what: title }), { action: t("undo"), onAction: async () => {
    await api("/api/undo", { method: "POST", body: { item } }); await refresh(); toast(t("undone"));
  } });
}

function pollUpdate() {
  if (S.polling) return;
  S.polling = setInterval(async () => {
    try {
      const u = await api("/api/update");
      S.shell.update = u.status; S.shell.last_update = u.last_update;
      renderTop();
      if (u.status.state !== "running") {
        clearInterval(S.polling); S.polling = null;
        if (u.status.state === "done") toast(t("update_done")); else if (u.status.state === "failed") toast(t("update_failed", { err: u.status.error || "" }), { error: true, ms: 10000 });
        await refresh();
      }
    } catch (_) { /* server restarting: try again */ }
  }, 2000);
}

const ACTIONS = {
  "capture-open": () => openCapture(),
  "capture-close": () => $("#capture").close(),
  "capture-back": () => { S.capture.step = "write"; renderCapture(); },
  "dt-add": () => { const box = $("[data-draft-tasks]"); box.insertAdjacentHTML("beforeend", `<div class="row" style="flex-wrap:nowrap" data-dt><input type="text" name="tt" aria-label="${esc(t("t_title"))}"><input type="number" name="th" min="0.5" max="200" step="0.5" value="1" style="width:96px" aria-label="${esc(t("t_hours"))}"><button class="btn icon ghost" type="button" data-act="dt-remove" aria-label="${esc(t("remove"))}">${icon("x")}</button></div>`); box.lastElementChild.querySelector("input").focus(); },
  "dt-remove": (el) => el.closest("[data-dt]").remove(),
  theme: async (el) => {
    S.theme = el.dataset.v; document.documentElement.dataset.theme = S.theme;
    await api("/api/settings", { method: "PUT", body: { theme: S.theme } }); S.shell.settings.theme = S.theme; await render();
  },
  lang: async (el) => { await api("/api/settings", { method: "PUT", body: { lang: el.dataset.v } }); await refresh(); },
  update: async () => {
    const r = await api("/api/update", { method: "POST" }); S.shell.update = r.status; renderTop();
    toast(r.started ? t("update_started") : t("update_running")); pollUpdate();
  },
  quit: async () => { await api("/api/quit", { method: "POST" }); main().innerHTML = `<div class="empty"><h1 class="display">${esc(t("bye_title"))}</h1><p class="muted">${esc(t("bye"))}</p></div>`; },
  done: (el) => logBlock(el.dataset.item, +el.dataset.hours, el.dataset.title),
  "partial-toggle": async () => { S.partial = !S.partial; await render(); $("[data-form=partial] input")?.focus(); },
  skip: async (el) => { S.skipped.add(el.dataset.item); await render(); },
  free: async (el) => {
    const v = Math.max(0, Math.min(16, (S.today?.free || 0) + +el.dataset.delta));
    await api("/api/free-today", { method: "PUT", body: { hours: v } }); await refresh();
  },
  borrow: async (el) => {
    await api("/api/borrow", { method: "POST", body: { foco: el.dataset.foco, hours: +el.dataset.hours } });
    await refresh(); toast(t("borrowed", { h: fh(+el.dataset.hours), foco: areaLabel(el.dataset.foco).toLowerCase(), task: el.dataset.task }));
  },
  "new-open": async () => { S.newProject = true; await render(); $("[data-form=new-project] input")?.focus(); },
  "new-cancel": async () => { S.newProject = false; await render(); },
  edit: async (el) => { S.editing = el.dataset.id; await render(); },
  "edit-cancel": async () => { S.editing = null; await render(); },
  archive: async (el) => { await api(`/api/projects/${el.dataset.id}`, { method: "PUT", body: { archived: true } }); await refresh();
    toast(t("archived_toast"), { action: t("undo"), onAction: async () => { await api(`/api/projects/${el.dataset.id}`, { method: "PUT", body: { archived: false } }); await refresh(); } }); },
  unarchive: async (el) => { await api(`/api/projects/${el.dataset.id}`, { method: "PUT", body: { archived: false } }); await refresh(); },
  delete: async (el) => { S.confirmDel = el.dataset.id; await render(); setTimeout(async () => { if (S.confirmDel === el.dataset.id) { S.confirmDel = null; if (route().page === "projetos") await render(); } }, 5000); },
  "delete-confirm": async (el) => { await api(`/api/projects/${el.dataset.id}`, { method: "DELETE" }); S.confirmDel = null; await refresh(); toast(t("deleted")); },
  "task-add": (el) => {
    const tb = el.closest("form").querySelector("tbody");
    tb.insertAdjacentHTML("beforeend", `<tr data-task=""><td style="width:44px"><input type="checkbox" name="done" aria-label="${esc(t("t_done"))}"></td><td><input type="text" name="title" aria-label="${esc(t("t_title"))}"></td>
      <td style="width:110px"><input type="number" name="hours" min="0.5" max="200" step="0.5" value="1" aria-label="${esc(t("t_hours"))}"></td><td style="width:170px"><input type="date" name="due" aria-label="${esc(t("t_due"))}"></td><td></td>
      <td style="width:48px"><button class="btn icon ghost" type="button" data-act="task-remove" aria-label="${esc(t("remove"))}">${icon("x")}</button></td></tr>`);
    tb.lastElementChild.querySelector("[name=title]").focus();
  },
  "task-remove": (el) => el.closest("tr").remove(),
  "plan-generate": async (el) => {
    el.disabled = true; el.textContent = t("plan_generating");
    await api("/api/plan", { method: "POST", body: { ideas: $("#ideas")?.checked ?? false } }); await refresh(); toast(t("plan_done"));
  },
  "plan-project": async (el) => {
    const p = S.planProjects[+el.dataset.i]; el.disabled = true;
    await api("/api/plan/project", { method: "POST", body: { title: p.title, description: p.description } }); await refresh(); toast(t("p_created", { name: p.title }));
  },
  "mk-role": async (el) => { S.market.role = el.dataset.v; S.market.picked = null; await render(); },
  "mk-sen": async (el) => { const k = el.dataset.v, s = S.market.seniority; S.market.seniority = s.includes(k) ? s.filter((x) => x !== k) : [...s, k]; await render(); },
  "mk-skill": async (el) => { S.market.picked = el.dataset.v || null; await render(); },
  "cmp-role": async (el) => {
    const id = el.dataset.v, c = S.compare;
    if (c.includes(id)) { if (c.length > 2) S.compare = c.filter((x) => x !== id); else toast(t("pick_two")); }
    else { if (c.length >= 3) toast(t("max_three")); else S.compare = [...c, id]; }
    await render();
  },
  "role-remove": async (el) => { await api(`/api/roles/custom/${el.dataset.id}`, { method: "DELETE" }); await refresh(); },
  "copy-post": async () => { try { await navigator.clipboard.writeText($("#post").value); toast(t("copied")); } catch (_) { $("#post").select(); } },
  report: async (el) => { const r = await api("/api/report", { method: "POST", body: { public: el.dataset.public === "1" } }); toast(t("saved_in", { p: r.saved }), { ms: 8000 }); },
  "job-open": async (el) => { S.jobs.sel = el.dataset.key; await render(); },
  "job-close": async () => { S.jobs.sel = null; await render(); },
  lvl: (el) => { el.parentElement.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b === el))); },
  "rt-step": (el) => {
    const k = el.dataset.k, av = S.routine.availability;
    av[k] = Math.max(0, Math.min(16, (+av[k] || 0) + +el.dataset.delta));
    $(`[data-rt="${k}"]`).textContent = fh(av[k]);
    $("[data-rt-total]").textContent = t("routine_total", { h: fh(Object.values(av).reduce((a, b) => a + (+b || 0), 0)) });
  },
  "rt-max": (el) => { S.routine.max_block = Math.max(0.5, Math.min(6, S.routine.max_block + +el.dataset.delta)); $("[data-rt-max]").textContent = fh(S.routine.max_block); },
  "rt-save": async () => { await api("/api/routine", { method: "PUT", body: { availability: S.routine.availability, max_block: S.routine.max_block } }); await refresh(); toast(t("saved")); },
  "rt-ex-remove": async (el) => {
    const ov = S.routine.overrides.filter((_, i) => i !== +el.dataset.i);
    await api("/api/routine", { method: "PUT", body: { overrides: ov } }); await refresh();
  },
};

const FORMS = {
  partial: async (f) => { const n = S.today.blocks.find((b) => !S.skipped.has(b.item)) || S.today.blocks[0]; await logBlock(n.item, +f.hours.value, n.title); },
  "capture-text": async (f) => {
    const text = f.text.value.trim(); if (!text) return;
    S.capture = { step: "loading", text }; renderCapture();
    try { S.capture = { step: "review", text, draft: await api("/api/capture", { method: "POST", body: { text } }) }; }
    catch (e) { S.capture = { step: "write", text }; fail(e); }
    renderCapture();
  },
  "capture-save": async (f) => {
    const tasks = [...f.querySelectorAll("[data-dt]")].map((r) => ({ title: r.querySelector("[name=tt]").value, hours: +r.querySelector("[name=th]").value || 1 })).filter((x) => x.title.trim());
    const body = { name: f.name.value, area: f.area.value, deadline: f.deadline.value || null, priority: +f.priority.value,
      hours: tasks.reduce((s, x) => s + x.hours, 0) || S.capture.draft.hours, tasks };
    await api("/api/projects", { method: "POST", body });
    $("#capture").close(); toast(t("p_created", { name: body.name }));
    if (route().page !== "projetos" && route().page !== "hoje") location.hash = "#/hoje"; else await refresh();
  },
  "new-project": async (f) => {
    const body = { name: f.name.value, area: f.area.value, deadline: f.deadline.value || null, priority: +f.priority.value, hours: +f.hours.value, notes: f.notes.value, breakdown: f.breakdown.checked };
    await api("/api/projects", { method: "POST", body }); S.newProject = false; await refresh(); toast(t("p_created", { name: body.name }));
  },
  "edit-project": async (f) => {
    await api(`/api/projects/${f.dataset.id}`, { method: "PUT", body: { name: f.name.value, area: f.area.value, deadline: f.deadline.value || null, priority: +f.priority.value, hours: +f.hours.value, notes: f.notes.value } });
    S.editing = null; await refresh(); toast(t("saved"));
  },
  tasks: async (f) => {
    const tasks = [...f.querySelectorAll("tbody tr")].map((r) => ({ id: r.dataset.task || null, title: r.querySelector("[name=title]").value,
      hours: +r.querySelector("[name=hours]").value || 1, due: r.querySelector("[name=due]").value || null, done: r.querySelector("[name=done]").checked }));
    S.openProject = f.dataset.id;
    await api(`/api/projects/${f.dataset.id}`, { method: "PUT", body: { tasks } }); await refresh(); toast(t("saved"));
  },
  focus: async (f) => {
    const split = (v) => v.split(",").map((x) => x.trim()).filter(Boolean);
    await api("/api/focus", { method: "PUT", body: { weekly_hours: +f.weekly_hours.value, protected: f.protected.checked, topics: split(f.topics.value), interests: split(f.interests.value),
      weights: { carreira: +f.carreira.value, exploracao: +f.exploracao.value, interesses: +f.interesses.value } } });
    await refresh(); toast(t("focus_saved"));
  },
  roles: async (f) => {
    const enabled = [...f.querySelectorAll("input[type=checkbox]")].filter((x) => x.checked).map((x) => x.name);
    if (!enabled.length) return toast(t("roles_none"), { error: true });
    const r = await api("/api/roles", { method: "PUT", body: { enabled } }); await refresh(); toast(t("roles_saved", { n: enabled.length, m: r.relabeled }), { ms: 8000 });
  },
  "custom-role": async (f) => { await api("/api/roles/custom", { method: "POST", body: { name: f.name.value } }); await refresh(); toast(t("role_created", { n: f.name.value }), { ms: 8000 }); },
  "jobs-filter": async (f) => { Object.assign(S.jobs, { q: f.q.value, role: f.role.value, region: f.region.value, seniority: f.seniority.value, skill: f.skill.value, sel: null }); await render(); },
  "paste-job": async (f) => { const r = await api("/api/jobs", { method: "POST", body: { title: f.title.value, company: f.company.value, url: f.url.value, text: f.text.value } }); f.reset(); toast(t("job_added", { t: r.title }), { ms: 8000 }); },
  resume: async (f) => {
    const fd = new FormData(); fd.append("file", f.file.files[0]);
    const btn = f.querySelector("button[type=submit]"); btn.disabled = true; btn.textContent = t("reading");
    const r = await api(`/api/profile/resume?use_ai=${f.use_ai.checked}`, { method: "POST", body: fd }); await refresh(); toast(t("skills_found", { n: r.skills }));
  },
  levels: async (f) => {
    const levels = {}; f.querySelectorAll("[aria-pressed=true][data-skill]").forEach((b) => { levels[b.dataset.skill] = +b.dataset.v; });
    await api("/api/profile/levels", { method: "PUT", body: { levels } }); await refresh(); toast(t("levels_saved"));
  },
  exception: async (f) => {
    const ov = [...S.routine.overrides, { date: f.date.value, hours: +f.hours.value }];
    await api("/api/routine", { method: "PUT", body: { overrides: ov } }); await refresh(); toast(t("saved"));
  },
};

const CHANGES = {
  "mk-region": async (el) => { S.market.region = el.value; S.market.picked = null; await render(); },
  "mk-top": async (el) => { S.market.top = +el.value; await render(); },
  "pf-role": async (el) => { S.profileRole = el.value; await render(); },
  "auto-update": async (el) => { await api("/api/settings", { method: "PUT", body: { auto_update_on_open: el.checked } }); S.shell.settings.auto_update_on_open = el.checked; toast(t("saved")); },
};

document.addEventListener("click", async (e) => {
  const el = e.target.closest("[data-act]");
  if (!el || el.disabled) return;
  const fn = ACTIONS[el.dataset.act];
  if (!fn) return;
  e.preventDefault();
  try { await fn(el, e); } catch (err) { fail(err); }
});
document.addEventListener("keydown", async (e) => {
  const el = e.target.closest && e.target.closest("tr[data-act]");
  if (el && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); try { await ACTIONS[el.dataset.act](el); } catch (err) { fail(err); } return; }
  const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName || "") || $("#capture").open;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openCapture(); return; }
  if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
  const { page } = route();
  if (page === "hoje" && e.key.toLowerCase() === "c") { const b = $(".slab [data-act=done]"); if (b) { e.preventDefault(); b.click(); } }
  if (page === "hoje" && e.key.toLowerCase() === "n") { const b = $(".slab [data-act=skip]"); if (b && !b.disabled) { e.preventDefault(); b.click(); } }
  if (e.key === "?") { location.hash = "#/perfil/preferencias"; }
});
document.addEventListener("submit", async (e) => {
  const f = e.target.closest("[data-form]");
  if (!f || !FORMS[f.dataset.form]) return;
  e.preventDefault();
  try { await FORMS[f.dataset.form](f); } catch (err) { fail(err); }
});
document.addEventListener("change", async (e) => {
  const el = e.target.closest("[data-change]");
  if (!el || !CHANGES[el.dataset.change]) return;
  try { await CHANGES[el.dataset.change](el); } catch (err) { fail(err); }
});
document.addEventListener("input", (e) => {
  const el = e.target.closest("[data-live]");
  if (el) { const o = $(`[data-out="${el.dataset.live}"]`); if (o) o.textContent = el.value; }
});
document.addEventListener("toggle", (e) => { if (e.target.matches && e.target.matches("details.more[data-id]")) S.openProject = e.target.open ? e.target.dataset.id : null; }, true);
$("#capture").addEventListener("close", () => { S.capture = null; });
window.addEventListener("hashchange", async () => { S.partial = false; S.editing = null; S.newProject = false; await render(); main().focus({ preventScroll: true }); window.scrollTo(0, 0); });

(async function boot() {
  try {
    await loadShell();
    await render();
    if (S.shell.update?.state === "running") pollUpdate();
  } catch (e) {
    main().innerHTML = `<div class="empty"><h1 class="h1">Waypoint</h1><p class="muted">${esc(e.message)}</p></div>`;
  }
})();
