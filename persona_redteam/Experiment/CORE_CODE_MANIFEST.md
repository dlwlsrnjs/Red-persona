# 핵심 코드 snapshot manifest

`core_code/`는 논문 제출 시점의 감사·보존용 사본이다. 실행과 수정은 오른쪽 canonical source에서
한다.

| snapshot | canonical source | 역할 |
|---|---|---|
| 해당 없음 | `experiments/final197/` | 최종 197건의 고정 설정·병렬 생성·병합·두 키 GPT-4o-mini Batch 실행. 이 폴더 자체를 canonical 배포 단위로 사용 |
| `core_code/experiments/run_jmir_persona_batch_api.py` | `experiments/run_jmir_persona_batch_api.py` | 500개 생성, checkpoint, resume, arm 실행 |
| `core_code/experiments/qwen_target_persona_research_dialogue.py` | `experiments/qwen_target_persona_research_dialogue.py` | multi-turn 연구 대화와 네 final branch |
| `core_code/experiments/run_ours_harmful_requests_v3.py` | `experiments/run_ours_harmful_requests_v3.py` | strict harmful-request v3 직접응답 설정 잠금 실행기 |
| `core_code/experiments/goal_contract_v2.py` | `experiments/goal_contract_v2.py` | legacy/v2/v3 목표 계약 검증 |
| `core_code/experiments/run_history_bridge_prompt_pilot.py` | `experiments/run_history_bridge_prompt_pilot.py` | 동일 history의 final-readout 교체 |
| `core_code/experiments/evaluate_history_bridge_prompt_pilot.py` | `experiments/evaluate_history_bridge_prompt_pilot.py` | 고정 pilot subset의 paired recovery/CARES 평가 |
| `core_code/ablation/specs.py` | `ablation/specs.py` | 허용 ablation registry |
| `core_code/ablation/context.py` | `ablation/context.py` | arm별 target-visible context 구성 |
| `core_code/ablation/cares_jmir_rq/evaluate.py` | `ablation/cares_jmir_rq/evaluate.py` | RQ1–RQ3 결합, 평가, paired 집계 |
| `core_code/ablation/aggregate.py` | `ablation/aggregate.py` | McNemar와 공통 집계 |
| `core_code/experiments/evaluate_cares_jmir_official500.py` | `experiments/evaluate_cares_jmir_official500.py` | CARES/JMIR request와 parser |
| `core_code/experiments/evaluate_final_cares_pilot64.py` | `experiments/evaluate_final_cares_pilot64.py` | CARES Level-2·JMIR OURS Best-of-4 및 외부 baseline 순위 |
| `core_code/experiments/evaluate_persona_co_research.py` | `experiments/evaluate_persona_co_research.py` | recovery와 직접 공격 응답 분리 평가 |
| `core_code/experiments/evaluate_recovery_behavior_batch.py` | `experiments/evaluate_recovery_behavior_batch.py` | R3+ 회복·B4+ 직접응답을 OpenAI Batch로 평가 |
| `core_code/experiments/evaluate_harmbench_direct_response.py` | `experiments/evaluate_harmbench_direct_response.py` | 로컬 HarmBench 및 동일 분기 R3+/B4+/joint Best-of-4 집계 |
| `core_code/experiments/evaluate_target_model_pilot40.py` | `experiments/evaluate_target_model_pilot40.py` | 추가 target 40개 파일럿의 Batch-only CARES/JMIR 평가 |
| `core_code/experiments/export_ours_paper_results.py` | `experiments/export_ours_paper_results.py` | canonical OURS 계약과 논문용 결과표 재생성 |
| `core_code/experiments/run_ours_official500.py` | `experiments/run_ours_official500.py` | neutral+history-bridge OURS 설정 잠금 실행기 |
| `core_code/experiments/evaluate_goal_exposure_history_bridge_official500.py` | `experiments/evaluate_goal_exposure_history_bridge_official500.py` | neutral 대 oracle 고정 bridge Official-500 Batch 평가 |
| `core_code/pipeline/openai_batch.py` | `pipeline/openai_batch.py` | Batch API, 비용 ledger, resume |
| `core_code/pipeline/openai_chat.py` | `pipeline/openai_chat.py` | standard API tail, partial checkpoint |
| `core_code/pipeline/contracts.py` | `pipeline/contracts.py` | verified bridge·공유 history·attack schema 계약 검사 |
| `core_code/ablation/contracts.py` | `ablation/contracts.py` | ablation 산출물의 recovery/attack 분리 계약 검사 |

`prompts/`에는 CARES h-level, CARES A/C/R, JMIR evaluator, recovery evaluator, 영문 질문·공격
스타일 bank, 안전 연구 지침과 출처 metadata를 복사했다. 사본은 독립 package가 아니므로 import를
수정해 직접 실행하지 않는다.
