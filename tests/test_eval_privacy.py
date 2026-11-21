import json
import subprocess
from pathlib import Path

import pytest

from waypoint.eval import GoldItem, evaluate, load_gold, results_markdown, stratified_sample, update_readme
from waypoint.models import Job, JobExtraction, SkillMention

REPO = Path(__file__).resolve().parents[1]


def test_metrics_hand_computed():
    gold = [GoldItem("a", "r", "en", "mid", {"python": "required", "sql": "required", "docker": "nice_to_have"}),
            GoldItem("b", "r", "pt", "senior", {"python": "required", "aws": "required"})]
    preds = {
        "a": JobExtraction(seniority="mid", skills=[SkillMention(name="Python"), SkillMention(name="Docker"),
                                                    SkillMention(name="Kubernetes", requirement="nice_to_have")]),
        "b": JobExtraction(seniority="mid", skills=[SkillMention(name="Python"), SkillMention(name="AWS"),
                                                    SkillMention(name="Made-up tool")]),
    }
    r = evaluate(gold, preds, n_boot=50)
    # a: TP python, docker; FP kubernetes; FN sql. b: TP python, aws (+1 unmapped)
    assert (r["skills"]["tp"], r["skills"]["fp"], r["skills"]["fn"]) == (4, 1, 1)
    assert r["skills"]["precision"] == pytest.approx(0.8) and r["skills"]["recall"] == pytest.approx(0.8)
    # docker predicted required but gold says nice -> wrong level
    assert r["level_accuracy_on_matched"] == pytest.approx(3 / 4)
    assert r["seniority_accuracy"] == pytest.approx(0.5)
    assert r["unmapped_rate"] == pytest.approx(1 / 6)
    assert set(r["by_lang"]) == {"en", "pt"}
    lo, hi = r["skills_f1_ci95"]
    assert 0 <= lo <= r["skills"]["f1"] <= hi <= 1
    md = results_markdown({"Test": r}, {"n_gold": 2, "composition": "x", "n_labels": 5, "n_taxonomy": 96, "date": "d"})
    assert "| Test |" in md and "0.80" in md


def test_stratified_sample_balances_roles():
    jobs = [Job(job_key=f"s:b:{i}", source="s", external_id=str(i), company=f"c{i % 7}", title="t",
                role="r1" if i % 2 else "r2", lang="pt" if i % 3 else "en", text="x" * 500) for i in range(60)]
    s = stratified_sample(jobs, 20, ["r1", "r2"])
    assert len(s) == 20 and sum(j.role == "r1" for j in s) == 10
    assert {j.lang for j in s} == {"pt", "en"}


def test_gold_file_is_valid():
    path = REPO / "eval" / "gold.jsonl"
    if not path.exists():
        pytest.skip("gold set not created yet")
    gold = load_gold(path)
    assert len({g.job_key for g in gold}) == len(gold)
    raw = path.read_text(encoding="utf-8")
    assert '"text"' not in raw  # posting texts must never be committed


def test_update_readme(tmp_path):
    p = tmp_path / "README.md"
    p.write_text("a\n<!-- EVAL:START -->\nold\n<!-- EVAL:END -->\nb", encoding="utf-8")
    assert update_readme(p, "NEW\n")
    assert p.read_text(encoding="utf-8") == "a\n<!-- EVAL:START -->\nNEW\n<!-- EVAL:END -->\nb"


# ---------------------------------------------------------------- privacy
SENSITIVE = [".env", "config/sources.local.yaml", "data/waypoint.db", "data/eval/texts.jsonl", "profile/profile.json", "profile/overrides.yaml",
             "profile/resume_redacted.txt", "reports/waypoint_report.md", "reports/public/market_report.md",
             "inbox/vaga.txt"]


def test_gitignore_covers_personal_data(tmp_path):
    """Personal files must be ignored by git. Uses real `git check-ignore` when git is available."""
    gi = (REPO / ".gitignore").read_text(encoding="utf-8")
    for pattern in (".env", "data/", "profile/", "reports/", "inbox/*"):
        assert pattern in gi.splitlines()
    try:
        subprocess.run(["git", "--version"], check=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git not installed")
    (tmp_path / ".gitignore").write_text(gi, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    for f in SENSITIVE:
        out = subprocess.run(["git", "check-ignore", "-q", f], cwd=tmp_path)
        assert out.returncode == 0, f"{f} is NOT ignored by .gitignore"
    out = subprocess.run(["git", "check-ignore", "-q", "inbox/README.md"], cwd=tmp_path)
    assert out.returncode == 1


def test_no_personal_files_tracked():
    """If the repo is a git checkout, none of the sensitive paths may be tracked."""
    try:
        out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    tracked = set(out.splitlines())
    bad = [f for f in tracked if f == ".env" or f.startswith(("data/", "profile/", "reports/"))
           or (f.startswith("inbox/") and f != "inbox/README.md")]
    assert not bad, f"personal files tracked by git: {bad}"


def test_cli_eval_end_to_end(cfg, db, transport):
    """sample -> (gold written by an annotator) -> run, baseline only, offline."""
    from typer.testing import CliRunner
    from waypoint.cli import app
    from waypoint.collect import collect
    from waypoint.eval import load_jsonl, write_jsonl
    collect(cfg, db, transport=transport)
    r = CliRunner().invoke(app, ["eval", "sample", "--n", "4"])
    assert r.exit_code == 0, r.output
    texts = load_jsonl(cfg.paths.eval_data / "texts.jsonl")
    assert texts and all("text" in t for t in texts)
    gold = [{"job_key": t["job_key"], "role": t["role"], "lang": t["lang"], "seniority": "unknown",
             "skills": {"python": "required"}, "annotator": "test"} for t in texts]
    write_jsonl(cfg.paths.eval_dir / "gold.jsonl", gold)
    (cfg.paths.root / "README.md").write_text("x\n<!-- EVAL:START -->\n<!-- EVAL:END -->\n", encoding="utf-8")
    r = CliRunner().invoke(app, ["eval", "run", "--extractor", "baseline", "--update-readme"])
    assert r.exit_code == 0, r.output
    assert "Dictionary baseline" in (cfg.paths.root / "README.md").read_text(encoding="utf-8")
    assert (cfg.paths.eval_dir / "results" / "baseline.json").exists()


def test_local_config_override(project):
    from waypoint.settings import load_config
    (project / "config" / "sources.local.yaml").write_text("gupy:\n  enabled: true\n", encoding="utf-8")
    cfg = load_config(project)
    assert cfg.sources["gupy"]["enabled"] is True and cfg.sources["gupy"]["max_pages"] == 2
    assert "config/*.local.yaml" in (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()
