# Why the first persona-framing pilot failed

The first 6-goal one-shot pilot is not evidence that persona strengthening itself is
ineffective. It combined a weak elicitation format, a defensive context, and a
misconfigured mode audit. It also differed materially from earlier multi-turn runs.

## 1. The generated artifacts were descriptions, not eliciting utterances

Across the 24 frozen candidates in the first pilot, there was only one question mark
and no `you` or `your` token. The candidates averaged about 141 words, but did not ask
the counselor to reassure, interpret, validate, or agree. Earlier inputs were
first-person client utterances with substantially more self-reference and explicit
agreement or authority cues.

This distinction matters: internalizing a hidden goal in a persona state does not by
itself specify the observable conversational act through which that state should
affect the next counselor response.

## 2. The response model received a defensive reference

The `clinical_context` and iterative case-reframing path pasted a reference into the
tested model's prompt. That reference explicitly instructed the reader to distinguish
empathy from endorsement and preserve role boundaries. It therefore acted as a safety
primer. The reference can ground candidate generation, but it must not be supplied to
the tested response model when the research question concerns the persona's effect.

## 3. The adaptive pressure from the earlier experiment disappeared

Earlier runs could use up to six turns and condition the next turn on the counselor's
previous response. The first one-shot pilot removed this adaptive history without
putting an equivalent elicitation move into the single input. The resulting comparison
changed both the number of turns and the functional form of the prompt.

The corrected one-shot design keeps a single response turn but requires every candidate
to be a first-person client message addressed to the counselor and to contain exactly
one strategy-specific elicitation question.

## 4. The auxiliary mode audit was misconfigured

The response prompt asked for a counselor reply, but the auxiliary audit treated
`case_analysis` and `mixed` as eligible outputs for the persona-analysis arm. The
reported `17/24 case_analysis` count is therefore confounded by the requested audit
mode and cannot establish that persona-analysis framing caused a clean task shift.

All experimental arms now require `live_counseling` or
`counseling_recommendation` output. Analysis remains an internal input framing only.

## 5. Earlier apparent success is not a clean baseline

On the same six goals, the completed GPT-4o-mini-generator run had 0/6 strict unsafe
outcomes. The partial Qwen and Lexi runs had 4/6 and 2/6, respectively, but exact
8-gram goal overlap occurred in three of the four Qwen unsafe cases and both Lexi
unsafe cases. Across the larger partial artifacts, unsafe outcomes also exist without
exact leakage, so leakage is not the whole effect; however, it materially confounds
the same-six comparison.

The corrected study must report goal exposure, turn count, generator, response model,
and selection procedure alongside the PCSA outcomes.

## Corrections made

- Candidate validation now requires first-person language, direct counselor address,
  and exactly one elicitation question.
- Evaluation and safety-policy meta-language is rejected from persona messages.
- The clinical reference is used to ground generation but is removed from the tested
  responder prompt, except in the explicit context control arm.
- Every arm is audited as a requested counseling response.
- Generator retries start from a clean context so rejected JSON does not crowd out the
  task instructions.
- The iterative optimizer uses the same utterance constraints as the one-shot pilot.

The original pilot remains useful as a failed-design ablation. It should not be cited
as a valid estimate of optimized red-persona effectiveness or transfer to GPT-4o.
