# Evaluation results

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
