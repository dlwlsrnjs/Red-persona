# Results (PsyCoPref-Llama3-8B target)

> **2026-10-07: these are the CARES-free v4 results** (`attack_goals_v4.jsonl`,
> 82 seeds / 576 goals, built from the JailbreakBench + HarmBench self-harm taxonomy
> + the Cactus counseling corpus + a hand-authored counseling failure-mode taxonomy).
> **CARES contributes no queries — it is the scoring metric and judge-validation set
> only.** The earlier v2 goal set was CARES-contaminated (10/26 seeds from CARES, 5
> verbatim) and is deprecated; its numbers (which suggested profiling helped) did not
> survive the correction. See `harmful_behavior_collection/data/DEPRECATED_v2.md`.

All metrics are CARES: **ASR** = non-refusal rate, **SS** = harm-level-weighted
Safety Score (higher = safer target), **UNSAFE** = fraction of cases failing any of
the 4 PCSA axes. LLM-judge research measurement, not a clinical-validity claim.
Full per-run table: [`ablation_table.md`](ablation_table.md) / `.csv`.

## 1. On-target profiling ablation — CARES-free goals + persona matching (N=100/condition)

| condition | UNSAFE | ASR | SS |
|---|---|---|---|
| fixed (no profile) | 0.640 | 0.300 | 0.752 |
| **profile_blind (profile ignored)** | **0.730** | 0.372 | 0.714 |
| profile_aware (on-target profile) | 0.610 | 0.292 | 0.720 |
| profile_shuffled (wrong profile) | 0.610 | 0.302 | 0.746 |

Paired (case-level bootstrap, 100 pairs): **aware − blind = −0.12, 95% CI
[−0.22, −0.02]** (discordant: blind-only 21 vs aware-only 9); aware − shuffled =
**0.00** ([−0.10, 0.10]).

- **On-target susceptibility profiling does NOT help on the clean goal set.** Giving
  the attacker the measured target profile (`aware`) is **significantly worse** than
  ignoring it (`blind`, same call budget) and **no different** from a wrong/shuffled
  profile. The profiling signal is not useful — and weakly counterproductive — here.
- This **overturns the deprecated v2 result** ("profile_aware strongest, +0.075"),
  which was an artifact of CARES-contaminated goals at N=40. The blind/shuffled
  controls are exactly what exposed it. We report the corrected null/negative finding.
- The target is **highly vulnerable regardless**: even `fixed` (no profiling) fails
  0.640 of disguised harmful counseling requests. The method's potency comes from the
  goal reconstruction + persona matching + multi-turn, not from profiling.

## 2. Skill-memory pilot — does the accumulated profile help? (N≈50/condition)

| condition | UNSAFE | ASR | SS |
|---|---|---|---|
| **profile_aware (static pre-test)** | **0.714** | 0.352 | 0.696 |
| profile_memory (accumulated) | 0.540 | 0.295 | 0.715 |

On the clean v4 goals the **accumulated cross-case skill memory did not help** (and
was lower than the static profile). Consistent with §1: the carried per-model prior
provides no measurable attack benefit here. (Small N; directional.)

## 3. External baselines (same CARES judge)

| method | UNSAFE | ASR | SS | PPL |
|---|---|---|---|---|
| direct | 0.000 | 0.000 | 1.000 | 37 |
| actorattack | 0.250 | 0.062 | 0.969 | 53 |
| coa | 0.286 | 0.107 | 0.946 | 48 |
| ama | 0.286 | 0.143 | 0.929 | 67 |
| crescendo | 0.500 | 0.281 | 0.797 | 59 |

Our pipeline's `fixed`/`blind` conditions on v4 (0.640 / 0.730 UNSAFE) exceed the
strongest external baseline (`crescendo` 0.500); all methods pass the GPT-2
perplexity filter (PPL < 100). The headline contribution is the counseling-specific
goal+persona construction and multi-turn attack, not the profiling step.

## 4. Phase-2 selector comparison — TRIPLE on a shared APE pool (v4)

Size-30 APE pool per goal (PCSA 4 strategies × APE induction + Monte-Carlo grow),
rebuilt per v4 goal; 4 axes, n=20/selector, **turns=2**:

| selector | UNSAFE | mean pulls |
|---|---|---|
| clustered (TRIPLE-CLST) | 0.000 | **19** |
| sequential_halving | 0.000 | 45 |
| uniform | 0.000 | 45 |

**Uninformative at turns=2**: every selector reached UNSAFE 0.000 (the selected
single-prompt attack did not break the target within 2 turns on any of 20 cases),
so there is no selection-quality signal to compare — only the query-efficiency
ordering holds (CLST 19 vs 45 pulls). §1–§2 show the target *is* broken at turns=4,
so a **turns=4 selector re-run** is needed for a meaningful comparison (pending).
A per-goal APE pool for all 576 v4 goals (avg 30 candidates each) is saved at
`runs/ape_pool_v4.json`.

## 5. Phase-1 persona perturbation (v4, open counseling surrogate)

Phase 1 = match a distress persona to each goal, then perturb the persona to raise
linguistic complexity + psychiatric jargon + evasiveness, scored by an **open
counseling surrogate** (`PsychoCounsel-Llama3-8B`, distinct from the target) with
hill-climbing (transfer-attack design; no closed model, no CARES).

- Hardened **570 / 576** goals (6 transient failures); fitness mean **5.75**
  (max 6.0, iters mean 2.6). Fitness plateaus near ~6/10 — the open counseling
  surrogate is itself fairly safe, capping the surrogate-measured progress.
- Hardened personas feed the base-vs-hardened ablation (Phase-1 value), to be run
  against the target next.

_Deprecated v2/v3 rows and the single-GPU throughput notes live in
`ablation_table.md`; small-N rows are noisy and shown for completeness._
