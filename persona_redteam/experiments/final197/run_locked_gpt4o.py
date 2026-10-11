"""Run the frozen Final-197 GPT-4o target protocol."""
from __future__ import annotations

import sys
from typing import Sequence

from experiments import run_jmir_persona_batch_api


LOCKED_ARGUMENTS = {
    "--target-model",
    "--target-base-url",
    "--researcher-model",
    "--researcher-revision",
    "--condition",
    "--final-readout-protocol",
    "--direct-response-prompt-protocol",
    "--research-language-profile",
    "--ablation-variant",
    "--no-research-dialogue-output-dir",
    "--omit-target-system-prompt",
    "--allow-truncated",
    "--final-response-only",
    "--require-harmful-goal-v2",
    "--require-strict-harmful-goal-v3",
    "--api-mode",
    "--target-total",
    "--target-workers",
}

CANONICAL_ARGUMENTS = (
    "--target-model", "gpt-4o-2024-11-20",
    "--researcher-model", "Qwen/Qwen2.5-7B-Instruct",
    "--researcher-revision", "a09a35458c702b33eeacc393d103063234e8bc28",
    "--condition", "neutral",
    "--final-readout-protocol", "jargon_history_bridge_v1",
    "--direct-response-prompt-protocol", "counterfactual_prevention_v1",
    "--research-language-profile", "clinical_safety_terminology_v1",
    "--require-strict-harmful-goal-v3",
    "--api-mode", "batch",
    "--target-total", "197",
    "--target-workers", "128",
)


def canonical_argv(user_arguments: Sequence[str]) -> list[str]:
    conflicts = [
        argument for argument in user_arguments
        if argument.split("=", 1)[0] in LOCKED_ARGUMENTS
    ]
    if conflicts:
        names = ", ".join(sorted({item.split("=", 1)[0] for item in conflicts}))
        raise ValueError(
            "Final-197 GPT-4o v1 locks these arguments; use the general "
            f"runner for ablations: {names}"
        )
    return [*user_arguments, *CANONICAL_ARGUMENTS]


def main() -> None:
    try:
        arguments = canonical_argv(sys.argv[1:])
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    sys.argv = [sys.argv[0], *arguments]
    run_jmir_persona_batch_api.main()


if __name__ == "__main__":
    main()
