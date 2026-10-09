import importlib.util
import json
from pathlib import Path
import sys


SCRIPT = Path(__file__).resolve().parents[1] / "run_baseline_matrix.py"
SPEC = importlib.util.spec_from_file_location("run_baseline_matrix", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_default_matrix_builds_eight_methods_for_two_targets():
    targets, adversary, methods = MODULE.load_matrix_config(MODULE.DEFAULT_CONFIG)
    jobs = MODULE.build_jobs(
        targets=targets,
        adversary=adversary,
        methods=methods,
        input_path=MODULE.DEFAULT_INPUT,
        output_root=Path("out"),
        pilot_cases=1,
        retry_failed=False,
    )
    assert len(jobs) == 16
    assert len({job.target_name for job in jobs}) == 2
    assert len({job.method for job in jobs}) == 8
    assert all("--limit" in job.command for job in jobs)
    gpt_jobs = [job for job in jobs if job.target_name == "gpt4o"]
    assert all("openai_batch" in job.command for job in gpt_jobs)
    assert all("625" in job.command for job in gpt_jobs)


def test_profiles_preserve_method_distinctions():
    assert MODULE.METHOD_PROFILES["direct"] == ()
    assert "--many-shot-examples" in MODULE.METHOD_PROFILES["many_shot"]
    assert "--pair-streams" in MODULE.METHOD_PROFILES["pair"]
    assert "--branching-factor" in MODULE.METHOD_PROFILES["tap"]
    assert MODULE.METHOD_PROFILES["crescendo"] != MODULE.METHOD_PROFILES["tap"]


def test_dry_run_has_16_concurrent_jobs_and_pcsa_phase2(capsys):
    assert MODULE.main(["--dry-run"]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["parallelism"] == {
        "job_count": 16,
        "max_concurrent_jobs": 16,
        "target_count": 2,
        "method_count": 8,
    }
    assert value["dataset"]["cases_per_job"] == 1
    assert value["pcsa"] == {
        "phase": 2,
        "phase1_enabled": False,
        "status": "pending",
        "persona_conditioned": True,
    }


def test_remote_target_requires_credential(monkeypatch):
    targets, adversary, _ = MODULE.load_matrix_config(MODULE.DEFAULT_CONFIG)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    errors = MODULE.preflight_errors(targets=targets, adversary=adversary)
    assert any("OPENAI_API_KEY" in error for error in errors)
