"""Run the Qwen-target singleton profile used by the verified 23-case pilot."""
from __future__ import annotations

import sys

from _bootstrap import activate_source
from run_singleton import option_value


TARGET_MODEL = "Qwen/Qwen2.5-7B-Instruct"
RESEARCHER_MODEL = "meta-llama/Llama-3.1-8B-Instruct"
RESEARCHER_REVISION = "0e9e39f249a16976918f6564b8830bc894c89659"

LOCKED_OPTIONS = {
    "--target-model": TARGET_MODEL,
    "--researcher-model": RESEARCHER_MODEL,
    "--researcher-revision": RESEARCHER_REVISION,
    "--condition": "neutral",
    "--method-protocol": "1011_method_v1",
    "--max-goal-convergence-turns": "0",
    "--final-readout-protocol": "safety_negative_examples_v1",
    "--direct-response-prompt-protocol": "counterfactual_prevention_v1",
    "--research-language-profile": "clinical_safety_terminology_v1",
}


def locked_argv(argv: list[str]) -> list[str]:
    result = list(argv)
    for required_url in ("--target-base-url", "--researcher-base-url"):
        if option_value(result, required_url) is None:
            raise SystemExit(f"{required_url} is required for the verified local profile")
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
