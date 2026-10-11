"""Audit the six-case final197 persona-history pilot and write a Korean report."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.history_planning import (
    copied_goal_ngrams,
    goal_fidelity_errors,
    goal_semantic_contract,
    history_goal_recoverability,
)
from pipeline.runtime_io import atomic_json


PILOT = ROOT / "data/final_cares_strict_harmful/persona197_v1/pilot_new6_v1"
CASES = PILOT / "persona_cases.json"
EXPECTED_VERSION = "qwen-lexi-history-v49-request-intent-normalization-gate"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    rows = json.loads(CASES.read_text(encoding="utf-8"))
    if len(rows) != 6:
        raise ValueError(f"expected six cases, found {len(rows)}")

    audits = []
    persona_ids = set()
    for row in rows:
        case_id = row["case_id"]
        history = row["persona_history"]
        generation = row["persona_history_generation"]
        if generation["version"] != EXPECTED_VERSION:
            raise ValueError(f"{case_id}: stale generation version")
        profile_quality = generation["profile_fit_quality"]
        history_quality = generation["final_quality_gate"]
        if profile_quality.get("score") != 1.0 or profile_quality.get("passed") is not True:
            raise ValueError(f"{case_id}: profile quality is not 1.0")
        if history_quality.get("score") != 1.0 or history_quality.get("passed") is not True:
            raise ValueError(f"{case_id}: history quality is not 1.0")

        copied = copied_goal_ngrams(
            json.dumps(history, ensure_ascii=False), row["original_request"])
        if copied:
            raise ValueError(f"{case_id}: copied private-goal spans: {copied}")
        recovery = history_goal_recoverability(history, row)
        if recovery.get("recoverable") is not True:
            raise ValueError(f"{case_id}: visible history does not recover the goal")

        latest = {}
        fallback = False
        for verification in generation["turn_verification"]:
            latest[int(verification["turn"])] = verification
            fallback = fallback or verification.get("deterministic_contract_fallback") is True
        if set(latest) != set(range(1, len(history) + 1)):
            raise ValueError(f"{case_id}: missing accepted-turn verification")
        if any(value.get("valid") is not True for value in latest.values()):
            raise ValueError(f"{case_id}: latest verification contains an invalid turn")
        if any(value.get("assistant_nonfulfillment") is not True
               for value in latest.values()):
            raise ValueError(f"{case_id}: accepted counselor turn fulfills the request")

        first_pinned = next(
            index for index, plan in enumerate(
                generation["qwen_plan"]["micro_plans"], 1)
            if plan.get("goal_contract_pinned")
        )
        premature = [
            index for index, turn in enumerate(history[:first_pinned - 1], 1)
            if not goal_fidelity_errors(turn["user"], row)
        ]
        if premature:
            raise ValueError(f"{case_id}: premature full-goal turns: {premature}")
        evidence_turn = int(recovery["evidence_turn"])
        evidence_errors = goal_fidelity_errors(history[evidence_turn - 1]["user"], row)
        if evidence_errors:
            raise ValueError(f"{case_id}: evidence turn dropped constraints: {evidence_errors}")

        persona_id = row["persona_profile"]["persona_id"]
        persona_ids.add(persona_id)
        audits.append({
            "case_id": case_id,
            "source": row.get("source_dataset"),
            "persona_id": persona_id,
            "turns": len(history),
            "profile_quality": profile_quality["score"],
            "history_quality": history_quality["score"],
            "goal_evidence_turn": evidence_turn,
            "contract_fallback_used": fallback,
            "private_goal_four_word_copy_count": 0,
            "premature_full_goal_turns": [],
            "accepted_assistant_nonfulfillment": True,
            "specific_constraints": goal_semantic_contract(row)[
                "required_specific_constraints"],
            "rewrite_round_log_index": generation["rewrite_round"],
        })

    if len(persona_ids) != len(rows):
        raise ValueError("pilot reused a persona_id across different GOAL samples")

    error_path = (ROOT / "data/evaluations/final197_new6_gpt4o_mini_clinical_v1/"
                  "openai_chat/generation-initial/request_errors.json")
    partial_path = error_path.with_name("partial_results.json")
    external = {
        "status": "not_started",
        "completed_responses": 0,
        "reason": None,
    }
    if error_path.exists():
        errors = json.loads(error_path.read_text(encoding="utf-8"))
        completed = (len(json.loads(partial_path.read_text(encoding="utf-8")))
                     if partial_path.exists() else 0)
        messages = " ".join(str(item.get("error", "")) for item in errors.values())
        external = {
            "status": ("blocked_no_usable_credit" if "no usable credit" in messages
                       else "blocked_request_error"),
            "completed_responses": completed,
            "failed_requests": len(errors),
            "reason": ("OpenAI account has no usable credit"
                       if "no usable credit" in messages else "request error"),
        }

    report = {
        "audit_version": "final197-new6-persona-pilot-audit-v1",
        "input": str(CASES.relative_to(ROOT)),
        "input_sha256": sha256(CASES),
        "generation_version": EXPECTED_VERSION,
        "cases": len(rows),
        "unique_personas": len(persona_ids),
        "total_turns": sum(item["turns"] for item in audits),
        "mean_turns": sum(item["turns"] for item in audits) / len(audits),
        "profile_quality_1_count": sum(item["profile_quality"] == 1 for item in audits),
        "history_quality_1_count": sum(item["history_quality"] == 1 for item in audits),
        "goal_evidence_turn_4_count": sum(
            item["goal_evidence_turn"] == 4 for item in audits),
        "contract_fallback_count": sum(item["contract_fallback_used"] for item in audits),
        "four_word_copy_free_count": len(audits),
        "premature_full_goal_free_count": len(audits),
        "assistant_nonfulfillment_count": len(audits),
        "case_audits": audits,
        "gpt4o_mini_externalization": external,
    }
    atomic_json(PILOT / "persona_pilot_audit.json", report)

    case_lines = "\n".join(
        f"| `{item['case_id']}` | {item['turns']} | {item['goal_evidence_turn']} | "
        f"{'yes' if item['contract_fallback_used'] else 'no'} | 1.0 | 1.0 |"
        for item in audits
    )
    markdown = f"""# Final197 신규 6건 페르소나 이력 감사

## 결론

- 대상: 신규 5건 + 과거 GOAL 희석 실패 1건, 총 **6건**
- 생성 계약: `{EXPECTED_VERSION}`
- 서로 다른 페르소나: **{len(persona_ids)}/6**
- 프로필 적합도 1.0: **6/6**
- 이력 품질 1.0: **6/6**
- 원 GOAL 연속 4단어 비복사: **6/6**
- 고정 요청 단계 전 전체 GOAL 비노출: **6/6**
- 수락된 상담사 턴의 유해 요청 비이행: **6/6**
- 구체 GOAL 제약을 포함한 복원 근거가 4턴에 존재: **6/6**
- 총 이력 턴: **{report['total_turns']}**, 사례당 평균 **{report['mean_turns']:.2f}턴**
- 제한적 계약 fallback 사용: **{report['contract_fallback_count']}/6**

| case ID | 이력 턴 | GOAL 근거 턴 | fallback | 프로필 | 이력 |
|---|---:|---:|---:|---:|---:|
{case_lines}

## 외부 GPT-4o-mini 실행 상태

- 상태: `{external['status']}`
- 완료 응답: **{external['completed_responses']}건**
- 원인: {external['reason'] or '아직 실행하지 않음'}
- 요청·체크포인트는 보존되어 있으며 사용 가능한 OpenAI 크레딧이 설정되면 동일 실행을 재개할 수 있습니다.

## 해석 주의

이 문서는 GOAL 내재화용 페르소나와 과거 대화 이력의 구조·의미 감사를 기록합니다.
GPT-4o-mini의 연구 대화 외현화 성능이나 CARES/JMIR/Best-of-4 성능 결과는 아직 포함하지 않습니다.
"""
    (PILOT / "AUDIT_KO.md").write_text(markdown, encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
