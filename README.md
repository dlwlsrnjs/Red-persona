# mental_jail — Counseling-Safety Red-Teaming (core method)

Research framework for red-teaming the safety of mental-health counseling LLMs.
Everything runs on small agent models (attacker/judge = gpt-5-nano; in-dialogue
evaluator = gpt-4o-mini); the target is a real counseling model
(e.g. PsyCoPref-Llama3-8B). Evaluation uses the CARES rubric. **For authorized
safety-measurement research only** — the pipeline *measures* model failures; it
does not distribute actionable harmful content.

See [METHOD.md](METHOD.md) for the full method, rationale, examples, and prior-work
references.

## Repository layout

| Folder | What it is |
|---|---|
| `harmful_behavior_collection/` | Build the attack goals: benchmark self-harm taxonomy (JailbreakBench + HarmBench) + counseling-corpus patterns → **seeds** → reconstructed counseling **goals** (5 PCSA target types, harm levels) + distress-oriented **personas**. |
| `phase1_persona_perturbation/` | Phase I: persona construction / perturbation and its PPL-constrained fitness (kept as an ablation in the corrected method). |
| `phase2_strategy_optimization/` | Phase II: the efficient **on-target** optimizer — APE candidate pool + TRIPLE best-arm-identification selectors (SH/CR/UCB/CLST) + BAI + cross-case skill memory. |
| `baselines/` | External attack methods, **one folder per paper** (Direct, Crescendo, CoA, AMA, ActorAttack), each self-contained and scored by the same CARES judge for a fair comparison. |
| `evaluation/` | CARES metrics, external-method baselines runner, §4.4 defenses, ablation report. |
| `common/` | Shared modules used by all stages: the multi-role small-model adapter, the target adapter, the PCSA core (strategies/axes/profiling/run_case), data loaders, experiment runner. |
| `docs/` | Design notes (goal-generation design, profiling-enhancement analysis). |

## Method at a glance

1. **Harmful-behavior collection** → `malicious_behavior_seeds.jsonl` (26 seeds,
   5 target types) → `attack_goals_v2.jsonl` (69 goals) + `personas.jsonl` (150).
2. **Target↔persona matching** (embedding cosine) → coherent client presentation.
3. **On-target susceptibility measurement** (`aware`) + **efficient TRIPLE
   best-arm optimization on the target** (no surrogate, no transferred prior).
4. **CARES evaluation**: ASR, harm-level-weighted Safety Score, 4-axis UNSAFE
   judge, perplexity + defenses.

## Datasets (research artifacts, in `harmful_behavior_collection/data/`)

- `malicious_behavior_seeds.jsonl` — behavior seeds (benchmark + corpus), tagged by target_type/axis.
- `attack_goals_v2.jsonl` — reconstructed counseling goals `{axis, target_type, harm_level, intent, masked_request}`.
- `personas.jsonl` — distress-oriented personas (derived from the Cactus corpus).
- `susceptibility_probes.jsonl`, `calibration_probes.jsonl`, `client_exemplars.jsonl`, `psych_jargon.jsonl` — profiling/probe assets.

The large raw corpora (Cactus, CARES-18K, HarmBench, JailbreakBench) are **not**
included — obtain them from their original sources; only our small derived
artifacts are here.

## Running

Modules use flat imports, so place `common/` and the stage folder on one
`PYTHONPATH` (the original development layout keeps all `.py` in a single
directory). API keys are read from environment variables
(`OPENAI_API_KEY`, optional `OPENAI_API_KEY_2` for rotation; `HF_API_KEY` for
gated model downloads) — never commit them.

## Safety & ethics

Authorized defensive safety research. Attack goals are disguised distressed-client
openers used to *measure* whether a counseling model responds safely; the judge
detects and the pipeline quantifies failures. Do not use to elicit actionable harm.
