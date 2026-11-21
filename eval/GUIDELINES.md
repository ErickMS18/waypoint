# Annotation guidelines (gold set)

The gold set measures how well an extractor turns a job posting into
`{skill_id: required | nice_to_have}` plus a seniority level. Every posting is labeled
by reading the **full text**, following the rules below (the same rules the LLM prompt uses,
so the task is well defined for both).

## What counts as a skill
- Technical skills, tools, frameworks, libraries, cloud services, methods/techniques
  (A/B testing, RAG, feature engineering), math/statistics areas and spoken languages.
- Soft skills only when explicitly demanded ("strong communication skills").
- Skills that appear **only in the responsibilities** count when the candidate will use them
  hands-on ("you will build RAG pipelines" → `rag`).
- **Not** skills: the company's own products, technologies mentioned only to describe the
  company, benefits, hiring steps, legal text, vague terms ("AI", "technology", "innovation").

## Requirement level
- `nice_to_have` when the posting marks it as optional: sections such as *Nice to have,
  Preferred, Bonus, Plus, Diferenciais, Desejável*, or phrases like *is a plus, preferably,
  ideally, será um diferencial*.
- Otherwise `required`.
- If a skill appears both ways, `required` wins.

## Vocabulary
- Labels use only the ids in `src/waypoint/resources/skills.yaml` (closed vocabulary).
  A skill outside the taxonomy is left unlabeled and noted in `notes`; the extractor's
  unmapped predictions are reported separately as "unmapped rate".
- Umbrella vs. specific: label what is written. "Experience with AWS (S3, Lambda)" → `aws`;
  "PyTorch or TensorFlow" → both, `required`. Model names used as tools ("GPT, Claude, Gemini") → `llm_apis`
  when the candidate builds with them, `llms` when they only use chat products.
- A "Stack / Tools" list describes tools used hands-on → `required`, unless the same item is also listed in
  an explicit optional section, in which case `required` still wins (rule above).

## Seniority
Title first (intern/estágio → `intern`; junior/jr/entry/associate → `junior`; pleno/mid/II →
`mid`; senior/sr/III → `senior`; staff/principal/lead/specialist/especialista → `staff_plus`).
If the title has two markers ("Sênior / Tech Lead"), the first one wins; "Leader" counts as lead.
If the title is silent, use the minimum years required: 0–1 `junior`, 2–4 `mid`, 5–7 `senior`,
8+ `staff_plus`. Otherwise `unknown` (excluded from seniority accuracy).

## Process and honesty notes
- Postings are sampled with `waypoint eval sample` (stratified by role and language, max 3 per
  company) from real collections — never hand-picked.
- Labels are written **before** looking at any extractor output for that posting.
- Only labels and posting ids/URLs are committed (`eval/gold.jsonl`); the posting texts stay
  local (`data/eval/texts.jsonl`) and can be re-downloaded with `waypoint eval fetch` while the
  postings are online.
- Who labeled is recorded in each line (`annotator`). Labels drafted with AI assistance are
  marked as such and must be reviewed by a human before results are published.
