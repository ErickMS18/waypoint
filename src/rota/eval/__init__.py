"""Evaluation of skill extraction against a hand-labeled gold set.

Gold labels live in eval/gold.jsonl (committed: labels + job ids/URLs only).
Posting texts live in data/eval/texts.jsonl (local, git-ignored) and can be
re-downloaded from the public APIs with `rota eval fetch`.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from ..extract import canonicalize
from ..models import Job, JobExtraction
from ..taxonomy import get_taxonomy


@dataclass
class GoldItem:
    job_key: str
    role: str
    lang: str
    seniority: str
    skills: dict[str, str]  # skill_id -> "required" | "nice_to_have"
    title: str = ""
    company: str = ""
    url: str = ""


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")


def load_gold(path: Path) -> list[GoldItem]:
    tax = get_taxonomy()
    items = []
    for d in load_jsonl(path):
        unknown = [s for s in d["skills"] if s not in tax.skills]
        if unknown:
            raise ValueError(f"{d['job_key']}: gold uses skills outside the taxonomy: {unknown}")
        items.append(GoldItem(job_key=d["job_key"], role=d.get("role", ""), lang=d.get("lang", ""),
                              seniority=d.get("seniority", "unknown"), skills=d["skills"],
                              title=d.get("title", ""), company=d.get("company", ""), url=d.get("url", "")))
    return items


# ----------------------------------------------------------------------------- sampling
def stratified_sample(jobs: list[Job], n: int, roles: list[str], seed: int = 42, max_per_company: int = 3) -> list[Job]:
    """Balanced by role, then mixed languages and companies."""
    rng = random.Random(seed)
    per_role = max(1, n // max(len(roles), 1))
    out: list[Job] = []
    for role in roles:
        pool = [j for j in jobs if j.role == role and len(j.text) > 400]
        rng.shuffle(pool)
        pool.sort(key=lambda j: j.lang)  # stable: groups by lang; interleave below
        by_lang = defaultdict(list)
        for j in pool:
            by_lang[j.lang].append(j)
        picked, per_company = [], defaultdict(int)
        while len(picked) < per_role and any(by_lang.values()):
            for lang in list(by_lang):
                while by_lang[lang]:
                    j = by_lang[lang].pop()
                    if per_company[j.company.lower()] < max_per_company:
                        per_company[j.company.lower()] += 1
                        picked.append(j)
                        break
                if len(picked) >= per_role:
                    break
        out.extend(picked)
    return out


# ----------------------------------------------------------------------------- metrics
def _prf(tp: int, fp: int, fn: int) -> dict[str, float]:
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"precision": p, "recall": r, "f1": f, "tp": tp, "fp": fp, "fn": fn}


def predicted_skills(ext: JobExtraction) -> tuple[dict[str, str], int]:
    """Canonical taxonomy predictions + number of unmapped ("other:") predictions."""
    pred, other = {}, 0
    for cs in canonicalize(ext):
        if cs.skill_id.startswith("other:"):
            other += 1
        else:
            pred[cs.skill_id] = cs.requirement
    return pred, other


def evaluate(gold: list[GoldItem], preds: dict[str, JobExtraction], n_boot: int = 1000, seed: int = 7) -> dict[str, Any]:
    tax = get_taxonomy()
    per_job = []
    for g in gold:
        ext = preds.get(g.job_key)
        if ext is None:
            continue
        p, other = predicted_skills(ext)
        G, P = set(g.skills), set(p)
        both = G & P
        per_job.append({
            "job_key": g.job_key, "lang": g.lang, "role": g.role,
            "tp": len(both), "fp": len(P - G), "fn": len(G - P),
            "tp_req": sum(1 for s in both if g.skills[s] == p[s]),
            "fp_req": len(P - G) + sum(1 for s in both if g.skills[s] != p[s]),
            "fn_req": len(G - P) + sum(1 for s in both if g.skills[s] != p[s]),
            "level_correct": sum(1 for s in both if g.skills[s] == p[s]), "matched": len(both),
            "sen_gold": g.seniority, "sen_pred": ext.seniority, "unmapped": other, "n_pred": len(P) + other,
            "fp_ids": sorted(P - G), "fn_ids": sorted(G - P),
            "cat": {c: [len([s for s in both if tax.category_of(s) == c]),
                        len([s for s in P - G if tax.category_of(s) == c]),
                        len([s for s in G - P if tax.category_of(s) == c])] for c in tax.categories},
        })

    def agg(rows, keys=("tp", "fp", "fn")):
        return _prf(*(sum(r[k] for r in rows) for k in keys))

    res: dict[str, Any] = {"n_jobs": len(per_job), "n_gold_jobs": len(gold)}
    if not per_job:
        return res
    res["skills"] = agg(per_job)
    res["skills_with_level"] = agg(per_job, ("tp_req", "fp_req", "fn_req"))
    matched = sum(r["matched"] for r in per_job)
    res["level_accuracy_on_matched"] = sum(r["level_correct"] for r in per_job) / matched if matched else 0.0
    sen_rows = [r for r in per_job if r["sen_gold"] != "unknown"]
    res["seniority_accuracy"] = (sum(r["sen_gold"] == r["sen_pred"] for r in sen_rows) / len(sen_rows)) if sen_rows else None
    tot_pred = sum(r["n_pred"] for r in per_job)
    res["unmapped_rate"] = sum(r["unmapped"] for r in per_job) / tot_pred if tot_pred else 0.0
    res["macro_f1_per_job"] = sum(_prf(r["tp"], r["fp"], r["fn"])["f1"] for r in per_job) / len(per_job)
    res["by_lang"] = {lang: agg([r for r in per_job if r["lang"] == lang]) | {"n": sum(r["lang"] == lang for r in per_job)}
                      for lang in sorted({r["lang"] for r in per_job})}
    res["by_role"] = {role: agg([r for r in per_job if r["role"] == role]) | {"n": sum(r["role"] == role for r in per_job)}
                      for role in sorted({r["role"] for r in per_job})}
    cats = {}
    for c in tax.categories:
        tp, fp, fn = (sum(r["cat"][c][i] for r in per_job) for i in range(3))
        if tp + fn >= 5:
            cats[c] = _prf(tp, fp, fn)
    res["by_category"] = cats
    # bootstrap CI over jobs for micro F1
    rng = random.Random(seed)
    f1s = sorted(agg([per_job[rng.randrange(len(per_job))] for _ in per_job])["f1"] for _ in range(n_boot))
    res["skills_f1_ci95"] = [f1s[int(0.025 * n_boot)], f1s[int(0.975 * n_boot) - 1]]
    fp_c, fn_c = defaultdict(int), defaultdict(int)
    for r in per_job:
        for s in r["fp_ids"]:
            fp_c[s] += 1
        for s in r["fn_ids"]:
            fn_c[s] += 1
    res["top_false_positives"] = sorted(fp_c.items(), key=lambda x: -x[1])[:8]
    res["top_false_negatives"] = sorted(fn_c.items(), key=lambda x: -x[1])[:8]
    res["per_job"] = [{k: v for k, v in r.items() if k != "cat"} for r in per_job]
    return res


def run_extractor(gold: list[GoldItem], texts: dict[str, Job], fn: Callable[[Job], JobExtraction],
                  progress: Callable[[int, int], None] | None = None) -> dict[str, JobExtraction]:
    out = {}
    for i, g in enumerate(gold, 1):
        job = texts.get(g.job_key)
        if job is None:
            continue
        if progress:
            progress(i, len(gold))
        out[g.job_key] = fn(job)
    return out


# ----------------------------------------------------------------------------- reporting
def results_markdown(results: dict[str, dict[str, Any]], meta: dict[str, Any]) -> str:
    def f(x):
        return "–" if x is None else f"{x:.2f}"

    lines = [
        f"Gold set: **{meta['n_gold']} real job postings** ({meta['composition']}), labeled with "
        f"{meta['n_labels']} skill labels from a {meta['n_taxonomy']}-skill taxonomy. Evaluated on {meta['date']}.",
        "",
        "| Extractor | Skill P | Skill R | Skill F1 (95% CI) | F1 incl. required/nice | Seniority acc. | Unmapped |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name, r in results.items():
        if not r.get("n_jobs"):
            continue
        s, ci = r["skills"], r["skills_f1_ci95"]
        lines.append(
            f"| {name} | {f(s['precision'])} | {f(s['recall'])} | **{f(s['f1'])}** ({f(ci[0])}–{f(ci[1])}) | "
            f"{f(r['skills_with_level']['f1'])} | {f(r['seniority_accuracy'])} | {r['unmapped_rate']:.0%} |"
        )
    lines += ["", "Skill F1 by posting language:", "", "| Extractor | " + " | ".join(
        f"{lang.upper()} (n={next(iter(results.values()))['by_lang'][lang]['n']})"
        for lang in next(iter(results.values())).get("by_lang", {})) + " |",
        "|---|" + "---:|" * len(next(iter(results.values())).get("by_lang", {}))]
    for name, r in results.items():
        if r.get("n_jobs"):
            lines.append(f"| {name} | " + " | ".join(f(v["f1"]) for v in r["by_lang"].values()) + " |")
    return "\n".join(lines) + "\n"


def update_readme(readme: Path, block: str) -> bool:
    start, end = "<!-- EVAL:START -->", "<!-- EVAL:END -->"
    text = readme.read_text(encoding="utf-8")
    if start not in text or end not in text:
        return False
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    readme.write_text(f"{head}{start}\n{block}{end}{tail}", encoding="utf-8")
    return True
