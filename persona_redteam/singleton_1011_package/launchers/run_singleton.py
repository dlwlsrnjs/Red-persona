"""Run one frozen GPT-4o singleton lane from the copied 1011 snapshot."""
from __future__ import annotations

import sys

from _bootstrap import activate_source

TARGET_MODEL = "gpt-4o-2024-11-20"
RESEARCHER_MODEL = "Qwen/Qwen2.5-7B-Instruct"
RESEARCHER_REVISION = "a09a35458c702b33eeacc393d103063234e8bc28"

LOCKED_OPTIONS = {
    "--target-model": TARGET_MODEL,
    "--researcher-model": RESEARCHER_MODEL,
    "--researcher-revision": RESEARCHER_REVISION,
    "--api-mode": "batch",
    "--condition": "neutral",
    "--method-protocol": "1011_method_v1",
    "--max-goal-convergence-turns": "0",
    "--final-readout-protocol": "safety_negative_examples_v1",
    "--direct-response-prompt-protocol": "counterfactual_prevention_v1",
    "--research-language-profile": "clinical_safety_terminology_v1",
}


def option_value(argv: list[str], name: str) -> str | None:
    prefix = name + "="
    for index, token in enumerate(argv):
        if token.startswith(prefix):
            return token[len(prefix):]
        if token == name:
            if index + 1 >= len(argv):
                raise SystemExit(f"{name} requires a value")
            return argv[index + 1]
    return None


def locked_argv(argv: list[str]) -> list[str]:
    if "--target-base-url" in argv or any(
        token.startswith("--target-base-url=") for token in argv
    ):
        raise SystemExit("This package permits only the OpenAI GPT-4o target, not a local target.")
    result = list(argv)
    for name, required in LOCKED_OPTIONS.items():
        current = option_value(result, name)
        if current is not None and current != required:
            raise SystemExit(f"{name} is locked to {required!r}; received {current!r}")
        if current is None:
            result.extend((name, required))
    if "--require-strict-harmful-goal-v3" not in result:
        result.append("--require-strict-harmful-goal-v3")
    if option_value(result, "--target-workers") is None:
        result.extend(("--target-workers", "128"))
    if option_value(result, "--researcher-workers") is None:
        result.extend(("--researcher-workers", "32"))
    return result


def main() -> None:
    activate_source()
    from our_method.run_1011_method import main as production_main

    sys.argv = [sys.argv[0], *locked_argv(sys.argv[1:])]
    production_main()


if __name__ == "__main__":
    main()

