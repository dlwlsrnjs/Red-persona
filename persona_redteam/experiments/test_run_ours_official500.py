import pytest

from experiments.run_ours_official500 import CANONICAL_ARGUMENTS, canonical_argv


def test_canonical_ours_locks_method_defining_arguments():
    arguments = canonical_argv([
        "--cases", "cases.json",
        "--output-dir", "out",
        "--campaign-dir", "campaign",
        "--target-total", "500",
    ])
    assert arguments[-len(CANONICAL_ARGUMENTS):] == list(CANONICAL_ARGUMENTS)
    assert arguments.count("--condition") == 1
    assert arguments[arguments.index("--condition") + 1] == "neutral"
    assert arguments[arguments.index("--final-readout-protocol") + 1] == (
        "jargon_history_bridge_v1"
    )
    assert "--final-response-only" in arguments


@pytest.mark.parametrize(
    "override",
    [
        ["--condition", "oracle_hint"],
        ["--condition=oracle_hint"],
        ["--final-readout-protocol", "legacy_v15"],
        ["--target-model", "another-model"],
        ["--ablation-variant", "persona_only"],
        ["--no-research-dialogue-output-dir", "out"],
        ["--omit-target-system-prompt"],
        ["--allow-truncated"],
    ],
)
def test_canonical_ours_rejects_ablation_overrides(override):
    with pytest.raises(ValueError):
        canonical_argv(override)
