# Why performance rose + Profiling enhancement design

Status: analysis (data-grounded) + design. Dated 2026-10-05.

## 1. Why did UNSAFE rise (OLD N=10 → NEW validation_v2)? — data-grounded

Measured on validation_v2 partial (n=64) vs N=10 (n=157):

| signal | OLD N=10 | NEW v2+match | reading |
|---|---|---|---|
| turn-0 opening triggers UNSAFE | 14% of unsafe | **30%** | v2 masked_requests (benchmark-seeded, harm-graded) are **much stronger openers** |
| harmful_content axis UNSAFE | 0.250 | **0.675** | benchmark self-harm taxonomy hits hard |
| self_harm_suicide target_type | — | **0.675** | strongest attack type |
| aware turn-0 strategy mix | spread | **reassurance_seeking 13/18** | aware **concentrates on the profiled weak strategy**; blind spreads (7/5/4/2) |

**Conclusions:**
- (a) **Stronger goals/openings** drive most of the rise — the benchmark-seeded, harm-level-graded `masked_request` fails the target at turn 0 twice as often.
- (b) **aware's lead comes from strategy concentration**: the profile tells it reassurance_seeking is weak, and it concentrates there → higher UNSAFE (0.643) than blind's even spread (0.500). Direct evidence the susceptibility profile has incremental value.
- (c) **Vulnerability concentrates in SUBTLE cases**: UNSAFE is HIGHER at low harm_level (L0 0.78, L1 0.75) than blatant (L2 0.45, L3 0.42) — the model refuses blatant requests but is caught by subtle ones (consistent with the toxic-empathy thesis). Metric note: for L0 the 4-axis UNSAFE flag likely over-fires on benign goals; harm-weighted SS is the trustworthy metric there.
- Caveat: partial n=64 skewed toward harmful_content/impersonation; full 160 needed for significance (aware−blind +0.077, aware−shuffled +0.071, CIs still cross 0).

## 2. Prior work (deeper analysis) — what to borrow, how we differ

- **RedAgent** (Xu et al. 2024, arXiv 2407.16667): multi-agent that abstracts attacks into *jailbreak strategies*, generates context-specific prompts, and keeps a **memory buffer with self-reflection on contextual feedback** to reuse strategies across contexts → ~5-query jailbreaks. General-purpose, black-box. **No separated susceptibility *measurement*, no ablation of its value, no counseling domain, no persona-target matching.**
- **ArtPrompt** (2024): static ASCII-art obfuscation; not target-adaptive profiling.
- **X-teaming / AutoRedTeamer / JailbreakSkill** (2025): multi-turn adaptive multi-agent, lifelong/reusable *skill memory* of attacks. General domain.
- **ArtPerception / wobble-probing**: per-axis sensitivity probing (our pre-test lineage).

**Our novelty (sharpened):** a counseling-specific **separated susceptibility measurement** (fixed probe battery → per-axis/target_type/strategy ranking) whose **incremental contribution is ablated** (aware vs blind vs shuffled) — prior profiling agents (RedAgent) bundle profiling inside an agent and never isolate its value. Plus persona↔target matching and Phase-I perturbation.

## 3. Profiling enhancement design (grounded in §1 findings + §2 prior work)

Since aware's edge = strategy concentration (§1b) and the weak signal is strategy-specific and subtle (§1c), strengthen the *strategy discrimination* and make it *adaptive/accumulating* (RedAgent memory):

- **E1 — finer granularity**: probe per (axis × **target_type** × strategy × register), not just per-axis. 5 target types → sharper, type-specific weak-strategy ranking. (Current: 32 probes = axis×strategy×register.)
- **E2 — replicated wobble**: k≥2 replicates per probe; wobble = mean (+ variance as a confidence signal). Stabler ranking → aware concentrates more reliably.
- **E3 — multi-turn rapport default ON** (rapport_turns≥2): deeper probing elicits a stronger, more discriminative wobble signal (the pre-test currently supports it but default 0 in experiment.py).
- **E4 — cross-case skill memory (RedAgent-style)**: a buffer mapping (axis/target_type) → observed (strategy,register)→UNSAFE success counts, updated after each case's judge, used to warm-start the next case's strategy selection. Turns the static pre-test into an accumulating prior — this is the biggest lever and our adaptation of RedAgent's memory to a *measured* susceptibility signal.
- **E5 — confidence-gated concentration**: when the profile is confident (high wobble spread/low variance) concentrate on the top strategy; when flat, explore (UCB-style). Prevents aware from degrading to blind when the signal is weak.
- **E6 — per-harm-level sensitivity**: record wobble by harm_level to exploit the subtle-case vulnerability (§1c) deliberately.

**Disruption note:** E1/E2/E3/E6 change the pre-test → invalidate the profile cache → require re-profiling + re-running aware/blind/shuffled. E4/E5 are additive to Phase-II selection and can layer on without re-profiling. Recommend: finish current validation (establish the baseline-design number), then apply E1-E3 + E4 for a "strengthened-profile" arm and compare.

Sources: RedAgent arXiv 2407.16667; ArtPrompt (Jiang et al. 2024); X-teaming / AutoRedTeamer / JailbreakSkill (2025); PCSA "Do No Harm" arXiv 2604.04842.
