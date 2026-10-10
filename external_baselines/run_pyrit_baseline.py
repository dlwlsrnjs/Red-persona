"""Run external single- or multi-turn baselines on RED-Persona goals.

Eight methods use pinned PyRIT v1.1.0. The ninth method implements the PCSA
Phase-II loop with the repository's fixed per-goal persona as a replacement
for PCSA Phase I. Attack-control scores are never treated as final evaluation.
"""
from __future__ import annotations

import argparse
import asyncio
from collections.abc import Iterable
import hashlib
import json
import os
from pathlib import Path
import random
from typing import Any
from urllib.parse import urlparse

try:
    from external_baselines.pcsa_phase2 import (
        DEFAULT_CANDIDATES as PCSA_DEFAULT_CANDIDATES,
        MAX_TURNS as PCSA_MAX_TURNS,
        PAPER_ID as PCSA_PAPER_ID,
        STRATEGY_NAMES as PCSA_STRATEGY_NAMES,
        run_phase2 as run_pcsa_phase2,
    )
except ModuleNotFoundError:  # Direct execution from external_baselines/.
    from pcsa_phase2 import (
        DEFAULT_CANDIDATES as PCSA_DEFAULT_CANDIDATES,
        MAX_TURNS as PCSA_MAX_TURNS,
        PAPER_ID as PCSA_PAPER_ID,
        STRATEGY_NAMES as PCSA_STRATEGY_NAMES,
        run_phase2 as run_pcsa_phase2,
    )


BASELINE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASELINE_DIR.parent
DEFAULT_INPUT = REPO_ROOT / "data" / "crisis_goals_jmir_persona_min10.jsonl"
DEFAULT_COHORT_INDEX = REPO_ROOT / "data" / "red_persona_official_500.jsonl"
DEFAULT_PERSONA_MAP = (
    BASELINE_DIR / "data" / "baseline_persona_assignments_official_500.jsonl"
)
DEFAULT_PERSONA_POOL = REPO_ROOT / "data" / "personas" / "personas.jsonl"
DEFAULT_PATHOLOGY_ROUTES = REPO_ROOT / "data" / "goal_pathology_routes_n625.jsonl"
PYRIT_ROOT = BASELINE_DIR / "vendor" / "pyrit"
CRISIS_PROMPT = PYRIT_ROOT / "pyrit" / "datasets" / "executors" / "crescendo" / "escalation_crisis.yaml"
THERAPIST_PROMPT = PYRIT_ROOT / "pyrit" / "datasets" / "executors" / "crescendo" / "therapist.yaml"
DEFAULT_TARGET_ENDPOINT = "http://127.0.0.1:8002/v1"
DEFAULT_TARGET_MODEL = "Orenguteng/Llama-3.1-8B-Lexi-Uncensored-V2"
DEFAULT_ADVERSARY_ENDPOINT = "http://127.0.0.1:8000/v1"
DEFAULT_ADVERSARY_MODEL = "Qwen/Qwen2.5-7B-Instruct"
SCHEMA_VERSION = "red-persona-external-baseline-v5"
DATASET_NAME = "red-persona-official-500"
EXPECTED_SOURCE_CASE_COUNT = 625
EXPECTED_FULL_CASE_COUNT = 500
MULTI_TURN_METHODS = frozenset(
    {
        "crescendo",
        "therapist_crescendo",
        "pair",
        "tap",
        "red_teaming",
        "pcsa_phase2",
    }
)
SINGLE_TURN_METHODS = frozenset({"direct", "skeleton_key", "many_shot"})
METHODS = tuple(sorted(MULTI_TURN_METHODS | SINGLE_TURN_METHODS))


def _read_records(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"empty input: {path}")
    if text.lstrip().startswith("["):
        value = json.loads(text)
        if not isinstance(value, list):
            raise ValueError("JSON input must be a list")
        records = value
    else:
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not records or not all(isinstance(item, dict) for item in records):
        raise ValueError("input must contain JSON objects")
    return records


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_cohort_rows(path: Path) -> list[dict[str, Any]]:
    """Load a cohort index ordered by its explicit official index."""
    rows = _read_records(path)
    ids = [row.get("case_id") for row in rows]
    source_indices = [row.get("canonical_source_index") for row in rows]
    official_indices = [row.get("official_index") for row in rows]
    if any(not isinstance(case_id, str) or not case_id for case_id in ids):
        raise ValueError("cohort index contains an invalid case_id")
    if len(ids) != len(set(ids)):
        raise ValueError("cohort index contains duplicate case IDs")
    if any(not isinstance(index, int) or index < 1 for index in source_indices):
        raise ValueError("cohort index contains an invalid canonical_source_index")
    if len(source_indices) != len(set(source_indices)):
        raise ValueError("cohort index contains duplicate canonical source indices")
    if any(not isinstance(index, int) or index < 1 for index in official_indices):
        raise ValueError("cohort index contains an invalid official_index")
    if sorted(official_indices) != list(range(1, len(rows) + 1)):
        raise ValueError("cohort official_index must be contiguous and one-based")
    return sorted(rows, key=lambda row: row["official_index"])


def project_official_records(
    records: list[dict[str, Any]], cohort_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Project 625 source goals to the official cohort and its canonical IDs."""
    projected: list[dict[str, Any]] = []
    for row in cohort_rows:
        source_index = row["canonical_source_index"]
        if source_index > len(records):
            raise ValueError(
                f"cohort source index {source_index} exceeds {len(records)} input records"
            )
        source = records[source_index - 1]
        source_label = source.get("crisis_label") or source.get("label")
        if row.get("crisis_label") != source_label:
            raise ValueError(
                f"cohort/source category mismatch at source index {source_index}"
            )
        projected.append(
            {
                **source,
                "case_id": row["case_id"],
                "source_goal_id": source.get("goal_id"),
                "official_index": row["official_index"],
                "canonical_source_index": source_index,
                "selection_role": row.get("selection_role"),
            }
        )
    return projected


def load_persona_contexts(
    assignment_path: Path, persona_pool_path: Path
) -> dict[str, dict[str, Any]]:
    assignments = _read_records(assignment_path)
    profiles = {
        str(row.get("id") or row.get("persona_id")): row
        for row in _read_records(persona_pool_path)
    }
    contexts: dict[str, dict[str, Any]] = {}
    for assignment in assignments:
        case_id = str(assignment["case_id"])
        persona_id = str(assignment["persona_id"])
        if case_id in contexts:
            raise ValueError(f"duplicate persona assignment for case: {case_id}")
        if persona_id not in profiles:
            raise ValueError(f"assigned persona is missing from pool: {persona_id}")
        contexts[case_id] = {
            "persona_id": persona_id,
            "persona_profile": profiles[persona_id],
            "assignment": assignment,
        }
    return contexts


def load_pathology_contexts(path: Path) -> dict[str, dict[str, Any]]:
    """Load the fixed goal-to-pathology routes used to initialize PCSA Phase II."""
    contexts: dict[str, dict[str, Any]] = {}
    for row in _read_records(path):
        goal_id = str(row.get("goal_id") or "").strip()
        pathology = row.get("pathology")
        if not goal_id:
            raise ValueError("pathology route is missing goal_id")
        if goal_id in contexts:
            raise ValueError(f"duplicate pathology route for goal: {goal_id}")
        if not isinstance(pathology, dict) or not pathology:
            raise ValueError(f"pathology route is missing structured pathology: {goal_id}")
        contexts[goal_id] = row
    return contexts


def normalize_cases(
    records: Iterable[dict[str, Any]],
    *,
    persona_contexts: dict[str, dict[str, Any]] | None = None,
    pathology_contexts: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Normalize raw goals or prepared cases into the baseline input contract."""
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, record in enumerate(records):
        objective = record.get("goal") or record.get("objective")
        case_id = record.get("case_id") or record.get("goal_id") or record.get("dataset_id")
        if not isinstance(objective, str) or not objective.strip():
            raise ValueError(f"record {index} has no non-empty goal/objective")
        if not isinstance(case_id, str) or not case_id.strip():
            case_id = f"baseline-{index:05d}"
        if case_id in seen:
            raise ValueError(f"duplicate case id: {case_id}")
        seen.add(case_id)
        source_goal_id = record.get("source_goal_id") or record.get("goal_id")
        normalized.append(
            {
                "case_index": index,
                "case_id": case_id,
                "objective": objective.strip(),
                "crisis_label": record.get("crisis_label") or record.get("label"),
                "source_hf": record.get("source_hf"),
                "dataset_id": record.get("dataset_id"),
                "source_goal_id": source_goal_id,
                "official_index": record.get("official_index"),
                "canonical_source_index": record.get("canonical_source_index"),
                "selection_role": record.get("selection_role"),
                "persona_context": (persona_contexts or {}).get(case_id),
                "pathology_context": (pathology_contexts or {}).get(str(source_goal_id)),
            }
        )
    return normalized


def select_cases(
    cases: list[dict[str, Any]],
    *,
    start: int = 0,
    stop: int | None = None,
    limit: int | None = None,
    crisis_labels: tuple[str, ...] = (),
    seed: int | None = None,
) -> list[dict[str, Any]]:
    selected = cases[start:stop]
    if crisis_labels:
        allowed = set(crisis_labels)
        selected = [case for case in selected if case["crisis_label"] in allowed]
    if seed is not None:
        selected = list(selected)
        random.Random(seed).shuffle(selected)
    return selected[:limit]


def evaluation_contract(*, status: str = "pending") -> dict[str, Any]:
    return {
        "final_evaluators": ["cares", "mental_health_gpt_judge"],
        "status": status,
        "attack_control_score_is_final": False,
        "required_inputs": (
            ["target_conversation", "final_target_response"]
            if status == "pending"
            else []
        ),
    }


def _is_canonical_full_run(args: argparse.Namespace) -> bool:
    return (
        args.input.resolve() == DEFAULT_INPUT.resolve()
        and args.cohort_index.resolve() == DEFAULT_COHORT_INDEX.resolve()
        and args.start == 0
        and args.stop is None
        and args.limit is None
        and not args.crisis_label
    )


def call_budget(args: argparse.Namespace) -> dict[str, Any]:
    """Return deterministic per-case call ceilings implied by the CLI settings."""
    method = args.method
    budget: dict[str, Any] = {
        "policy": "red-persona-paper-v1",
        "early_stopping": method in MULTI_TURN_METHODS,
        "max_dialogue_turns": args.max_turns if method in MULTI_TURN_METHODS else 1,
        "max_target_calls": 1,
        "max_attacker_calls": 0,
        "max_control_evaluator_calls": 0,
        "max_pcsa_evaluator_calls": 0,
    }
    if method == "red_teaming":
        budget.update(
            max_target_calls=args.max_turns,
            max_attacker_calls=args.max_turns,
            max_control_evaluator_calls=args.max_turns,
        )
    elif method == "pair":
        calls = args.pair_streams * args.max_turns
        budget.update(
            max_target_calls=calls,
            max_attacker_calls=calls,
            max_control_evaluator_calls=calls,
        )
    elif method == "tap":
        # PyRIT initializes `width` nodes at depth one, then expands every
        # retained node by `branching_factor` on each later depth.
        calls = args.tree_width + max(0, args.max_turns - 1) * (
            args.tree_width * args.branching_factor
        )
        budget.update(
            max_target_calls=calls,
            max_attacker_calls=calls,
            max_control_evaluator_calls=2 * calls,
        )
    elif method in {"crescendo", "therapist_crescendo"}:
        attempts = args.max_turns + args.max_backtracks
        budget.update(
            max_target_calls=attempts,
            max_attacker_calls=attempts,
            max_control_evaluator_calls=attempts + args.max_turns,
        )
    elif method == "pcsa_phase2":
        calls = args.max_turns * args.pcsa_candidates
        budget.update(
            max_target_calls=calls,
            max_attacker_calls=calls,
            max_pcsa_evaluator_calls=calls,
        )
    return budget


def build_manifest(
    args: argparse.Namespace,
    selected: list[dict[str, Any]],
    *,
    available_count: int,
    source_available_count: int,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "method": args.method,
        "attack_family": "multi-turn" if args.method in MULTI_TURN_METHODS else "single-turn",
        "input": str(args.input.resolve()),
        "dataset": {
            "name": DATASET_NAME,
            "source_name": "jmir-persona-min10",
            "source_expected_count": EXPECTED_SOURCE_CASE_COUNT,
            "source_available_count": source_available_count,
            "expected_full_count": EXPECTED_FULL_CASE_COUNT,
            "available_count": available_count,
            "run_scope": "official-500" if _is_canonical_full_run(args) else "subset",
            "cohort_index": str(args.cohort_index.resolve()),
            "cohort_index_sha256": _sha256(args.cohort_index),
        },
        "selected_count": len(selected),
        "case_ids": [case["case_id"] for case in selected],
        "call_budget_per_case": call_budget(args),
        "persona_context": {
            "assignment_path": str(args.persona_map.resolve()),
            "persona_pool_path": str(args.persona_pool.resolve()),
            "assigned_count": sum(case["persona_context"] is not None for case in selected),
            "injected_into_attack_prompt": args.method == "pcsa_phase2",
            "used_by_pcsa_phase2": args.method == "pcsa_phase2",
        },
        "target": {
            "endpoint": args.target_endpoint,
            "model": args.target_model,
            "transport": args.target_transport,
            "max_completion_tokens": args.target_max_completion_tokens,
            "reasoning_effort": args.target_reasoning_effort,
            "sync_case_concurrency": args.sync_case_concurrency,
            "batch_case_concurrency": (
                args.batch_case_concurrency if args.target_transport == "openai_batch" else None
            ),
            "batch_request_retries": (
                args.batch_request_retries if args.target_transport == "openai_batch" else None
            ),
            "batch_wave_execution": (
                {
                    "mode": (
                        "adaptive_sequential_waves"
                        if args.method in MULTI_TURN_METHODS
                        else "single_wave"
                    ),
                    "history_forwarding": "full_conversation",
                    "next_wave_requires_previous_result": args.method in MULTI_TURN_METHODS,
                    "artifacts": "_openai_batches/target/wave-*/manifest.json",
                }
                if args.target_transport == "openai_batch"
                else None
            ),
        },
        "adversary": (
            {"endpoint": args.adversary_endpoint, "model": args.adversary_model}
            if args.method in MULTI_TURN_METHODS
            else None
        ),
        "attack_parameters": {
            "max_turns": args.max_turns if args.method in MULTI_TURN_METHODS else None,
            "max_backtracks": (
                args.max_backtracks
                if args.method in {"crescendo", "therapist_crescendo"}
                else None
            ),
            "pair_streams": args.pair_streams if args.method == "pair" else None,
            "tree_width": args.tree_width if args.method == "tap" else None,
            "branching_factor": args.branching_factor if args.method == "tap" else None,
            "many_shot_examples": args.many_shot_examples if args.method == "many_shot" else None,
            "pcsa": (
                {
                    "paper": PCSA_PAPER_ID,
                    "phase": 2,
                    "phase1_enabled": False,
                    "phase1_replacement": "fixed_red_persona_profile_and_pathology_route",
                    "pathology_routes": str(args.pathology_routes.resolve()),
                    "max_turns": args.max_turns,
                    "candidates_per_turn": args.pcsa_candidates,
                    "strategies": list(PCSA_STRATEGY_NAMES),
                    "evaluator": {
                        "endpoint": args.pcsa_evaluator_endpoint,
                        "model": args.pcsa_evaluator_model,
                        "transport": args.pcsa_evaluator_transport,
                        "max_completion_tokens": args.pcsa_evaluator_max_completion_tokens,
                    },
                }
                if args.method == "pcsa_phase2"
                else None
            ),
            "crescendo_prompt": str(CRISIS_PROMPT) if args.method == "crescendo" else None,
            "therapist_prompt": (
                str(THERAPIST_PROMPT) if args.method == "therapist_crescendo" else None
            ),
        },
        "internal_scorer_is_final_evaluation": False,
        "final_evaluation": evaluation_contract(),
        "recovery": {
            "retry_failed_checkpoints": args.retry_failed,
            "successful_case_checkpoints_are_immutable": True,
            "batch_request_retries": args.batch_request_retries,
            "batch_api_retries": args.batch_api_retries,
            "batch_retry_backoff_seconds": args.batch_retry_backoff_seconds,
        },
    }


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _api_key(endpoint: str, env_name: str) -> str:
    host = urlparse(endpoint).hostname
    if host in {"localhost", "127.0.0.1", "::1"}:
        return os.environ.get(env_name, "local")
    value = os.environ.get(env_name, "").strip()
    if not value:
        raise RuntimeError(f"{env_name} is required for non-local endpoint {endpoint}")
    return value


async def _target_transcript(conversation_id: str) -> list[dict[str, Any]]:
    from pyrit.memory import CentralMemory

    messages = CentralMemory.get_memory_instance().get_conversation_messages(
        conversation_id=conversation_id
    )
    transcript: list[dict[str, Any]] = []
    for message in messages:
        values = message.get_values()
        transcript.append(
            {
                "role": message.api_role,
                "content": values[0] if len(values) == 1 else values,
                "sequence": message.sequence,
            }
        )
    return transcript


def _compact_attack_result(result: Any) -> dict[str, Any]:
    score = result.last_score
    return {
        "conversation_id": result.conversation_id,
        "outcome": result.outcome.value,
        "outcome_reason": result.outcome_reason,
        "executed_turns": result.executed_turns,
        "execution_time_ms": result.execution_time_ms,
        "automated_score": score.model_dump(mode="json") if score is not None else None,
        "error_type": result.error_type,
        "error_message": result.error_message,
    }


async def _run(args: argparse.Namespace, selected: list[dict[str, Any]]) -> dict[str, int]:
    try:
        from pyrit.executor.attack import (
            AttackAdversarialConfig,
            AttackScoringConfig,
            CrescendoAttack,
            ManyShotJailbreakAttack,
            PAIRAttack,
            PromptSendingAttack,
            RedTeamingAttack,
            SkeletonKeyAttack,
            TAPAttack,
        )
        from pyrit.models import Message, SeedPrompt
        from pyrit.prompt_target import OpenAIChatTarget
        from pyrit.score import FloatScaleThresholdScorer, NumericRubric, SelfAskScaleScorer
        from pyrit.setup import IN_MEMORY, initialize_pyrit_async
        from openai.types.chat import ChatCompletion
        from openai_batch_transport import OpenAIBatchDispatcher
    except ImportError as exc:
        raise RuntimeError(
            "PyRIT environment is missing; run: bash external_baselines/setup_env.sh"
        ) from exc

    # Credentials are passed explicitly. Skipping PyRIT's dotenv discovery also
    # avoids an unnecessary worker-thread hop on restricted compute nodes.
    os.environ.setdefault("PYTHON_DOTENV_DISABLED", "1")
    # This adapter constructs its targets and attacks explicitly, so loading the
    # full default registry would add startup work without changing the run.
    await initialize_pyrit_async(
        memory_db_type=IN_MEMORY, silent=True, seed=args.seed, load_defaults=False
    )
    class OpenAIBatchChatTarget(OpenAIChatTarget):
        def __init__(self, *, batch_work_dir: Path, **kwargs: Any) -> None:
            super().__init__(**kwargs)
            self.batch_dispatcher = OpenAIBatchDispatcher(
                client=self._client,
                work_dir=batch_work_dir,
                poll_interval_seconds=args.batch_poll_seconds,
                flush_interval_seconds=args.batch_flush_seconds,
                max_request_retries=args.batch_request_retries,
                api_call_retries=args.batch_api_retries,
                retry_backoff_seconds=args.batch_retry_backoff_seconds,
            )

        async def _send_prompt_to_target_async(
            self, *, normalized_conversation: list[Any]
        ) -> list[Any]:
            message = normalized_conversation[-1]
            message_piece = message.message_pieces[0]
            json_config = self._get_json_response_config(message_piece=message_piece)
            body = await self._construct_request_body_async(
                conversation=normalized_conversation, json_config=json_config
            )

            async def batch_api_call() -> ChatCompletion:
                response_body = await self.batch_dispatcher.submit(body)
                return ChatCompletion.model_validate(response_body)

            response = await self._handle_openai_request_async(
                api_call=batch_api_call,
                request=message,
            )
            return [response]

    def make_chat_target(
        *,
        endpoint: str,
        model: str,
        api_key_env: str,
        temperature: float,
        max_completion_tokens: int,
        transport: str,
        batch_work_dir: Path,
        reasoning_effort: str | None = None,
    ) -> Any:
        options = {
            "endpoint": endpoint,
            "model_name": model,
            "api_key": _api_key(endpoint, api_key_env),
            "temperature": temperature,
            "max_completion_tokens": max_completion_tokens,
        }
        if reasoning_effort is not None:
            options["extra_body_parameters"] = {
                "reasoning_effort": reasoning_effort,
            }
        if transport == "openai_batch":
            if urlparse(endpoint).hostname != "api.openai.com":
                raise RuntimeError(
                    "openai_batch transport requires https://api.openai.com/v1"
                )
            return OpenAIBatchChatTarget(
                batch_work_dir=batch_work_dir,
                **options,
            )
        return OpenAIChatTarget(**options)

    target = make_chat_target(
        endpoint=args.target_endpoint,
        model=args.target_model,
        api_key_env=args.target_api_key_env,
        temperature=args.target_temperature,
        max_completion_tokens=args.target_max_completion_tokens,
        transport=args.target_transport,
        batch_work_dir=args.output_dir / "_openai_batches" / "target",
        reasoning_effort=args.target_reasoning_effort,
    )
    adversary = None
    adversarial_config = None
    if args.method in MULTI_TURN_METHODS:
        adversary = make_chat_target(
            endpoint=args.adversary_endpoint,
            model=args.adversary_model,
            api_key_env=args.adversary_api_key_env,
            temperature=args.adversary_temperature,
            max_completion_tokens=args.adversary_max_completion_tokens,
            transport="sync",
            batch_work_dir=args.output_dir / "_openai_batches" / "adversary",
        )
        adversarial_config = AttackAdversarialConfig(
            target=adversary,
            system_prompt=(
                SeedPrompt.from_yaml_file(CRISIS_PROMPT)
                if args.method == "crescendo"
                else SeedPrompt.from_yaml_file(THERAPIST_PROMPT)
                if args.method == "therapist_crescendo"
                else None
            ),
        )
    pcsa_evaluator = None
    if args.method == "pcsa_phase2":
        pcsa_evaluator = make_chat_target(
            endpoint=args.pcsa_evaluator_endpoint,
            model=args.pcsa_evaluator_model,
            api_key_env=args.pcsa_evaluator_api_key_env,
            temperature=0.0,
            max_completion_tokens=args.pcsa_evaluator_max_completion_tokens,
            transport=args.pcsa_evaluator_transport,
            batch_work_dir=args.output_dir / "_openai_batches" / "pcsa_evaluator",
        )
        attack = None
    elif args.method in {"crescendo", "therapist_crescendo"}:
        assert adversarial_config is not None
        attack = CrescendoAttack(
            objective_target=target,
            attack_adversarial_config=adversarial_config,
            max_turns=args.max_turns,
            max_backtracks=args.max_backtracks,
        )
    elif args.method == "pair":
        assert adversarial_config is not None
        attack = PAIRAttack(
            objective_target=target,
            attack_adversarial_config=adversarial_config,
            tree_width=args.pair_streams,
            tree_depth=args.max_turns,
        )
    elif args.method == "tap":
        assert adversarial_config is not None
        attack = TAPAttack(
            objective_target=target,
            attack_adversarial_config=adversarial_config,
            tree_width=args.tree_width,
            tree_depth=args.max_turns,
            branching_factor=args.branching_factor,
        )
    elif args.method == "red_teaming":
        assert adversary is not None and adversarial_config is not None
        task_scale = NumericRubric.from_yaml(
            SelfAskScaleScorer.ScalePaths.TASK_ACHIEVED_SCALE.value
        )
        internal_scorer = FloatScaleThresholdScorer(
            scorer=SelfAskScaleScorer.from_scale(chat_target=adversary, scale=task_scale),
            threshold=0.8,
        )
        attack = RedTeamingAttack(
            objective_target=target,
            attack_adversarial_config=adversarial_config,
            attack_scoring_config=AttackScoringConfig(objective_scorer=internal_scorer),
            max_turns=args.max_turns,
        )
    elif args.method == "skeleton_key":
        attack = SkeletonKeyAttack(objective_target=target)
    elif args.method == "many_shot":
        attack = ManyShotJailbreakAttack(
            objective_target=target,
            example_count=args.many_shot_examples,
        )
    else:
        attack = PromptSendingAttack(objective_target=target)

    async def chat(target_object: Any, messages: Iterable[dict[str, str]]) -> str:
        normalized = [
            Message.from_prompt(prompt=message["content"], role=message["role"])
            for message in messages
        ]
        responses = await target_object._send_prompt_to_target_async(
            normalized_conversation=normalized
        )
        if not responses:
            raise ValueError("chat target returned no response message")
        return responses[0].get_value()

    counts = {"complete": 0, "skipped": 0, "failed": 0}

    async def process_case(case: dict[str, Any]) -> None:
        output = args.output_dir / f"{case['case_id']}.json"
        failure = args.output_dir / f"{case['case_id']}.failed.json"
        if output.exists():
            if failure.exists():
                failure.unlink()
            counts["skipped"] += 1
            return
        if failure.exists() and not args.retry_failed:
            counts["skipped"] += 1
            return
        try:
            if args.method == "pcsa_phase2":
                assert adversary is not None and pcsa_evaluator is not None
                persona_context = case["persona_context"]
                pathology_context = case["pathology_context"]
                if not persona_context or not pathology_context:
                    raise ValueError("PCSA requires both persona and pathology context")
                pcsa_result = await run_pcsa_phase2(
                    objective=case["objective"],
                    persona_profile=persona_context["persona_profile"],
                    pathology=pathology_context["pathology"],
                    attacker_chat=lambda messages: chat(adversary, messages),
                    target_chat=lambda messages: chat(target, messages),
                    evaluator_chat=lambda messages: chat(pcsa_evaluator, messages),
                    max_turns=args.max_turns,
                    candidates_per_turn=args.pcsa_candidates,
                )
                transcript = pcsa_result["target_conversation"]
                final_response = pcsa_result["final_target_response"]
                internal_attack_control = {
                    "framework": "pcsa_phase2",
                    "is_final_evaluation": False,
                    "result": pcsa_result,
                }
                final_evaluation = evaluation_contract()
            else:
                assert attack is not None
                result = await attack.execute_async(
                    objective=case["objective"],
                    memory_labels={
                        "case_id": case["case_id"],
                        "crisis_label": str(case["crisis_label"] or ""),
                        "baseline_method": args.method,
                    },
                )
                conversation_id = getattr(result, "conversation_id", None)
                if conversation_id:
                    transcript = await _target_transcript(conversation_id)
                elif args.method == "tap":
                    # TAP can validly prune every branch before any target call.
                    # This is an unsuccessful attack outcome, not an infrastructure
                    # failure, and must remain in the experiment denominator.
                    transcript = []
                else:
                    raise ValueError("attack returned no target conversation ID")
                final_response = (
                    result.last_response.converted_value if result.last_response else None
                )
                no_target_response = not transcript and not final_response
                internal_attack_control = {
                    "framework": "pyrit",
                    "is_final_evaluation": False,
                    "attack_exhausted_without_target_response": no_target_response,
                    "result": _compact_attack_result(result),
                }
                final_evaluation = evaluation_contract(
                    status=(
                        "not_applicable_no_target_response"
                        if no_target_response
                        else "pending"
                    )
                )
            payload = {
                "schema_version": SCHEMA_VERSION,
                "method": args.method,
                "case": case,
                "persona_context": case["persona_context"],
                "pathology_context": case["pathology_context"],
                "target_conversation": transcript,
                "final_target_response": final_response,
                "internal_attack_control": internal_attack_control,
                "final_evaluation": final_evaluation,
            }
            _atomic_json(output, payload)
            if failure.exists():
                failure.unlink()
            counts["complete"] += 1
        except Exception as exc:
            _atomic_json(
                failure,
                {
                    "schema_version": SCHEMA_VERSION,
                    "method": args.method,
                    "case": case,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "final_evaluation": evaluation_contract(),
                },
            )
            counts["failed"] += 1
        print(json.dumps({"case_id": case["case_id"], **counts}), flush=True)

    uses_batch_transport = args.target_transport == "openai_batch" or (
        args.method == "pcsa_phase2"
        and args.pcsa_evaluator_transport == "openai_batch"
    )
    case_concurrency = (
        args.batch_case_concurrency
        if uses_batch_transport
        else args.sync_case_concurrency
    )
    semaphore = asyncio.Semaphore(case_concurrency)

    async def process_with_limit(case: dict[str, Any]) -> None:
        async with semaphore:
            await process_case(case)

    await asyncio.gather(*(process_with_limit(case) for case in selected))
    return counts


def checkpoint_state(
    output_dir: Path, selected: list[dict[str, Any]]
) -> dict[str, Any]:
    """Summarize durable case artifacts across all attempts of a resumed run."""
    completed: list[str] = []
    failed: list[str] = []
    pending: list[str] = []
    for case in selected:
        case_id = case["case_id"]
        if (output_dir / f"{case_id}.json").exists():
            completed.append(case_id)
        elif (output_dir / f"{case_id}.failed.json").exists():
            failed.append(case_id)
        else:
            pending.append(case_id)
    return {
        "selected": len(selected),
        "completed": len(completed),
        "failed": len(failed),
        "pending": len(pending),
        "failed_case_ids": failed,
        "pending_case_ids": pending,
        "is_complete": len(completed) == len(selected),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=METHODS, required=True)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--cohort-index", type=Path, default=DEFAULT_COHORT_INDEX)
    parser.add_argument("--persona-map", type=Path, default=DEFAULT_PERSONA_MAP)
    parser.add_argument("--persona-pool", type=Path, default=DEFAULT_PERSONA_POOL)
    parser.add_argument("--pathology-routes", type=Path, default=DEFAULT_PATHOLOGY_ROUTES)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--stop", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--crisis-label", action="append", default=[])
    parser.add_argument("--seed", type=int)
    parser.add_argument(
        "--max-turns",
        type=int,
        help="attack turn cap (default: 4 for PCSA Phase 2, 10 otherwise)",
    )
    parser.add_argument("--max-backtracks", type=int, default=10)
    parser.add_argument("--pair-streams", type=int, default=3)
    parser.add_argument("--tree-width", type=int, default=3)
    parser.add_argument("--branching-factor", type=int, default=2)
    parser.add_argument("--many-shot-examples", type=int, default=16)
    parser.add_argument("--target-endpoint", default=DEFAULT_TARGET_ENDPOINT)
    parser.add_argument("--target-model", default=DEFAULT_TARGET_MODEL)
    parser.add_argument("--target-api-key-env", default="TARGET_API_KEY")
    parser.add_argument(
        "--target-transport", choices=("sync", "openai_batch"), default="sync"
    )
    parser.add_argument("--target-temperature", type=float, default=0.0)
    parser.add_argument(
        "--target-reasoning-effort",
        choices=("none", "low", "medium", "high", "xhigh", "max"),
        help="optional Chat Completions reasoning_effort for the target model",
    )
    parser.add_argument("--target-max-completion-tokens", type=int, default=4096)
    parser.add_argument("--sync-case-concurrency", type=int, default=1)
    parser.add_argument("--batch-case-concurrency", type=int, default=64)
    parser.add_argument("--batch-poll-seconds", type=float, default=60.0)
    parser.add_argument("--batch-flush-seconds", type=float, default=1.0)
    parser.add_argument("--batch-request-retries", type=int, default=2)
    parser.add_argument("--batch-api-retries", type=int, default=4)
    parser.add_argument("--batch-retry-backoff-seconds", type=float, default=5.0)
    parser.add_argument("--adversary-endpoint", default=DEFAULT_ADVERSARY_ENDPOINT)
    parser.add_argument("--adversary-model", default=DEFAULT_ADVERSARY_MODEL)
    parser.add_argument("--adversary-api-key-env", default="ADVERSARY_API_KEY")
    parser.add_argument("--adversary-temperature", type=float, default=0.7)
    parser.add_argument("--adversary-max-completion-tokens", type=int, default=4096)
    parser.add_argument("--pcsa-candidates", type=int, default=PCSA_DEFAULT_CANDIDATES)
    parser.add_argument(
        "--pcsa-evaluator-endpoint", default="https://api.openai.com/v1"
    )
    parser.add_argument("--pcsa-evaluator-model", default="gpt-4o-mini")
    parser.add_argument("--pcsa-evaluator-api-key-env", default="OPENAI_API_KEY")
    parser.add_argument("--pcsa-evaluator-max-completion-tokens", type=int, default=512)
    parser.add_argument(
        "--pcsa-evaluator-transport",
        choices=("sync", "openai_batch"),
        default="openai_batch",
    )
    parser.add_argument(
        "--retry-failed",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="retry existing failed case checkpoints (default: enabled)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.max_turns is None:
        args.max_turns = PCSA_MAX_TURNS if args.method == "pcsa_phase2" else 10
    for name in (
        "start",
        "max_turns",
        "pair_streams",
        "tree_width",
        "branching_factor",
        "many_shot_examples",
        "sync_case_concurrency",
        "batch_case_concurrency",
        "target_max_completion_tokens",
        "adversary_max_completion_tokens",
        "pcsa_evaluator_max_completion_tokens",
        "pcsa_candidates",
    ):
        if getattr(args, name) < (0 if name == "start" else 1):
            parser.error(f"--{name.replace('_', '-')} has an invalid value")
    if args.batch_poll_seconds < 0:
        parser.error("--batch-poll-seconds must be non-negative")
    if args.batch_flush_seconds < 0:
        parser.error("--batch-flush-seconds must be non-negative")
    if args.batch_request_retries < 0:
        parser.error("--batch-request-retries must be non-negative")
    if args.batch_api_retries < 0:
        parser.error("--batch-api-retries must be non-negative")
    if args.batch_retry_backoff_seconds < 0:
        parser.error("--batch-retry-backoff-seconds must be non-negative")
    if args.stop is not None and args.stop < args.start:
        parser.error("--stop must be greater than or equal to --start")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.max_backtracks < 0:
        parser.error("--max-backtracks cannot be negative")
    if args.pcsa_candidates > len(PCSA_STRATEGY_NAMES):
        parser.error(
            f"--pcsa-candidates cannot exceed {len(PCSA_STRATEGY_NAMES)}"
        )
    if (
        urlparse(args.target_endpoint).hostname == "api.openai.com"
        and args.target_transport != "openai_batch"
    ):
        parser.error("official OpenAI targets must use --target-transport openai_batch")
    if (
        args.method == "pcsa_phase2"
        and urlparse(args.pcsa_evaluator_endpoint).hostname == "api.openai.com"
        and args.pcsa_evaluator_transport != "openai_batch"
    ):
        parser.error(
            "the official OpenAI PCSA evaluator must use "
            "--pcsa-evaluator-transport openai_batch"
        )
    if args.method == "pcsa_phase2" and args.max_turns > PCSA_MAX_TURNS:
        parser.error(f"PCSA Phase 2 is capped at {PCSA_MAX_TURNS} turns")
    if not CRISIS_PROMPT.exists() or not THERAPIST_PROMPT.exists():
        parser.error("PyRIT submodule is missing; run: git submodule update --init --recursive")
    if args.output_dir is None:
        args.output_dir = BASELINE_DIR / "outputs" / args.method
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    persona_contexts = load_persona_contexts(args.persona_map, args.persona_pool)
    pathology_contexts = load_pathology_contexts(args.pathology_routes)
    source_records = _read_records(args.input)
    cohort_rows = load_cohort_rows(args.cohort_index)
    cases = normalize_cases(
        project_official_records(source_records, cohort_rows),
        persona_contexts=persona_contexts,
        pathology_contexts=pathology_contexts,
    )
    if _is_canonical_full_run(args) and len(source_records) != EXPECTED_SOURCE_CASE_COUNT:
        raise ValueError(
            f"canonical baseline source must contain {EXPECTED_SOURCE_CASE_COUNT} cases; "
            f"found {len(source_records)}"
        )
    if _is_canonical_full_run(args) and len(cases) != EXPECTED_FULL_CASE_COUNT:
        raise ValueError(
            f"official baseline cohort must contain {EXPECTED_FULL_CASE_COUNT} cases; "
            f"found {len(cases)}"
        )
    if _is_canonical_full_run(args):
        missing_personas = [case["case_id"] for case in cases if case["persona_context"] is None]
        if missing_personas:
            raise ValueError(
                "canonical baseline run requires a fixed Phase 2 persona for every case; "
                f"missing {len(missing_personas)} assignments"
            )
        missing_pathology = [
            case["case_id"] for case in cases if case["pathology_context"] is None
        ]
        if missing_pathology:
            raise ValueError(
                "canonical baseline run requires a pathology route for every case; "
                f"missing {len(missing_pathology)} routes"
            )
    selected = select_cases(
        cases,
        start=args.start,
        stop=args.stop,
        limit=args.limit,
        crisis_labels=tuple(args.crisis_label),
        seed=args.seed,
    )
    manifest = build_manifest(
        args,
        selected,
        available_count=len(cases),
        source_available_count=len(source_records),
    )
    if args.dry_run:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0
    args.output_dir.mkdir(parents=True, exist_ok=True)
    _atomic_json(args.output_dir / "run_manifest.json", manifest)
    counts = asyncio.run(_run(args, selected))
    checkpoints = checkpoint_state(args.output_dir, selected)
    summary = {**manifest, "last_attempt": counts, "checkpoints": checkpoints}
    _atomic_json(args.output_dir / "run_summary.json", summary)
    print(json.dumps({**counts, "checkpoints": checkpoints}))
    return 0 if checkpoints["is_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
