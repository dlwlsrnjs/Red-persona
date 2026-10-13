from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import random
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
PERSONA_DATA = (
    ROOT / "persona_redteam/our_method/data/"
    "FINAL197_PERSONAS_WITH_HISTORY_NO_VERBATIM_GOAL.json"
)
COMPACT_ROOT = (
    ROOT / "persona_redteam/result/OURS/"
    "final197_no_research_pair_gpt4o_v2/gpt4o"
)
DIRECT_FINAL_ROOT = (
    ROOT / "persona_redteam/result/OURS/"
    "final197_direct_final_only_gpt4o_v1/gpt4o"
)
SEVEN_STAGE_ROOT = (
    ROOT / "persona_redteam/result/OURS/"
    "final197_gpt4o_qwen_three_arm_v1/gpt4o"
)
PERSONA_POOL = ROOT / "data/personas/personas.jsonl"


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


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


def _score_map(history: str) -> dict[str, dict[str, Any]]:
    score_path = (
        ROOT / "persona_redteam/data/evaluations/"
        "final197_no_research_pair_gpt4o_v2/gpt4o" / history /
        "scoring/harmbench.json"
    )
    if not score_path.exists():
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
        self.compact = {
            key: _merged_map(COMPACT_ROOT / key / "merged")
            for key in ("with_history", "no_history")
        }
        self.direct_final = {
            key: _merged_map(DIRECT_FINAL_ROOT / key / "merged")
            for key in ("with_history", "no_history")
        }
        # The earlier complete seven-stage run calls the latent-history arm
        # `no_verbatim`; its actual no-history arm is named `no_history`.
        self.seven_stage = {
            "with_history": _merged_map(SEVEN_STAGE_ROOT / "no_verbatim" / "merged"),
            "no_history": _merged_map(SEVEN_STAGE_ROOT / "no_history" / "merged"),
        }
        self.scores = {
            key: _score_map(key) for key in ("with_history", "no_history")
        }

    def ids(self) -> list[str]:
        return sorted(self.base)

    def list_cases(
        self, *, outcome: str = "all", query: str = "", history_enabled: bool = True
    ) -> list[dict[str, Any]]:
        key = _history_key(history_enabled)
        needle = query.casefold().strip()
        rows: list[dict[str, Any]] = []
        for case_id in self.ids():
            artifact = self.compact[key].get(case_id, {})
            case = artifact.get("case", {})
            score = self.scores[key].get(case_id, {"status": "unscored"})
            row = {
                "case_id": case_id,
                "outcome": score["status"],
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
        self, *, outcome: str = "all", history_enabled: bool = True
    ) -> dict[str, Any]:
        rows = self.list_cases(outcome=outcome, history_enabled=history_enabled)
        if not rows:
            raise KeyError(f"no cases match outcome={outcome}")
        return random.SystemRandom().choice(rows)

    def _artifact(self, case_id: str, history_enabled: bool) -> dict[str, Any]:
        key = _history_key(history_enabled)
        artifact = self.compact[key].get(case_id)
        if not artifact:
            raise KeyError(case_id)
        return artifact

    def get_case(self, case_id: str, *, history_enabled: bool = True) -> dict[str, Any]:
        artifact = self._artifact(case_id, history_enabled)
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
            "historical_score": self.scores[_history_key(history_enabled)].get(
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
        self, case_id: str, protocol: str, history_enabled: bool
    ) -> dict[str, Any] | None:
        key = _history_key(history_enabled)
        mapping = {
            "red_persona_compact": self.compact,
            "red_persona_direct_final": self.direct_final,
            "red_persona_seven_stage": self.seven_stage,
        }.get(protocol)
        return mapping[key].get(case_id) if mapping else None

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
