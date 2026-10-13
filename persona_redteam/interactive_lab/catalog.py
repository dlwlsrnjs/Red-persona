from __future__ import annotations

from functools import lru_cache
import json
import os
from pathlib import Path
import random
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
PERSONA_DATA = (
    ROOT / "persona_redteam/our_method/data/"
    "FINAL197_PERSONAS_WITH_HISTORY_NO_VERBATIM_GOAL.json"
)
PERSONA_POOL = ROOT / "data/personas/personas.jsonl"

RESULT_ROOTS = tuple(dict.fromkeys(Path(value).expanduser() for value in (
    os.environ.get("RED_PERSONA_RESULTS_ROOT", ""),
    str(ROOT / "persona_redteam/result/OURS"),
    "/home/ljk98/mental-jail/Red-persona-final/persona_redteam/result/OURS",
    "/data1/users/ljk98/runtime_cache/persona_redteam_final197/results",
) if value))
EVALUATION_ROOTS = tuple(dict.fromkeys(Path(value).expanduser() for value in (
    os.environ.get("RED_PERSONA_EVALUATIONS_ROOT", ""),
    str(ROOT / "persona_redteam/data/evaluations"),
    "/home/ljk98/mental-jail/Red-persona-final/persona_redteam/data/evaluations",
) if value))


# These are experiment contracts, not copies of the experiment data.  Every
# relative path is resolved against the existing repository/runtime roots.
RUN_SPECS: dict[str, dict[str, Any]] = {
    "compact_gpt4o": {
        "label": "Compact · GPT-4o", "protocol": "red_persona_compact",
        "target_model": "gpt-4o",
        "artifacts": {
            "with_history": "final197_no_research_pair_gpt4o_v2/gpt4o/with_history/merged",
            "no_history": "final197_no_research_pair_gpt4o_v2/gpt4o/no_history/merged",
        },
        "scores": {
            "with_history": "final197_no_research_pair_gpt4o_v2/gpt4o/with_history/scoring/harmbench.json",
            "no_history": "final197_no_research_pair_gpt4o_v2/gpt4o/no_history/scoring/harmbench.json",
        },
    },
    "compact_qwen2_5_7b": {
        "label": "Compact · Qwen2.5-7B", "protocol": "red_persona_compact",
        "target_model": "Qwen2.5-7B-Instruct",
        "artifacts": {
            "with_history": "final197_single_readout_qwen_v2/qwen2_5_7b/with_history/merged",
            "no_history": "final197_single_readout_qwen_v2/qwen2_5_7b/no_history/merged",
        },
        "scores": {
            "with_history": "final197_single_readout_qwen_v2/qwen2_5_7b/with_history/scoring/harmbench.json",
            "no_history": "final197_single_readout_qwen_v2/qwen2_5_7b/no_history/scoring/harmbench.json",
        },
    },
    "direct_final_gpt4o": {
        "label": "Direct-final-only · GPT-4o", "protocol": "red_persona_direct_final",
        "target_model": "gpt-4o",
        "artifacts": {
            "with_history": "final197_direct_final_only_gpt4o_v1/gpt4o/with_history/merged",
            "no_history": "final197_direct_final_only_gpt4o_v1/gpt4o/no_history/merged",
        },
        "scores": {
            "with_history": "final197_direct_final_only_gpt4o_v1/gpt4o/with_history/scoring/harmbench.json",
            "no_history": "final197_direct_final_only_gpt4o_v1/gpt4o/no_history/scoring/harmbench.json",
        },
    },
    "direct_final_qwen2_5_7b": {
        "label": "Direct-final-only · Qwen2.5-7B", "protocol": "red_persona_direct_final",
        "target_model": "Qwen2.5-7B-Instruct",
        "artifacts": {
            "with_history": "final197_direct_final_only_qwen_v1/qwen2_5_7b/with_history/merged",
            "no_history": "final197_direct_final_only_qwen_v1/qwen2_5_7b/no_history/merged",
        },
    },
    "seven_stage_gpt4o": {
        "label": "Seven-stage · GPT-4o", "protocol": "red_persona_seven_stage",
        "target_model": "gpt-4o",
        "artifacts": {
            "with_history": "final197_gpt4o_qwen_three_arm_v1/gpt4o/no_verbatim/merged",
            "no_history": "final197_gpt4o_qwen_three_arm_v1/gpt4o/no_history/merged",
        },
        "scores": {
            "with_history": "final197_gpt4o_qwen_three_arm_v1/gpt4o/no_verbatim/scoring/harmbench.json",
            "no_history": "final197_gpt4o_qwen_three_arm_v1/gpt4o/no_history/scoring/harmbench.json",
        },
    },
    "seven_stage_qwen2_5_7b": {
        "label": "Seven-stage · Qwen2.5-7B", "protocol": "red_persona_seven_stage",
        "target_model": "Qwen2.5-7B-Instruct",
        "artifacts": {
            "with_history": "final197_gpt4o_qwen_three_arm_v1/qwen2_5_7b/no_verbatim/merged",
            "no_history": "final197_gpt4o_qwen_three_arm_v1/qwen2_5_7b/no_history/merged",
        },
        "scores": {
            "with_history": "final197_gpt4o_qwen_three_arm_v1/qwen2_5_7b/no_verbatim/scoring/harmbench.json",
            "no_history": "final197_gpt4o_qwen_three_arm_v1/qwen2_5_7b/no_history/scoring/harmbench.json",
        },
    },
}

for model_id, label in {
    "mistral_small_3_2_24b": "Mistral Small 3.2 24B",
    "gemma4_26b_a4b_it": "Gemma 4 26B-A4B",
    "phi4": "Phi-4",
    "llama3_1_8b_instruct": "Llama 3.1 8B Instruct",
    "llama3_g2c": "Llama3-G2C",
    "gpt5_4_mini": "GPT-5.4-mini",
    "gpt6_luna": "GPT-6-luna",
}.items():
    RUN_SPECS[f"compact_{model_id}"] = {
        "label": f"Compact · {label}",
        "protocol": "red_persona_compact",
        "target_model": label,
        "artifacts": {
            "with_history": f"final197_best_short_cross_model_v1/{model_id}/cases_0_197/merged",
        },
        "scores": {
            "with_history": f"final197_best_short_cross_model_v1/{model_id}/cases_0_197/scoring/harmbench.json",
        },
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_existing(relative: str, roots: tuple[Path, ...]) -> Path | None:
    for root in roots:
        candidate = root / relative
        if candidate.exists():
            return candidate.resolve()
    return None


def _case_files(directory: Path) -> Iterable[Path]:
    if not directory.exists():
        return []
    return (
        path for path in sorted(directory.glob("*.json"))
        if path.name != "run_summary.json"
    )


def _merged_map(directory: Path) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for path in _case_files(directory):
        try:
            value = _read_json(path)
            case_id = str(value.get("case", {}).get("case_id") or path.stem)
            if value.get("results"):
                rows[case_id] = value
        except (OSError, ValueError, TypeError):
            continue
    return rows


def _score_map(score_path: Path | None) -> dict[str, dict[str, Any]]:
    if score_path is None or not score_path.exists():
        return {}
    value = _read_json(score_path)
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in value.get("rows", []):
        grouped.setdefault(str(row.get("case_id")), []).append(row)
    result: dict[str, dict[str, Any]] = {}
    for case_id, rows in grouped.items():
        result[case_id] = {
            "status": "success" if any(row.get("joint_success") for row in rows) else "failure",
            "strict_joint": any(row.get("joint_success") for row in rows),
            "r3_plus": any(row.get("recovery_success") for row in rows),
            "b4_plus": any(row.get("commitment_success") for row in rows),
            "harmbench_positive": any(row.get("harmbench_positive") for row in rows),
            "branches": [
                {
                    "direction": row.get("direction"),
                    "R": row.get("recovery_level"),
                    "B": row.get("response_behavior_level"),
                    "harmbench_positive": bool(row.get("harmbench_positive")),
                    "joint_success": bool(row.get("joint_success")),
                    "cares_label": row.get("cares_label"),
                }
                for row in rows
            ],
        }
    return result


def _history_key(enabled: bool) -> str:
    return "with_history" if enabled else "no_history"


class Catalog:
    """Index local experiment artifacts without changing them."""

    def __init__(self) -> None:
        base_rows = _read_json(PERSONA_DATA)
        self.base = {str(row["case_id"]): row for row in base_rows}
        self.runs: dict[str, dict[str, Any]] = {}
        for run_id, spec in RUN_SPECS.items():
            artifacts: dict[str, dict[str, dict[str, Any]]] = {}
            scores: dict[str, dict[str, dict[str, Any]]] = {}
            locations: dict[str, str] = {}
            for history, relative in spec.get("artifacts", {}).items():
                path = _resolve_existing(relative, RESULT_ROOTS)
                if path is not None:
                    artifacts[history] = _merged_map(path)
                    locations[f"artifacts:{history}"] = str(path)
            for history, relative in spec.get("scores", {}).items():
                path = _resolve_existing(relative, EVALUATION_ROOTS)
                if path is not None:
                    scores[history] = _score_map(path)
                    locations[f"scores:{history}"] = str(path)
            if artifacts:
                self.runs[run_id] = {
                    **spec,
                    "artifacts_by_history": artifacts,
                    "scores_by_history": scores,
                    "locations": locations,
                }

        # Backward-compatible aliases used by the protocol state machine and
        # existing tests. The dashboard itself can select any discovered run.
        self.compact = self._run_artifacts("compact_gpt4o")
        self.direct_final = self._run_artifacts("direct_final_gpt4o")
        self.seven_stage = self._run_artifacts("seven_stage_gpt4o")
        self.scores = self._run_scores("compact_gpt4o")

    def _run_artifacts(self, run_id: str) -> dict[str, dict[str, dict[str, Any]]]:
        run = self.runs.get(run_id, {})
        values = run.get("artifacts_by_history", {})
        return {key: values.get(key, {}) for key in ("with_history", "no_history")}

    def _run_scores(self, run_id: str) -> dict[str, dict[str, dict[str, Any]]]:
        run = self.runs.get(run_id, {})
        values = run.get("scores_by_history", {})
        return {key: values.get(key, {}) for key in ("with_history", "no_history")}

    def public_runs(self) -> dict[str, dict[str, Any]]:
        return {
            run_id: {
                "label": run["label"],
                "protocol": run["protocol"],
                "target_model": run["target_model"],
                "history_modes": sorted(run["artifacts_by_history"]),
                "artifact_counts": {
                    history: len(rows)
                    for history, rows in run["artifacts_by_history"].items()
                },
                "score_counts": {
                    history: len(rows)
                    for history, rows in run["scores_by_history"].items()
                },
                "locations": run["locations"],
            }
            for run_id, run in self.runs.items()
        }

    def default_run(self, protocol: str, history_enabled: bool = True) -> str | None:
        history = _history_key(history_enabled)
        preferred = {
            "red_persona_compact": "compact_gpt4o",
            "red_persona_direct_final": "direct_final_gpt4o",
            "red_persona_seven_stage": "seven_stage_gpt4o",
        }.get(protocol)
        if preferred in self.runs and history in self.runs[preferred]["artifacts_by_history"]:
            return preferred
        return next((
            run_id for run_id, run in self.runs.items()
            if run["protocol"] == protocol and history in run["artifacts_by_history"]
        ), None)

    def _resolve_run(
        self, run_id: str | None, protocol: str, history_enabled: bool
    ) -> tuple[str | None, dict[str, Any] | None]:
        selected = run_id or self.default_run(protocol, history_enabled)
        if selected is None:
            return None, None
        run = self.runs.get(selected)
        if run is None:
            raise KeyError(f"unknown historical run: {selected}")
        if run["protocol"] != protocol:
            raise ValueError(
                f"historical run {selected} belongs to {run['protocol']}, not {protocol}"
            )
        return selected, run

    def ids(self) -> list[str]:
        return sorted(self.base)

    def list_cases(
        self, *, outcome: str = "all", query: str = "", history_enabled: bool = True,
        run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        key = _history_key(history_enabled)
        selected, run = self._resolve_run(
            run_id, "red_persona_compact", history_enabled
        )
        artifacts = run.get("artifacts_by_history", {}).get(key, {}) if run else {}
        scores = run.get("scores_by_history", {}).get(key, {}) if run else {}
        needle = query.casefold().strip()
        rows: list[dict[str, Any]] = []
        for case_id in self.ids():
            artifact = artifacts.get(case_id, {})
            case = artifact.get("case", {})
            score = scores.get(case_id, {"status": "unscored"})
            row = {
                "case_id": case_id,
                "outcome": score["status"],
                "historical_run": selected,
                "crisis_label": case.get("crisis_label") or self.base[case_id].get("crisis_label"),
                "source_dataset": self.base[case_id].get("source_dataset"),
                "persona_id": self.base[case_id].get("persona_id"),
                "goal_preview": str(case.get("original_request", ""))[:180],
            }
            if outcome != "all" and row["outcome"] != outcome:
                continue
            searchable = " ".join(map(str, row.values())).casefold()
            if needle and needle not in searchable:
                continue
            rows.append(row)
        return rows

    def random_case(
        self, *, outcome: str = "all", history_enabled: bool = True,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        rows = self.list_cases(
            outcome=outcome, history_enabled=history_enabled, run_id=run_id
        )
        if not rows:
            raise KeyError(f"no cases match outcome={outcome}")
        return random.SystemRandom().choice(rows)

    def _artifact(
        self, case_id: str, history_enabled: bool, run_id: str | None = None
    ) -> tuple[str, dict[str, Any], dict[str, Any]]:
        key = _history_key(history_enabled)
        selected, run = self._resolve_run(
            run_id, "red_persona_compact", history_enabled
        )
        if selected is None or run is None:
            raise KeyError("no compact historical run is available")
        artifact = run.get("artifacts_by_history", {}).get(key, {}).get(case_id)
        if not artifact:
            raise KeyError(case_id)
        return selected, run, artifact

    def get_case(
        self, case_id: str, *, history_enabled: bool = True,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        selected, run, artifact = self._artifact(case_id, history_enabled, run_id)
        case = artifact["case"]
        result = artifact["results"][0]
        generation = case.get("persona_history_generation", {})
        attempts = generation.get("profile_candidate_attempts", [])
        top_k = generation.get("retrieval_top_k", [])
        candidates = []
        for rank, item in enumerate(top_k, 1):
            profile = item.get("profile", item) if isinstance(item, dict) else {}
            candidates.append({
                "rank": rank,
                "persona_id": profile.get("id") or profile.get("persona_id"),
                "background": profile.get("background"),
                "concerns": profile.get("concerns"),
                "communication_style": profile.get("communication_style"),
                "retrieval_metadata": {
                    key: value for key, value in item.items() if key != "profile"
                } if isinstance(item, dict) else {},
            })
        branches = result.get("final_branches", [])
        return {
            "case_id": case_id,
            "historical_run": selected,
            "historical_run_label": run["label"],
            "historical_target_model": run["target_model"],
            "goal": case.get("original_request") or result.get("private_goal"),
            "crisis_label": case.get("crisis_label"),
            "source_dataset": self.base[case_id].get("source_dataset"),
            "harm_level": self.base[case_id].get("harm_level"),
            "persona_id": self.base[case_id].get("persona_id"),
            "persona": case.get("persona") or self.base[case_id].get("persona"),
            "persona_profile": case.get("persona_profile", {}),
            "persona_history": case.get("persona_history") or self.base[case_id].get("persona_history", []),
            "persona_selection": {
                "selected": generation.get("profile_selection", {}),
                "fit_quality": generation.get("profile_fit_quality", {}),
                "attempts": attempts,
                "retrieval_top_k": candidates,
            },
            "question_pool": case.get("similar_goal_question_pool", {}),
            "historical_score": run.get("scores_by_history", {}).get(
                _history_key(history_enabled), {}
            ).get(
                case_id, {"status": "unscored"}
            ),
            "branches": [
                {
                    "index": index,
                    "direction": branch.get("direction"),
                    "attack_style": branch.get("attack_style"),
                    "recovery_question": branch.get("recovery_question"),
                    "recovery_question_audit": branch.get("recovery_question_audit", {}),
                    "anchor": branch.get("final_anchor_record") or branch.get("bridge_record", {}),
                    "historical_recovery_response": branch.get("recovery_response", {}).get("text", ""),
                    "attack_question": branch.get("attack_question", ""),
                    "historical_attack_response": branch.get("attack_response", {}).get("text", ""),
                }
                for index, branch in enumerate(branches)
            ],
            "available_protocols": {
                "red_persona_compact": case_id in self.compact[_history_key(history_enabled)],
                "red_persona_direct_final": case_id in self.direct_final[_history_key(history_enabled)],
                "red_persona_seven_stage": case_id in self.seven_stage[_history_key(history_enabled)],
                "direct_baseline": True,
                "pcsa_phase2": True,
            },
        }

    def artifact_for_protocol(
        self, case_id: str, protocol: str, history_enabled: bool,
        run_id: str | None = None,
    ) -> dict[str, Any] | None:
        key = _history_key(history_enabled)
        _, run = self._resolve_run(run_id, protocol, history_enabled)
        if run is None:
            return None
        return run.get("artifacts_by_history", {}).get(key, {}).get(case_id)

    @lru_cache(maxsize=64)
    def search_persona_pool(self, query: str, limit: int = 25) -> tuple[dict[str, Any], ...]:
        needle = query.casefold().strip()
        rows: list[dict[str, Any]] = []
        if not PERSONA_POOL.exists():
            return tuple()
        with PERSONA_POOL.open(encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    value = json.loads(line)
                except ValueError:
                    continue
                text = json.dumps(value, ensure_ascii=False).casefold()
                if needle and needle not in text:
                    continue
                rows.append({
                    "persona_id": value.get("id") or value.get("persona_id"),
                    "background": value.get("background"),
                    "concerns": value.get("concerns"),
                    "communication_style": value.get("communication_style"),
                    "source": value.get("source") or value.get("provenance"),
                })
                if len(rows) >= max(1, min(limit, 100)):
                    break
        return tuple(rows)
