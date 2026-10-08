# Legacy prompt pipeline backup (2026-10-09)

This directory preserves superseded exploratory files without keeping them in the active pipeline.
Nothing here is imported by the current persona co-research runner or evaluator.

The archived sequence covers:

- adaptive and fixed latent-request pilots;
- Lexi JSON and interleaved-dialogue experiments;
- early fixed manifestation prompt packs and prompt-bank expansion;
- early Qwen framing pilots;
- the matching tests, fixtures, specifications, and notes for those implementations.

The active implementation is now:

- `experiments/qwen_target_persona_research_dialogue.py`;
- `experiments/evaluate_persona_co_research.py`;
- `experiments/evaluate_cares_official.py`;
- `configs/persona_co_research_spec.json`;
- `configs/persona_co_research_evaluation.json`;
- `evaluation/prompts/persona_co_research_recovery_evaluator.txt`;
- `evaluation/prompts/cares_official_response_evaluator.txt`.

The active final protocol uses eight independent branches. Each branch first obtains the target's
own latent-request reconstruction and then adds a goal-free transition to an actual counseling
reply while retaining the complete speaker-attributed history and explicit safety boundary.
