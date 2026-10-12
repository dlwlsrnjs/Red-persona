from __future__ import annotations

from argparse import Namespace
import hashlib
import json
from pathlib import Path

from experiments.final197.launch_single_readout_qwen import base_command, ranges


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "experiments/final197/QWEN_SINGLE_READOUT_CODE_MANIFEST.json"


def test_registered_code_and_prompt_hashes_match() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    for relative, expected in manifest["files"].items():
        path = ROOT / relative
        assert path.is_file(), relative
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, relative


def test_eight_lanes_reproduce_registered_final197_slices() -> None:
    assert ranges(0, 197, 8) == [
        (0, 25),
        (25, 50),
        (50, 75),
        (75, 100),
        (100, 125),
        (125, 149),
        (149, 173),
        (173, 197),
    ]


def test_no_history_changes_only_registered_context_ablation(tmp_path: Path) -> None:
    args = Namespace(
        cases=tmp_path / "cases.json",
        selection_path=tmp_path / "selection.json",
        expected_cases=197,
        target_workers=128,
        researcher_workers=32,
        arm="with_history",
    )
    history = base_command(args, tmp_path / "campaign-a", tmp_path / "result-a")
    args.arm = "no_history"
    no_history = base_command(
        args, tmp_path / "campaign-b", tmp_path / "result-b"
    )
    assert "--ablation-variant" not in history
    index = no_history.index("--ablation-variant")
    assert no_history[index + 1] == "no_prior_dialogue"
    for required in (
        "1011_method_v1",
        "safety_negative_examples_v1",
        "counterfactual_prevention_v1",
        "clinical_safety_terminology_v1",
    ):
        assert required in history
        assert required in no_history
