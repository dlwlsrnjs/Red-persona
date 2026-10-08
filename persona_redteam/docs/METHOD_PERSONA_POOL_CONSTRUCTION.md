# Persona pool construction and quality control

This document describes how the vulnerable-persona pool is built and quality-controlled
for the counseling red-team pipeline. It is written to be excerpted into the paper's
methods section. All model calls use `gpt-4o-mini-2024-07-18` as the pathology
structurer; raw persona text, weights, and logs are not published.

## 1. Persona sources

Personas are drawn from four public corpora and projected onto a single clinical
pathology schema. Raw persona text is gitignored; only the derived pathology is retained.

| Pool | n | Nature | Primary crisis coverage |
|---|---:|---|---|
| VERA-MH SI (`veramh_si`) | 100 | Suicide-risk clinical personas (with suicide risk level) | suicidal_ideation |
| VERA-MH HFO (`veramh_hfo`) | 100 | Harm-from-others (threat/violence context) personas | violence context (victim-framed) |
| SimMH (`simmh`) | 157 | Simulated mental-health client narratives | suicidal, anxiety, mixed |
| Cactus distress (`cactus`) | 2000 | Distress-prioritized counseling personas | depression, anxiety, eating/body, self-harm |

Total profiled: **2357** personas.

## 2. Pathology schema (v2)

Each persona is normalized to a fixed, de-identified clinical signature:
`core_condition`, `symptoms`, `functional_impairments`, `cognitive_distortions`
(CBT subset), `stressors`, `relational_stance`, `communication_style`, `risk_state`
(ideation / intent / plan / preparation, preserved separately), `persona_self_schema`
(characteristic distorted first-person belief), `susceptibility_lever` (the empathy
frame the persona tends to evoke), and `crisis_tags` (JMIR 7-category vocabulary).
Demographics (age, gender) are never inferred. `core_condition` is the primary clinical
condition in standard terms (e.g., `substance_use_disorder`, `gambling_disorder`,
`intermittent_explosive_disorder`), never a crisis label and never a cognitive
distortion — this keeps goals and personas on the same ontological level for matching.

## 3. Completeness repair with provenance tagging

A single extraction pass frequently leaves clinical axes empty (the source text may
describe context, not symptoms). Rather than drop such personas, the profiler runs a
bounded repair loop: it re-prompts the model with the list of empty required fields and
asks it to populate them from the same source text, inferring the most clinically
plausible value where the text is thin. Every field that was empty on the first pass and
filled by repair is recorded in a `repaired_fields` provenance list on the persona.

This trades completeness for a transparent, auditable inference flag: downstream matching
and audits can discount or down-weight inferred axes. Example (HFO persona under imminent
threat): the first pass left `symptoms` and `functional_impairments` empty; repair filled
`symptoms=[anxiety, hypervigilance]` and `functional_impairments=[difficulty_concentrating,
sleep_disturbances]` — clinically plausible for acute threat but inferred, not stated, and
tagged accordingly. Repair incidence is pool-dependent: high for HFO (threat-context
source, ~29% of personas), near zero for narrative-rich SimMH.

## 4. Crisis-conditioned enrichment for under-represented categories

When profiled under a purely clinical frame, the behavioral-crisis categories
(substance abuse/withdrawal, violent thoughts, risk-taking) and, to a lesser extent,
self-harm are rarely tagged as the *primary* crisis: the profiler collapses them onto the
dominant clinical condition (depression/anxiety/suicidal). These categories also have no
dedicated real-persona corpus in English.

To make the existing personas usable for these categories without fabricating sources,
candidate personas are re-profiled with a crisis-conditioned prompt: given a target crisis
category, the model surfaces the clinical presentation relevant to that crisis
(crisis-relevant symptoms, cognitive distortions, self-schema) **only where the source text
supports it**, and sets `core_condition` to the primary clinical condition. Candidates are
drawn from the most relevant source (HFO for violence/risk; native self-harm-tagged Cactus
rows for self-harm; substance/risk keyword matches across pools), re-profiled, and kept only
if the model independently tags them with the target crisis. Enriched personas carry a
distinct `<id>__<crisis>` identifier, `crisis_tags=[crisis]`, and an `enriched_for` tag.

Yield: 397 candidates → **389 enriched** personas (violent_thoughts 96, risk_taking 149,
self-harm 100, substance 44).

## 5. Retrieval / grounding gate

Goals are matched to personas on the shared pathology signature across the **union** of all
pools (filtered by crisis tag, risk compatibility, and the suicide risk gate where a pool
carries a risk level), ranked by a hybrid of structured clinical-axis overlap (0.75) and
embedding cosine of the pathology text (0.25, `text-embedding-3-small`). A candidate is
kept only if it is *clinically grounded*: an exact overlap on `core_condition`, `symptoms`,
or `functional_impairments`, **or** a pathology-signature cosine at or above a threshold
(default 0.55). The grounding mode (`structural` / `semantic` / `both`) is recorded per
candidate. This tolerates free-text label variance while keeping a clinical anchor.

## 6. Quality outcome

On the 30-goal pilot (6 crisis categories × 5 goals), with the union of standard and
enriched pools:

- **30/30 goals routed**; **29/30 top matches are `both`-grounded** (structural + semantic),
  up from semantic-only matches (cosine ≈ 0.57) before clinical-core alignment and
  enrichment.
- `core_condition` overlap of 1.0 on roughly 18/30 top matches; symptom overlap present in
  most previously-weak matches.
- Category examples now showing full alignment: risk-taking ↔ PTSD persona (core 1.0,
  symptom 1.0, cosine 0.85); violent thoughts ↔ intermittent-explosive persona (core 1.0,
  symptom 0.5, cosine 0.82); substance ↔ substance-use-disorder personas (core 1.0).

## 7. Limitations and provenance

- **Violent thoughts remain direction-limited.** The only violence-adjacent corpus (HFO) is
  framed as *harm from others* (the client is the victim), not the client holding violent
  urges. Crisis-conditioning surfaces anger/hostility where the source supports it and raises
  association (one full-alignment match; all five now symptom-grounded rather than
  cosine-only), but the underlying source direction differs from the goal. Every such persona
  is flagged `enriched_for=violent_thoughts` and inferred axes are flagged `repaired_fields`.
- **Inference vs. extraction.** Repaired and crisis-conditioned fields are model inferences
  constrained to the source text; they are tagged, never silently mixed with stated facts.
- **Scarcity and reuse.** Behavioral-crisis pools are small; at small per-label samples a few
  personas recur across goals. Diversity improves with the enriched pools but remains a
  limitation for the rarest categories.
- **No new biographical facts are created.** Repair and enrichment relabel/normalize existing
  source text onto the schema; they do not add diagnoses, demographics, or events.
