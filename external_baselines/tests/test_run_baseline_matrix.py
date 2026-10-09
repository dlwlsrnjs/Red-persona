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


def test_dry_run_has_18_concurrent_jobs_and_pcsa_phase2(capsys):
    assert MODULE.main(["--dry-run"]) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["parallelism"] == {
        "job_count": 18,
        "max_concurrent_jobs": 18,
        "target_count": 2,
        "method_count": 9,
        "qwen_replica_count": 1,
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
    assert value["dataset"]["cohort_index"] == str(MODULE.DEFAULT_COHORT_INDEX.resolve())
    assert all("--limit" not in job["command"] for job in value["jobs"])


def test_remote_target_requires_credential(monkeypatch):
    targets, adversary, pcsa_evaluator, _ = MODULE.load_matrix_config(MODULE.DEFAULT_CONFIG)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    errors = MODULE.preflight_errors(
        targets=targets,
        adversary=adversary,
        pcsa_evaluator=pcsa_evaluator,
    )
    assert any("OPENAI_API_KEY" in error for error in errors)
