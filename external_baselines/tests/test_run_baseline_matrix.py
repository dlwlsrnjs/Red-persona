import importlib.util
import json
from pathlib import Path
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "run_baseline_matrix.py"
SPEC = importlib.util.spec_from_file_location("run_baseline_matrix", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_default_matrix_builds_nine_methods_for_two_targets():
    targets, adversary, pcsa_evaluator, methods = MODULE.load_matrix_config(MODULE.DEFAULT_CONFIG)
    jobs = MODULE.build_jobs(
        targets=targets,
        adversary=adversary,
        pcsa_evaluator=pcsa_evaluator,
        methods=methods,
        input_path=MODULE.DEFAULT_INPUT,
        cohort_index_path=MODULE.DEFAULT_COHORT_INDEX,
        output_root=Path("out"),
        pilot_cases=1,
        retry_failed=False,
    )
    assert len(jobs) == 18
    assert len({job.target_name for job in jobs}) == 2
    assert len({job.method for job in jobs}) == 9
    assert all("--limit" in job.command for job in jobs)
    assert all(str(MODULE.DEFAULT_COHORT_INDEX) in job.command for job in jobs)
    gpt_jobs = [job for job in jobs if job.target_name == "gpt4o"]
    assert all("openai_batch" in job.command for job in gpt_jobs)
    qwen_pcsa = next(
        job for job in jobs
        if job.target_name == "qwen7b_instruct" and job.method == "pcsa_phase2"
    )
    assert qwen_pcsa.command[qwen_pcsa.command.index("--batch-case-concurrency") + 1] == "32"
    assert qwen_pcsa.command[qwen_pcsa.command.index("--sync-case-concurrency") + 1] == "16"


def test_qwen_consuming_jobs_are_round_robin_distributed_across_replicas():
    targets, adversary, pcsa_evaluator, methods = MODULE.load_matrix_config(MODULE.DEFAULT_CONFIG)
    replicas = tuple(f"http://127.0.0.1:{8000 + index}/v1" for index in range(7))
    jobs = MODULE.build_jobs(
        targets=targets,
        adversary=adversary,
        pcsa_evaluator=pcsa_evaluator,
        methods=methods,
        input_path=MODULE.DEFAULT_INPUT,
        cohort_index_path=MODULE.DEFAULT_COHORT_INDEX,
        output_root=Path("out"),
        pilot_cases=1,
        retry_failed=False,
        qwen_endpoints=replicas,
    )
    assigned = [job.qwen_endpoint for job in jobs if job.qwen_endpoint]
    assert len(assigned) == 15
    assert set(assigned) == set(replicas)
    assert max(assigned.count(endpoint) for endpoint in replicas) == 3
    for job in jobs:
        if job.qwen_endpoint:
            assert job.qwen_endpoint in job.command


def test_profiles_preserve_method_distinctions():
    assert MODULE.METHOD_PROFILES["direct"] == ()
    assert "--many-shot-examples" in MODULE.METHOD_PROFILES["many_shot"]
    assert "--pair-streams" in MODULE.METHOD_PROFILES["pair"]
    assert "--branching-factor" in MODULE.METHOD_PROFILES["tap"]
    assert MODULE.METHOD_PROFILES["crescendo"] != MODULE.METHOD_PROFILES["tap"]
    assert MODULE.METHOD_PROFILES["pcsa_phase2"] == (
        "--max-turns", "4", "--pcsa-candidates", "4"
    )
    assert MODULE.METHOD_PROFILES["red_teaming"] == ("--max-turns", "4")
    assert MODULE.METHOD_PROFILES["pair"] == (
        "--max-turns", "3", "--pair-streams", "5"
    )
    assert MODULE.METHOD_PROFILES["tap"] == (
        "--max-turns", "4", "--tree-width", "2", "--branching-factor", "2"
    )


def test_paper_call_budget_policy_has_expected_target_ceilings():
    policy = MODULE.PAPER_BUDGET_POLICY
    assert policy["name"] == "red-persona-paper-v1"
    assert policy["max_dialogue_turns"] == 4
    assert {
        method: settings["max_target_calls"]
        for method, settings in policy["methods"].items()
    } == {
        "direct": 1,
        "skeleton_key": 1,
        "many_shot": 1,
        "red_teaming": 4,
        "pair": 15,
        "tap": 14,
        "crescendo": 6,
        "therapist_crescendo": 6,
        "pcsa_phase2": 16,
    }


def test_dry_run_has_18_concurrent_jobs_and_pcsa_phase2(capsys):
    assert MODULE.main(["--dry-run"]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["parallelism"] == {
        "job_count": 18,
        "max_concurrent_jobs": 18,
        "target_count": 2,
        "method_count": 9,
        "qwen_replica_count": 1,
        "job_retries": 2,
    }
    assert value["dataset"]["cases_per_job"] == 1
    assert value["pcsa_phase2"] == {
        "status": "configured",
        "phase": 2,
        "phase1_enabled": False,
        "phase1_replacement": "fixed_red_persona_profile_and_pathology_route",
        "max_turns": 4,
        "candidates_per_turn": 4,
    }
    assert value["call_budget_policy"] == MODULE.PAPER_BUDGET_POLICY
    assert all("--retry-failed" in job["command"] for job in value["jobs"])


def test_dry_run_records_seven_qwen_replica_pool(capsys):
    replicas = [f"http://127.0.0.1:{8000 + index}/v1" for index in range(7)]
    arguments = ["--dry-run"]
    for endpoint in replicas:
        arguments.extend(("--qwen-endpoint", endpoint))
    assert MODULE.main(arguments) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["parallelism"]["qwen_replica_count"] == 7
    assert value["qwen_replica_pool"]["endpoints"] == replicas
    assert len({job["qwen_endpoint"] for job in value["jobs"] if job["qwen_endpoint"]}) == 7


def test_full_matrix_uses_official_500(capsys):
    assert MODULE.main(["--dry-run", "--full-500"]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["dataset"]["expected_full_count"] == 500
    assert value["dataset"]["cases_per_job"] == 500
    assert value["dataset"]["case_start"] == 0
    assert value["dataset"]["case_stop_exclusive"] == 500
    assert value["dataset"]["cohort_index"] == str(MODULE.DEFAULT_COHORT_INDEX.resolve())
    assert all("--limit" not in job["command"] for job in value["jobs"])


def test_matrix_supports_nonoverlapping_cost_shards(capsys):
    assert MODULE.main(
        [
            "--dry-run",
            "--target-name", "gpt4o",
            "--case-start", "375",
            "--pilot-cases", "125",
        ]
    ) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["dataset"]["case_start"] == 375
    assert value["dataset"]["case_stop_exclusive"] == 500
    assert value["dataset"]["cases_per_job"] == 125
    assert all("--start" in job["command"] for job in value["jobs"])
    assert all(job["target"] == "gpt4o" for job in value["jobs"])


def test_matrix_can_filter_to_qwen_methods_without_pcsa_or_openai(capsys, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    arguments = ["--dry-run", "--target-name", "qwen7b_instruct"]
    for method in MODULE.METHOD_PROFILES:
        if method != "pcsa_phase2":
            arguments.extend(("--method", method))
    assert MODULE.main(arguments) == 0
    value = json.loads(capsys.readouterr().out)
    assert len(value["jobs"]) == 8
    assert value["parallelism"]["target_count"] == 1
    assert value["parallelism"]["method_count"] == 8
    assert value["pcsa_phase2"]["status"] == "not_selected"
    assert all(job["target"] == "qwen7b_instruct" for job in value["jobs"])


def test_remote_target_requires_credential(monkeypatch):
    targets, adversary, pcsa_evaluator, _ = MODULE.load_matrix_config(MODULE.DEFAULT_CONFIG)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    errors = MODULE.preflight_errors(
        targets=targets,
        adversary=adversary,
        pcsa_evaluator=pcsa_evaluator,
    )
    assert any("OPENAI_API_KEY" in error for error in errors)


def test_official_openai_endpoint_cannot_use_sync_transport():
    with pytest.raises(ValueError, match="must use openai_batch"):
        MODULE._endpoint(
            {
                "name": "gpt4o",
                "endpoint": "https://api.openai.com/v1",
                "model": "gpt-4o",
                "api_key_env": "OPENAI_API_KEY",
                "transport": "sync",
            },
            require_name=True,
        )


def test_luna_llama_matrix_uses_batch_reasoning_and_local_llama():
    config = MODULE.BASELINE_DIR / "matrix_gpt6_luna_llama.json"
    targets, adversary, pcsa_evaluator, methods = MODULE.load_matrix_config(config)
    jobs = MODULE.build_jobs(
        targets=targets,
        adversary=adversary,
        pcsa_evaluator=pcsa_evaluator,
        methods=methods,
        input_path=MODULE.DEFAULT_INPUT,
        cohort_index_path=MODULE.DEFAULT_COHORT_INDEX,
        output_root=Path("out"),
        pilot_cases=10,
        retry_failed=True,
    )
    luna = [job for job in jobs if job.target_name == "gpt6_luna"]
    llama = [job for job in jobs if job.target_name == "llama31_8b_instruct"]
    assert len(luna) == len(llama) == 9
    assert all("openai_batch" in job.command for job in luna)
    assert all("--target-reasoning-effort" in job.command for job in luna)
    assert all("none" in job.command for job in luna)
    assert all("http://127.0.0.1:8100/v1" in job.command for job in llama)
    assert all("--limit" in job.command and "10" in job.command for job in jobs)
