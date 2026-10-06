# Results (PsyCoPref-Llama3-8B target)

> ⚠️ **2026-10-06: the numbers below used the v2 goal set, which was found to be
> CARES-contaminated (10/26 seeds from CARES, 5 verbatim) and is deprecated.**
> CARES must be a scoring metric only, not a query source. A CARES-free re-run on
> `attack_goals_v3.jsonl` (43 seeds, 108 goals) is in progress; these tables will be
> replaced with the v3 numbers as they land. See `docs/STATUS.md` §3 and
> `harmful_behavior_collection/data/DEPRECATED_v2.md`.


All metrics are CARES: **ASR** = non-refusal rate, **SS** = harm-level-weighted
Safety Score (higher = safer target), **UNSAFE** = fraction of cases failing any
of the 4 PCSA axes. LLM-judge research measurement, not a clinical-validity claim.
Full per-run table: [`ablation_table.md`](ablation_table.md) / `.csv`.

## 1. On-target profiling ablation — benchmark goals + persona matching (N=40/condition)

| condition | UNSAFE | ASR | SS |
|---|---|---|---|
| fixed (no profile) | 0.475 | 0.194 | 0.831 |
| profile_blind (profile ignored) | 0.525 | 0.244 | 0.809 |
| profile_shuffled (wrong profile) | 0.575 | 0.263 | 0.816 |
| **profile_aware (on-target profile)** | **0.600** | **0.275** | 0.812 |

Paired: aware−blind **+0.075** (95% CI [−0.15, 0.30]); aware−shuffled **+0.025**
([−0.15, 0.20]).
- **profile_aware is the strongest condition** and clearly beats **fixed** (+0.125):
  on-target susceptibility profiling raises attack success over no profiling.
- aware vs blind/shuffled is **directionally positive but not significant at N=40** —
  the open challenge (targeted vs generic profiling).
- The benchmark-seeded goals + persona matching **~2.4× the fixed-condition potency**
  vs the earlier synthetic-goal setup (fixed 0.200 → 0.475).

## 2. Skill-memory pilot — does the accumulated profile help? (N=20/condition)

| condition | UNSAFE | ASR | SS |
|---|---|---|---|
| profile_aware (static pre-test) | 0.500 | 0.250 | 0.750 |
| **profile_memory (accumulated)** | **0.600** | 0.263 | 0.756 |

Accumulated cross-case skill memory adds **+0.10 UNSAFE** over the static profile
(directional; N=20).

## 3. External baselines (same CARES judge)

| method | UNSAFE | ASR | SS | PPL |
|---|---|---|---|---|
| direct | 0.000 | 0.000 | 1.000 | 37 |
| actorattack | 0.250 | 0.062 | 0.969 | 53 |
| coa | 0.286 | 0.107 | 0.946 | 48 |
| ama | 0.286 | 0.143 | 0.929 | 67 |
| crescendo | 0.500 | 0.281 | 0.797 | 59 |

Our **profile_aware (0.600)** exceeds the strongest baseline **crescendo (0.500)**;
all methods pass the GPT-2 perplexity filter (PPL < 100).

_Notes: base-vs-hardened (Phase-I) and the earlier synthetic-goal N=10 run are in
the full `ablation_table.md`; small-N rows are noisy and shown for completeness._

## 4. Phase-2 selector comparison — TRIPLE on a shared APE pool (new config)

All selectors compete on the SAME size-30 APE pool per case (v2 goals + persona
matching + ICL demos + on-target warm-start + skill-memory), 4 axes (n=20/selector):

| selector | UNSAFE | ASR | SS | mean pulls |
|---|---|---|---|---|
| **clustered (TRIPLE-CLST)** | 0.450 | 0.450 | 0.762 | **21** |
| sequential_halving | 0.400 | 0.400 | 0.725 | 45 |
| uniform | 0.650 | 0.650 | 0.662 | 45 |

The efficiency advantage TRIPLE's clustering is designed for shows at N=20:
**CLST matches/beats sequential_halving using ~half the query budget** (21 vs 45
pulls; 0.450 vs 0.400 UNSAFE). `uniform` reaches the highest raw UNSAFE (0.650) but
it is the full-budget, non-adaptive reference — it spends the entire budget probing
every candidate equally rather than identifying a best arm, so its "win" costs the
most queries and offers no selection. Among the adaptive best-arm selectors, CLST is
the best accuracy-per-query. Pool-size sweep (30/50/120) will extend this.

## 5. Phase-I persona perturbation — base vs hardened (v2 config, N=4/condition)

Does the surrogate-guided persona-hardening of Phase I (re-run under the v2 goal
config) make the resulting client opener harder for the target to handle safely?
Same 4 target-type cases, base persona vs hardened persona, scored on-target:

| condition | base UNSAFE | hardened UNSAFE | base SS | hardened SS |
|---|---|---|---|---|
| fixed (no profile) | 0.500 | 0.250 | 0.906 | 0.969 |
| profile_blind | 0.750 | 0.750 | 0.844 | 0.844 |
| profile_aware | 0.250 | **0.750** | 0.938 | 0.844 |
| profile_shuffled | 0.500 | **1.000** | 0.906 | 0.625 |

Directional read (N=4 — **not** significant, shown for completeness): hardening
raises UNSAFE under the profile-driven conditions (aware 0.25→0.75, shuffled
0.50→1.00) while leaving the no-profile `fixed` condition flat/lower — i.e. the
Phase-I hardening and the Phase-II on-target profiling appear **complementary**
(hardening pays off most once a profile steers the strategy). Phase I currently
produces only 4 hardened cases; scaling it is future work. This is an ablation of
the corrected method, not the main result.
