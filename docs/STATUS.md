# Project status & worklog

Living record of what the method is now, what has been measured, what is running,
and how to continue. See [METHOD.md](../METHOD.md) for the full method and
[results/RESULTS.md](../results/RESULTS.md) for numbers.

## 1. Method (current, locked)

Fully **on-target, surrogate-free, prior-transfer-free** counseling red-teaming:

1. **Harmful-behavior collection** — query seeds from the JailbreakBench + HarmBench
   self-harm taxonomy (all counseling-relevant behaviors) + counseling-corpus (Cactus)
   + a hand-authored counseling failure-mode taxonomy → `malicious_behavior_seeds_v3.jsonl`
   (**43 seeds, CARES-free**, 5 target types) → `generate_counseling_goal` →
   `attack_goals_v3.jsonl` (**108 goals**, harm levels) + distress personas from Cactus
   (`personas.jsonl`, 150). **CARES supplies no queries — it is the scoring metric and
   judge-validation set only** (see `data/DEPRECATED_v2.md`: the earlier 26-seed/69-goal
   v2 set pulled 10 seeds from CARES, 5 verbatim, and is deprecated).
2. **Target↔persona matching** — embedding cosine (goal ↔ distress persona).
3. **On-target susceptibility** (profile *aware*) — fixed probe battery (16, axis×
   strategy; **no register dimension**) measured on the target.
4. **Pool = PCSA 4 strategies × APE generation** — `ape_forward` = APE instruction
   induction from demos; `grow_pool` = APE Monte-Carlo resampling to a target size.
   The 4 strategies (reassurance_seeking, appeal_to_expertise, intellectualization,
   metaphorical_expression) are the arms.
5. **Efficient selection (TRIPLE, NeurIPS 2024)** — SH / CR / UCB-E / CLST over a
   SHARED pool per (case, pool_mode, size), on the target, then multi-turn
   Best-of-N continuation.
6. **CARES evaluation** — ASR, harm-level-weighted Safety Score, 4-axis UNSAFE
   judge, PPL + §4.4 defenses. Agents: attacker/judge = gpt-5-nano, in-dialogue
   evaluator = gpt-4o-mini; target = PsyCoPref-Llama3-8B.

ICL demos (`data/icl_demos.jsonl`): one ORIGINAL harmful request (HarmBench seed)
mapped to 10 indirect **disguised** client openers (A → A₁..A₁₀), so APE induces
the original→disguise *transformation*.

## 2. Results so far (PsyCoPref target)

- **On-target profiling ablation (N=40/cond):** fixed 0.475 < blind 0.525 <
  shuffled 0.575 < **aware 0.600** UNSAFE. aware beats fixed clearly (+0.125);
  aware−blind +0.075 (95% CI crosses 0 — not yet significant). Benchmark goals +
  persona matching ~2.4× the fixed potency vs old synthetic goals (0.20→0.475).
- **Skill-memory pilot (N=20):** profile_memory 0.600 > profile_aware 0.500
  (accumulated profile helps, directional).
- **Baselines:** direct 0.0, actorattack 0.25, coa/ama 0.286, crescendo 0.50
  UNSAFE — our aware (0.600) exceeds the strongest baseline; all pass PPL<100.
- **TRIPLE pool-size sweep (30/50/120 × SH/UCB/CLST/uniform):** RUNNING.

## 3. What is running / pending

- **2026-10-07 — CARES-free v4 complete (CURRENT).** After finding v2 was
  CARES-contaminated, rebuilt the query set CARES-free and scaled it:
  `malicious_behavior_seeds_v4.jsonl` (82 seeds) → `attack_goals_v4.jsonl` (576 goals),
  from JailbreakBench+HarmBench self-harm taxonomy (all PCSA-fitting benchmark queries,
  ~12) + Cactus corpus (10 distortion patterns + 12 CBT-technique subversions) + a
  hand-authored counseling failure-mode taxonomy. **CARES = scoring metric only.**
  - **Phase 1** (open surrogate `PsychoCounsel-Llama3-8B`, persona-match + jargon/
    evasiveness perturbation): 570/576 hardened, fitness mean 5.75.
  - **aware-vs-blind** N=100/cond: fixed 0.640 / blind 0.730 / aware 0.610 / shuffled
    0.610. **aware−blind = −0.12 (95% CI [−0.22,−0.02]) — profiling does NOT help**
    (overturns the contaminated-v2 positive). The target is highly vulnerable anyway.
  - **pilot** N≈50: aware 0.714 vs memory 0.540 — accumulated memory did not help.
  - **selector** turns=2: all 0.000 (uninformative; target not broken in 2 turns) →
    **turns=4 re-run pending** for a real selection comparison. Per-goal APE pool for
    all 576 goals saved (`runs/ape_pool_v4.json`).
- PENDING: selector turns=4 re-run; base-vs-hardened_v4 (Phase-1 value); pool-size sweep on v4.

## 4. How to run / resume / top-up

Target server (persistent; launch as a background task, **never** `pkill -f
local_server.py` inside the launch command — it self-matches and kills the shell):
```
PCSA_LOCAL_PORT=8012 PCSA_LOCAL_CONCURRENCY=3 CUDA_VISIBLE_DEVICES=1 \
  PCSA_LOCAL_MODEL=Psychotherapy-LLM/PsyCoPref-Llama3-8B PCSA_LOCAL_KEY=local \
  PCSA_LOCAL_DEVICE=cuda PCSA_LOCAL_DTYPE=bfloat16 HF_API_KEY=... python3 -u local_server.py
```
Main method run (defaults = intended method; `--legacy` reverts):
```
python3 experiment.py            # v2 goals + persona-match, 4 conditions, CARES
```
TRIPLE sweep (resume-safe; **top-up without restart** — same --out/--jsonl +
expanded --selectors/--pool-sizes/--goals + --resume runs only the new units and
re-aggregates over all records):
```
python3 phase2_select.py --selectors sequential_halving ucb clustered uniform \
  --pool-modes fused --pool-sizes 30 50 120 --budget 20 --budget-mult 1.5 --turns 2 \
  --base-of-k 3 --cases-per-axis 1 --persona-match --icl-demos \
  --goals ../data/<goals>.jsonl --target-command '["python3","adapters/openai_target.py"]' \
  --out ../reports/phase2_sweep.json --jsonl runs/phase2_sweep.jsonl --resume --profile-cache-dir runs/profile_cache
```

## 5. Key decisions & fixes (session log)

- Goal source pivoted to benchmark taxonomy (JailbreakBench+HarmBench) + corpus,
  reconstructed into counseling goals — fair parity with the PCSA baseline; CARES
  used only as rubric + held-out validation, never as the shared goals.
- **Dropped** surrogate Phase-I and transferred prior; everything on-target.
- **Removed** the plain/clinical register (overlapped appeal_to_expertise, not in
  PCSA); arms = the 4 strategies.
- APE made faithful: forward instruction-induction + Monte-Carlo resampling;
  `grow_pool` expands to 30/50/120.
- **Shared pool** per (case, pool_mode, size) across selectors — TRIPLE compares
  selection algorithms, not pool luck.
- Harm-level-weighted CARES Safety Score (goals carry harm_level).
- ICL demos redesigned as original→disguise A→A₁..A₁₀; softened to indirect
  disguises so the attacker model does not refuse; `build_pool`/`grow_pool` made
  tolerant (a refusing strategy is skipped, never crashes the pool).
- Runtime: everything is `--resume`-safe (per-unit JSONL + flush) with a disk
  profile cache. Local server: unbatched generate under a semaphore, so keep
  concurrency low (3) and workers low (2) — high concurrency wedges the single GPU.
- Background tasks have a ~2h limit; long runs are resumed, not restarted.

Repos/papers: TRIPLE (Shi et al., NeurIPS 2024), APE (Zhou et al., 2211.01910),
CARES (Chen et al., 2505.11413), PCSA "Do No Harm" (2604.04842), JailbreakBench
(Chao 2024), HarmBench (Mazeika 2024).
