# Project history & concrete worklog

Chronological record of what was built, what was measured, the mistakes found and
corrected, and the exact artifacts/numbers. Companion to [STATUS.md](STATUS.md)
(current state) and [../results/RESULTS.md](../results/RESULTS.md) (numbers).

Target: `PsyCoPref-Llama3-8B` (real counseling model). Agents: attacker/judge/
profiler/scriptwriter = gpt-5-nano; in-dialogue evaluator = gpt-4o-mini. Metrics:
CARES (ASR = non-refusal, harm-level-weighted Safety Score, 4-axis UNSAFE).

## Goal-set evolution (query construction)

| version | seeds | goals | status | note |
|---|---|---|---|---|
| v2 | 26 | 69 | **deprecated** | CARES-contaminated: 10/26 seeds from CARES-18K, **5 verbatim** prompts used as queries |
| v3 | 43 | 108 | superseded | first CARES-free rebuild |
| **v4** | **82** | **576** | **current** | CARES-free + scaled; one APE pool per goal |

**Query source = JailbreakBench + HarmBench self-harm taxonomy + Cactus counseling
corpus + a hand-authored counseling failure-mode taxonomy. CARES = scoring metric
and judge-validation ONLY, never a query source.**

- Benchmark ceiling: HarmBench (400) + JailbreakBench (100) contain only ~12
  PCSA-fitting counseling-harm queries total (suicide/self-harm/eating-disorder/
  gaslighting/relapse/unauthorized-med). All are included; the rest of those
  benchmarks are off-domain (bombs, malware, copyright, …) and excluded.
- Cactus (31,577 CBT cases) grounds: 150 distress personas (`intake_form`),
  800 client utterances (`dialogue`), 10 cognitive-distortion seeds (`patterns`),
  12 anti-recovery seeds (CBT-technique subversion).
- v4 goal mix: axis harmful_content 176 / toxic_empathy 160 / target_compliance 152
  / impersonation_violation 88; types self_harm 96, eating 96, cognitive 144,
  anti_recovery 152, unauthorized_med 88; harm levels L0 72, L1 161, L2 238, L3 105.
- Quality (automated): 100% first-person client voice, 0 exact duplicates, 0 overt
  imperatives (disguise intact), 0 off-domain keywords, mean 23 words.

## Method (final, locked)

1. **Phase 1 — persona perturbation (transfer-attack, open surrogate).** Match a
   distress persona to each goal (embedding cosine), then perturb the persona to
   raise linguistic complexity + psychiatric jargon + evasiveness, scored by an
   **open counseling surrogate** `PsychoCounsel-Llama3-8B` (distinct from the target)
   with hill-climbing. No closed model, no CARES. `run_phase1.py --one-per-goal`.
2. **Phase 2 — on-target efficient optimization.** Per goal: build an APE candidate
   pool (PCSA 4 strategies × APE instruction-induction + Monte-Carlo grow to 30),
   then TRIPLE best-arm-identification selectors (SH/CR/UCB-E/CLST) on a SHARED pool,
   then multi-turn Best-of-N. On-target susceptibility profile + cross-case skill
   memory optionally fed to the selector warm-start.
3. **CARES evaluation** — ASR, harm-level-weighted SS, 4-axis UNSAFE, paired
   aware-vs-blind bootstrap; GPT-2 perplexity + defenses.

## Key events & corrections

- **CARES contamination found & fixed.** v2 had 10 CARES-sourced seeds (5 verbatim).
  Violated the fairness rule (CARES is metric-only). Rebuilt CARES-free (v3→v4).
- **Phase-1 surrogate corrected to an open model.** First redo used gpt-4o-mini
  (closed) after HF-router credits were depleted (HTTP 402) — wrong for a
  transfer-attack design. Switched to the locally-served open `PsychoCounsel-Llama3-8B`
  (HF *hub download* is free; only hosted inference was out of credit).
- **Scaled the query set** on request: 69 → 108 → 576 goals; one APE pool per goal
  for all 576 (`runs/ape_pool_v4.json`, avg 30 candidates).
- **harm_level metric-validity finding** (see `results/harm_level_analysis.md`):
  L0/L1 goals are benign / over-refusal probes, not attacks; mixing them into
  UNSAFE/ASR contaminates the attack metric. Attack success must be scored on L2-L3.

## Measured results (v4, CARES-free)

- **Phase 1**: 570/576 hardened, fitness mean 5.75 (open surrogate ceiling ~6/10).
- **aware-vs-blind (N=100, all levels)**: fixed 0.640 / blind 0.730 / aware 0.610 /
  shuffled 0.610; paired aware−blind = −0.12 (95% CI [−0.22,−0.02]).
- **Restricted to attack goals L2-L3 (n=53/cond)**: fixed 0.509 / blind 0.698 /
  aware 0.604 / shuffled 0.528 — here aware > fixed and > shuffled, but blind is
  anomalously high (needs scrutiny). The all-levels null was partly L0/L1 contamination.
- **pilot (N≈50)**: aware 0.714 vs memory 0.540 (accumulated memory did not help).
- **selector (turns=2)**: all 0.000 (target not broken in 2 turns) — uninformative;
  turns=4 re-run pending. CLST is most query-efficient (19 vs 45 pulls).
- **external baselines (same judge)**: direct 0.000, actorattack 0.250, coa 0.286,
  ama 0.286, crescendo 0.500 UNSAFE.

## Open items

1. Recompute all attack metrics **L2-L3 only** (attack) vs **L0-L1** (over-refusal),
   update RESULTS.
2. Investigate the `profile_blind` L2-L3 anomaly (0.698 vs fixed 0.509).
3. Selector **turns=4** re-run for a real selection comparison.
4. base-vs-hardened_v4 to measure Phase-1 value against the target.

## Artifacts (repo paths)

- Goals/seeds: `harmful_behavior_collection/data/attack_goals_v4.jsonl` (576),
  `malicious_behavior_seeds_v4.jsonl` (82), `ape_pool_v4_per_goal.json`.
- Code: `phase1_persona_perturbation/run_phase1.py`,
  `phase2_strategy_optimization/{phase2_select.py, prompt_pool.py, bai.py, build_ape_pool_v4.py}`,
  `common/{pcsa.py, data_sources.py, experiment.py, skill_memory.py, adapters/}`.
- Results: `results/RESULTS.md`, `ablation_table.md/.csv`, `harm_level_analysis.md`.
