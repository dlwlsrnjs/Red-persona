# 외부 베이스라인 핵심 코드 snapshot

| snapshot | canonical source | 역할 |
|---|---|---|
| `core_code/prepare_final197_assets.py` | `../prepare_final197_assets.py` | 최종 197개 실행 자산과 43+154 분할 생성 |
| `core_code/prepare_baseline_personas.py` | `../prepare_baseline_personas.py` | 고정 persona 보존과 나머지 사례의 중복 없는 결정적 배정 |
| `core_code/seed_final197_checkpoints.py` | `../seed_final197_checkpoints.py` | 검증된 기존 응답·대화 체크포인트 재사용 |
| `core_code/run_final197_remaining154.sbatch` | `../run_final197_remaining154.sbatch` | 미완료 15개 target×method 셀 실행 |
| `core_code/prepare_final_matrix.py` | `../../official_evaluation/prepare_final_matrix.py` | 결과를 공통 평가 스키마로 변환 (`--row-prefix final197`) |
| `core_code/prepare_final197_eval_reuse.py` | `../../official_evaluation/prepare_final197_eval_reuse.py` | 기존 43개 평가 투영 및 154개 평가 입력 분리 |
| `core_code/run_final197_eval.sbatch` | `../../official_evaluation/run_final197_eval.sbatch` | HarmBench·R/B·Strict Joint ASR 자동 평가 |
| `core_code/evaluate_cares.py` | `../../official_evaluation/evaluate_cares.py` | PCSA식 CARES A/C/R Batch 평가 |
| `core_code/evaluate_pcsa_gpt4o_judge.py` | `../../official_evaluation/evaluate_pcsa_gpt4o_judge.py` | PCSA Figure-4 GPT-4o Batch 평가 |
| `core_code/evaluate_b3_behavior.py` | `../../official_evaluation/evaluate_b3_behavior.py` | 수정 goal-compliance v3 Batch 평가 |
| `core_code/aggregate_final197.py` | `../../official_evaluation/aggregate_final197.py` | 본 표의 공식·보조 지표 분리 집계 |
| `core_code/audit_final197_evaluations.py` | `../../official_evaluation/audit_final197_evaluations.py` | 3,546행 coverage·인용·판정 검증 및 재시도 입력 생성 |
| `core_code/reprocess_pcsa_batches.py` | `../../official_evaluation/reprocess_pcsa_batches.py` | 저장된 PCSA Batch 출력의 점수 보존형 근거 호환성 재검증 |
| `core_code/reprocess_rb_batches.py` | `../../official_evaluation/reprocess_rb_batches.py` | 저장된 R/B 출력의 근거 교정과 명시적 보수 판정 |
| `core_code/merge_rejudged_results.py` | `../../official_evaluation/merge_rejudged_results.py` | 재판정 결과를 원 입력 순서대로 검증·병합 |
| `core_code/prompts/goal_compliance_evaluator_v3.txt` | `../../official_evaluation/prompts/goal_compliance_evaluator_v3.txt` | 거절 오판과 자동 하향을 수정한 외부 baseline 전용 rubric |
| `core_code/run_baseline_matrix.py` | `../run_baseline_matrix.py` | 방법×target 병렬 orchestration과 retry |
| `core_code/run_pyrit_baseline.py` | `../run_pyrit_baseline.py` | 외부 방법 공통 실행 adapter |
| `core_code/openai_batch_transport.py` | `../openai_batch_transport.py` | wave별 Batch 제출·resume·부분 실패 복구 |

사본은 독립 package가 아니다. 실행은 canonical source에서 한다.
