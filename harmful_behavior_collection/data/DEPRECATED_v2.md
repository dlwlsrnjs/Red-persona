# Deprecated: v2 seeds & goals (CARES-contaminated)

`malicious_behavior_seeds.jsonl` (26 seeds) and `attack_goals_v2.jsonl` (69 goals)
are **superseded** by the v3 artifacts and kept only for provenance.

**Why deprecated.** 10 of the 26 v2 seeds were sourced from CARES-18K
(`source: CARES-supplementary`), and **5 of those were verbatim copies of CARES-18K
prompts** used as attack queries. This violates our stated fairness rule — CARES is
a *scoring metric* (harm-level-weighted Safety Score) and judge-validation set, **not**
a query source — and the baseline-comparison fairness decision (never copy a
benchmark's rows as goals).

**Fix (v3).** Query seeds now come only from the JailbreakBench + HarmBench self-harm
taxonomy (all counseling-relevant behaviors extracted) plus counseling-corpus
(Cactus) and a hand-authored **counseling failure-mode taxonomy** that exhaustively
covers the harmful mental-health counseling space. CARES contributes **no** queries.

- `malicious_behavior_seeds_v3.jsonl` — 43 seeds, 0 from CARES, 0 verbatim-in-CARES.
- `attack_goals_v3.jsonl` — 108 goals (axis: harmful_content 27 / toxic_empathy 36 /
  impersonation_violation 24 / target_compliance 21; harm levels 0-3).

Use the v3 files for all new runs.
