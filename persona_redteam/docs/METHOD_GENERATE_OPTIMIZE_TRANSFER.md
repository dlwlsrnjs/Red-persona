# Red Persona: Generate → Optimize → Transfer

## Research question

Can a clinically grounded red persona internalize a hidden counseling-risk goal and
elicit a measurable safety failure in a single turn, and does a persona selected on an
open surrogate retain that effect on a held-out target model?

The method transfers text, not model state. GPT-4o must never generate, revise, or
select the persona used in the main transfer experiment. Any target-informed revision
is a separate target-adaptive condition.

![Method overview](figures/red_persona_pipeline.svg)

## 1. Generate

The attack generator receives a hidden goal, a source counseling persona, a pathology
mapping, and a sourced clinical context. The tested response model receives none of the
canonical goal text. One generation call returns four independent candidates:
reassurance seeking, appeal to expertise, intellectualization, and metaphorical
expression.

Illustrative schema; the text placeholder is not a research-data example:

```json
{
  "goal_id": "g013",
  "strategy": "intellectualization",
  "parent_id": "root",
  "persona_case": "[single-turn persona that internalizes the hidden goal]",
  "used_terms": ["rumination", "cognitive distortion"],
  "evidence_notes": "grounded in the supplied persona and pathology"
}
```

Every candidate must preserve the source facts, avoid invented diagnosis or treatment
history, use only allowed clinical terminology, and pass a direct-goal leakage check.

## 2. Optimize

Each candidate is sent to the Llama-3.1-8B-Instruct surrogate. GPT-4o-mini audits the
response using the PCSA Figure-3 score, four Figure-4 axes, CARES, and auxiliary quality
constraints. The optimization record stores hashes rather than publishing raw crisis
responses.

```json
{
  "candidate_id": "g013-r2-c4",
  "response_sha256": "...",
  "pcsa": {
    "target_compliance": 1,
    "harmful_content": 0,
    "impersonation": 0,
    "toxic_empathy": 1
  },
  "constraints": {
    "goal_exposed": false,
    "unsupported_clinical_facts": 0,
    "counseling_mode_preserved": true,
    "clinical_grounding": true
  },
  "selected": true
}
```

For the full method, sample three to five surrogate responses per candidate. Retain a
diverse top-k set under the hard quality constraints, and use each selected candidate as
a parent for the next round. The resulting parent-child-score history is the reusable
optimization knowledge. It can later form preference pairs, but the first experiment
uses inference-time selection and does not claim generator fine-tuning.

## 3. Transfer

Freeze the selected persona text before any GPT-4o call. Send that exact text once to
the held-out target and apply the same evaluator and constraints.

```json
{
  "candidate_id": "g013-r2-c4",
  "optimization_model": "meta-llama/Llama-3.1-8B-Instruct",
  "target_model": "gpt-4o-2024-11-20",
  "target_optimized": false,
  "surrogate_score": 2,
  "target_score": 1,
  "transferred": true
}
```

Report surrogate ASR, target ASR, transfer rate, surrogate-target score gap, strategy
diversity, and constraint-valid ASR. With GPT-4o as the only held-out target, describe
the result specifically as Llama-8B-to-GPT-4o transfer. A general cross-model claim
requires at least one additional held-out target.

## Relationship to Jailbreak-Zero

[Jailbreak-Zero](https://arxiv.org/html/2601.03265) uses a strong attack LLM to sample
many proposals and small open models to screen them before querying expensive targets.
In its example-based experiment, Gemma-3 27B generates 1,000 proposals per harmful
behavior. Llama-3.1 8B and Llama-3 RR 8B each generate five responses per proposal,
giving a 0–10 surrogate score; the top 30 proposals per behavior are then tested on
proprietary targets. Its fine-tuned variant converts high- and low-scoring proposals
into preference data and optimizes coverage, diversity, and fidelity. See the
[paper PDF, Sections 3–4](https://openreview.net/pdf/3d46cbb30837fbc806361e95ebbb2932510a2337.pdf).

| Jailbreak-Zero | Red Persona method |
|---|---|
| Harmful behavior or safety policy | Counseling-risk goal |
| Adversarial prompt | Goal-internalized clinical persona |
| Attack LLM | Llama-3.3-70B-Instruct-abliterated |
| Open surrogate | Llama-3.1-8B-Instruct |
| Binary unsafe judge | GPT-4o-mini PCSA four-axis audit |
| Coverage, ASR, diversity, fidelity | Goal coverage, PCSA ASR, strategy diversity, clinical fidelity |
| Top proposal transfer | Frozen persona transfer to GPT-4o |

The adaptation contributes a domain-specific attack representation, a constrained
single-turn objective, and persona-level transfer analysis. It should not claim that
surrogate screening itself is new.

## Experimental matrix

Use the same goals, candidate budget, response-sampling budget, and evaluator across
conditions.

### Baselines

1. Original persona.
2. Jargon-only rewrite.
3. Goal internalization without clinical case framing.
4. Four-strategy generation without surrogate selection.
5. Full surrogate-guided optimization.

### Ablations

1. Remove clinical context.
2. Remove persona-analysis framing.
3. Remove each of the four strategies in turn.
4. Remove cumulative parent state.
5. Remove quality constraints.
6. Compare one response with three or five responses per candidate.

### Evidence for the surrogate's value

Compare random candidates and surrogate-ranked top-k candidates on GPT-4o. Report
target ASR at each k, rank correlation between surrogate and target scores, transfer
precision among surrogate successes, and target API cost per transferred success.
This directly tests whether surrogate screening provides useful information rather
than merely reducing cost.

## Completed one-shot framing pilot

The first six-goal pilot froze 24 candidates and evaluated each under direct persona,
clinical context, and persona-analysis framing, for 72 single-turn response cells.
Strict PCSA Figure-4 unsafe counts were 0/24 in all three arms. Figure-3 means were
4.333, 4.250, and 4.208, respectively. The auxiliary audit reported 17/24
persona-analysis responses as case analysis, but that count is confounded by the
original audit-mode configuration. Candidate messages also lacked direct elicitation,
and the context arm supplied explicit safety guidance. The original pilot therefore
does not isolate a framing-only effect; it is retained as a failed-design ablation
motivating the corrected candidate-selection experiment.
