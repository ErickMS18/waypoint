<p align="center"><img src="assets/cover.png" alt="Waypoint — AI career radar" width="820"></p>

# Waypoint — an LLM-powered career radar for data & AI roles

[![tests](https://github.com/ErickMS18/waypoint/actions/workflows/tests.yml/badge.svg)](https://github.com/ErickMS18/waypoint/actions/workflows/tests.yml)
![python](https://img.shields.io/badge/python-3.11%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

**Waypoint answers one question with real data: _"what does the market actually ask for in the roles I want,
what am I missing, and what should I study this week?"_**

It collects real job postings from public job-board APIs, uses an LLM to turn each posting into structured data
(skills, required vs. nice-to-have, seniority), compares the market with your resume and builds a weekly study plan.
Extraction quality is measured against a labeled gold set, and the numbers are in this README.

> I built it for my own job search (AI/ML Engineer, Data Scientist, BI/Analytics Engineer, MLOps), and I use it every week.

## What it found (snapshot, Nov 2026)

**360 postings · 180 companies · 5 roles · Brazil + remote-friendly international** (one click refreshes them):

| Role | Postings | Most requested skills (share of postings) |
|---|---:|---|
| AI/ML Engineer (LLM/GenAI) | 177 | Python 68% · AI agents & tool use 54% · LLMs 53% · Machine Learning 40% · RAG 40% |
| Data Scientist | 104 | Python 90% · SQL 74% · Machine Learning 68% · Statistics 52% · A/B testing 35% |
| BI Developer / BI Analyst | 43 | Power BI/DAX 79% · SQL 74% · Excel 51% · Data modeling 47% · ETL/ELT 42% |
| Analytics Engineer | 24 | SQL 100% · Python 79% · dbt 71% · Data modeling 54% · Tableau/Looker 54% |
| MLOps Engineer | 12 | Python 92% · CI/CD 58% · AWS 50% · Infrastructure as code 50% · Kubernetes 42% |

Small samples (MLOps, Analytics Engineer) are flagged as unstable in the app; they grow with each weekly refresh.

<p align="center"><img src="assets/screenshots/market.png" alt="Market page: most requested skills, required vs nice-to-have" width="900"></p>

## What it does

| | |
|---|---|
| **Market radar** | Most requested skills per role (required vs. nice-to-have), Brazil vs. international, seniority mix, rising skills over time. Click a bar to see the postings behind it. |
| **Role comparison** | The same skills side by side across up to 3 roles, plus what is *typical* of each role. Useful to decide between, say, BI and Analytics Engineering. |
| **Gap analysis** | Reads your resume (PII redacted first), scores your level per skill (0–3, editable) and ranks gaps by `demand × (1 − coverage)`. |
| **Weekly plan** | Splits your weekly hours by focus weights (career / exploration / personal interests). Exploration time is protected; nothing is ever called "irrelevant": conflicts become explicit trade-offs. Check items off as you go. |
| **Job explorer** | Filter postings by role, region, seniority and skills; open one to see what it asks for and what you still don't cover. |
| **Role catalog** | Each role comes with a plain-language description. Turn roles on/off or create a custom role from a job title. |
| **One-click app** | A desktop shortcut opens the app without a terminal; the **Update** button collects, extracts and re-plans in the background. |

<p align="center"><img src="assets/screenshots/compare.png" alt="Compare roles: AI/ML Engineer vs Data Scientist vs BI" width="900"></p>

The interface is in Portuguese (it is my personal tool); code, docs and the evaluation are in English.

## How it works

```mermaid
flowchart LR
    subgraph Sources["Public sources (read-only APIs)"]
      GH[Greenhouse]
      LV[Lever]
      ASH[Ashby]
      HM["Himalayas<br/>remote, open to Brazil"]
      GP["Gupy<br/>opt-in, local only"]
      IN["Postings you paste"]
    end
    Sources --> N["Normalize · role match by title regex · near-duplicate removal"] --> DB[("SQLite")]
    DB --> X{Extractor}
    X -->|"LLM → JSON → Pydantic (cached)"| C["Canonicalize to a 101-skill taxonomy"]
    X -->|dictionary baseline| C
    C --> M["Market stats<br/>demand = required + 0.5 · nice"]
    CV[Resume] --> R[Redact PII] --> P["Skill levels 0–3<br/>+ manual overrides"]
    M & P --> G["Gap = demand × (1 − coverage)"]
    G --> PL["Weekly plan<br/>focus weights · protected exploration · trade-offs"]
    M & G & PL --> UI["Streamlit app · Markdown report · charts"]
```

### Engineering decisions (the parts I'd talk about in an interview)

| Decision | Why |
|---|---|
| **Official public APIs, not scraping** | Stable JSON, no login, allowed by the providers. LinkedIn and Indeed are excluded because their terms forbid automated collection. |
| **LLM output → Pydantic schema → closed taxonomy** | Free text ("Py", "python3", "Python 3.x") maps to one id, so counts mean something. Unknown skills are kept as `other:*` and surface as possible emerging topics. Invalid JSON gets one repair retry. |
| **A dictionary baseline next to the LLM** | Gives the evaluation a reference point and keeps the tool useful with no API key. It turned out to be a strong baseline (see below). |
| **Provider-agnostic LLM client over plain HTTP** | Gemini, Anthropic, OpenAI or any OpenAI-compatible endpoint (Ollama for fully local). One `.env` line to switch. Throttling and 429/503 backoff built in. |
| **Content-hash cache for every LLM call** | Re-runs are free; only new or changed postings are sent. A full weekly refresh costs a few dozen calls. |
| **Background updater + status file** | The UI never blocks: the update runs in a window-less process and reports progress in a JSON file the page polls. Closing the browser doesn't kill it; a dead process is detected instead of showing "running" forever. |
| **Roles as data, not code** | A YAML catalog (title regexes, search terms, descriptions). Turning a role off hides it without deleting data; postings are re-labeled when the catalog changes. |
| **Small-sample guardrails** | Per-role percentages are flagged when a role has fewer than 10 postings, and trends need ≥ 10 recent and ≥ 10 older postings. |
| **Privacy enforced by tests** | A test fails if `.env`, `data/`, `profile/`, `reports/` or local configs stop being git-ignored. |

## Evaluation

Extraction quality is measured against a labeled gold set of **real postings** (stratified by role and language,
at most 3 per company). Labels follow [eval/GUIDELINES.md](eval/GUIDELINES.md). The metric is micro
precision/recall/F1 over `(posting, skill)` pairs in the closed taxonomy, with a 95% bootstrap confidence interval
over postings. "F1 incl. required/nice" only counts a hit if the requirement level also matches.

<!-- EVAL:START -->
Gold set: **40 real job postings** (20 AI/ML Engineer (LLM/GenAI), 20 Data Scientist; 20 EN, 20 PT), labeled with 618 skill labels from a 101-skill taxonomy. Evaluated on 2026-11-21.

| Extractor | Skill P | Skill R | Skill F1 (95% CI) | F1 incl. required/nice | Seniority acc. | Unmapped |
|---|---:|---:|---:|---:|---:|---:|
| Dictionary baseline | 0.92 | 0.80 | **0.85** (0.83–0.88) | 0.77 | 0.90 | 0% |
| LLM (gemini/gemini-3.5-flash-lite) | 0.97 | 0.73 | **0.83** (0.80–0.86) | 0.80 | 0.97 | 1% |

Skill F1 by posting language:

| Extractor | EN (n=20) | PT (n=20) |
|---|---:|---:|
| Dictionary baseline | 0.83 | 0.87 |
| LLM (gemini/gemini-3.5-flash-lite) | 0.80 | 0.86 |
<!-- EVAL:END -->

**How to read these numbers**

- The LLM is the more *precise* extractor (0.97: when it says a posting asks for a skill, it almost always does) and is better at telling required from nice-to-have and at seniority. The baseline has higher recall because it matches every alias it sees. On this closed-vocabulary metric they tie within the confidence interval; the app uses the LLM output and keeps the baseline as a fallback.
- **How the gold set was built:** 40 postings drawn by `waypoint eval sample` (seed 42) on 2026-11-21: 20 AI/ML Engineer + 20 Data Scientist, 20 English + 20 Portuguese. Labels were drafted by an AI assistant (Claude) following the guidelines, without seeing any extractor output, and are marked `pending human review` in `eval/gold.jsonl`.
- The taxonomy was frozen (96 skills) before labeling. Five skills were added later for the new BI/MLOps roles (SSIS/SSAS/SSRS, Fabric/Synapse, KPI definition, model serving, ETL tools); the scores above were re-run after that change, and predictions of those new skills count as false positives because the gold labels predate them.
- Postings for the three newer roles (BI, Analytics Engineer, MLOps) are not in the gold set yet; extending it is on the roadmap.

Reproduce:

```powershell
waypoint eval fetch                 # re-downloads the gold postings that are still online
waypoint eval run --update-readme   # baseline + LLM, writes eval/RESULTS.md and eval/results/*.json
```

The repository contains only labels and posting ids/URLs (`eval/gold.jsonl`), never the posting texts.

## Quickstart

### Windows, one click

1. Install Python 3.11+ and clone the repo (or download the ZIP).
2. Optional but recommended: create `.env` with a free Gemini key: `GEMINI_API_KEY=...` (see `.env.example`).
3. Put your resume (PDF/DOCX) in `profile/`, or upload it later in the app.
4. Double-click **`RODAR_WAYPOINT.bat`**. It creates the environment, collects postings, runs the extraction,
   the evaluation and the tests, and creates a **Waypoint** shortcut on the Desktop and in the Start menu.

From then on, just open the **Waypoint** shortcut: it starts the app in the background (no terminal window),
opens the browser and, if the data is more than a day old, refreshes it automatically. The **Atualizar tudo**
button refreshes on demand; **Encerrar Waypoint** shuts it down.

### Any OS, command line

```bash
git clone https://github.com/ErickMS18/waypoint.git && cd waypoint
python -m venv .venv && source .venv/bin/activate      # Windows: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

waypoint init                    # creates data/, profile/, reports/ and .env
waypoint profile path/to/resume.pdf
waypoint update                  # collect → extract (LLM + baseline) → plan → reports
waypoint ui                      # opens the app (runs in the background)
waypoint report --public         # market-only report, safe to share
```

Other commands: `waypoint boards check`, `collect`, `extract [--extractor baseline]`, `analyze`, `add` (paste a posting), `eval sample|fetch|run`.

## Configuration

| File | What it controls |
|---|---|
| `config/targets.yaml` | Which roles are on (`roles_enabled`), custom roles, the seniority you are aiming for. |
| `src/waypoint/resources/roles_catalog.yaml` | The role catalog: descriptions, search terms and title regexes. |
| `config/sources.yaml` | Which sources are on and which companies (boards) to read. |
| `config/focus.yaml` | Weekly hours, focus weights, exploration topics, personal interests. |
| `config/*.local.yaml` | Your machine-only overrides (written by the app; git-ignored). |
| `.env` | `LLM_PROVIDER`, `LLM_MODEL` and the key. Never committed. |

## Sources and compliance

| Source | Access | Notes |
|---|---|---|
| [Greenhouse Job Board API](https://developers.greenhouse.io/job-board.html) | Public GET, no auth | Company board tokens in `config/sources.yaml`. |
| [Lever Postings API](https://github.com/lever/postings-api) | Public GET, no auth | US and EU hosts handled automatically. |
| [Ashby Job Postings API](https://developers.ashbyhq.com/docs/public-job-posting-api) | Public GET, no auth | |
| [Himalayas Remote Jobs API](https://himalayas.app/docs/remote-jobs-api) | Public, free | Remote roles open to people in Brazil. Attribution shown in reports; data not redistributed. |
| Gupy portal search | Undocumented endpoint | **Off by default.** Gupy's terms forbid aggregating platform content; if you enable it locally, use it for personal analysis only and publish only aggregate numbers. |
| Pasted postings | You | Anything you found elsewhere (LinkedIn, InfoJobs…), pasted in the app or dropped in `inbox/`. |

Collectors send a descriptive User-Agent, wait between requests to the same host and back off on HTTP 429.
Posting texts stay in your local database; the repository and public reports contain only aggregate counts.

## Privacy

- `.env`, `data/`, `profile/`, `reports/`, `inbox/*` and `config/*.local.yaml` are git-ignored, and
  `tests/test_eval_privacy.py` fails if any of them stops being ignored.
- Before the resume goes to the LLM, the name line, e-mails, phone numbers, links and document numbers are removed
  (`profile/resume_redacted.txt` shows exactly what was sent). `waypoint profile --no-llm` sends nothing.
- On free LLM tiers the provider may use requests to improve its products; use a paid key or a local model
  (`LLM_PROVIDER=openai_compatible` + Ollama) if that matters to you.

## Project layout

```
src/waypoint/
  sources/        Greenhouse, Lever, Ashby, Himalayas, Gupy, manual inbox
  llm/            provider-agnostic JSON client (retries, throttling, cache)
  extract/        LLM prompt + dictionary baseline + canonicalization
  analysis/       market stats, gap, focus-weighted plan
  report/         Markdown report, charts, post numbers
  eval/           sampling, metrics, bootstrap CI, README update
  ui/app.py       Streamlit app (8 pages)
  updater.py      background "update everything" + status file
  launcher.py     one-click start (no terminal), used by the desktop shortcut
  resources/      skill taxonomy, role catalog, project templates, report template
scripts/          Windows runner, shortcut target, cover generator
tests/            54 offline tests with a fake network (pytest; CI on Ubuntu + Windows)
```

## Limitations

- Coverage depends on which companies and sources are configured; Greenhouse/Lever/Ashby skew toward tech companies, and most Brazilian BI postings come from Gupy (local opt-in).
- Shares are computed per posting, not per hire; one company with many similar openings can tilt the numbers (near-duplicates are removed, distinct openings are not).
- Effort estimates in the plan are rough per-skill defaults, meant for ordering, not promises.
- The gold set covers 2 of the 5 roles and awaits a human review pass.

## Roadmap

- Extend the gold set to BI, Analytics Engineer and MLOps postings; human review of all labels.
- **v2 — personal orchestrator:** combine the plan with current projects and deadlines (college, internship, research) into a daily "what now", re-planning when something slips, with the same focus weights and protected exploration.

## License

MIT — see [LICENSE](LICENSE). Job data belongs to the respective employers and job boards.
