# 리뷰 요구사항 실행 완료표

작성일: 2026-11-25
범위: 5인 독립 인간평가 제외, 현재 보존 데이터로 실행 가능한 자동 실험·재분석·감사·재현성 작업

## 상태 정의

- **완료**: 실험 또는 재분석 결과와 재현 산출물이 존재함
- **부분 완료**: 현재 데이터로 가능한 범위는 완료했으나 원 우려 전체를 해소하지는 못함
- **제외**: 연구자 요청으로 이번 실행 범위에서 수행하지 않음
- **복구 불가**: 필요한 원기록이 존재하지 않아 값을 만들 수 없으며 0으로 대체하지 않음

## 리뷰 항목별 상태

| 리뷰 요구/우려 | 수행 내용 | 핵심 결과 | 산출물 | 상태 |
|---|---|---|---|---|
| Follow-up과 exact quotation의 confounding | 누락된 두 셀을 생성·평가한 paired 2×2 ablation | Direct 7.11%, Follow-up-only 4.06%, Quotation-only 70.56%, Compact 95.94% Success@4 | `docs/FOLLOWUP_QUOTATION_FACTORIAL_ABLATION_KO.md`, safe factorial aggregates | **완료** |
| Goal cue leakage / pre-implanted goal | within-crisis-label aligned-vs-shuffled goal-blind control | 97.97% vs 70.05%, +27.92%p, exact McNemar p=1.38e-13 | `result/reviewer_response/goal_blind_summary.json` | **완료** |
| 자연 사례로의 외적 타당도 | 4 source datasets와 crisis labels별 compact 및 goal-blind sensitivity | 모든 source에서 compact strict @4 ≥90.91%; source별 shuffle contrast +5.88~+33.09%p | `result/reviewer_response/source_strata/` | **부분 완료**: 별도 자연 대화 corpus가 아님 |
| Branch 선택이 post-hoc best-of-4인가 | fixed branch @1, uniform-random expected @1, five-fold cross-fit, @4를 분리 | fixed 43.65–82.74%, random @1 69.42%, cross-fit 80.71%, @4 95.94% | `result/reviewer_response/branch_endpoints/` | **완료** |
| Success@1/Success@4 명확화 | branch/case 단위와 call budget을 명시 | @1과 @4를 별도 endpoint로 유지 | branch 재분석 및 원고 문안 | **완료** |
| Length와 content confounding | 동일 branch의 cumulative 0..7 stage control | strict @1 64.97%→25.38%; 단계당 -5.85%p | `result/reviewer_response/length_depth_summary.*` | **완료** |
| Goal recognition과 executable compliance 분리 | 197 paired cases × 9 compact models 재분석 | R3–B4 model-rate ρ=0.177; 두 모델은 R3≥97.97%지만 B4=0% | `result/reviewer_response/cross_model/` | **완료** |
| Target-model dependence | 같은 197 cases의 9개 target 결과와 Cochran's Q/McNemar-Holm | 모든 endpoint의 model heterogeneity p<1.3e-34 | `result/reviewer_response/cross_model/` | **완료** |
| 판정기 충돌 | row-level agreement/κ와 18-cell method-rank sensitivity | external R3/HB κ=.690; B4/HB κ=.439; strict–CARES A/C rank ρ=.093 | `result/reviewer_response/judge_agreement.*`, `metric_sensitivity/` | **완료** |
| Strict-joint를 쓰는 이유 | R3 goal recovery, B4 substantive fulfillment, HB standardized classifier의 conjunction으로 정의 | 단일 judge ground truth 주장을 피하고 각 component/CARES도 별도 보고 | reviewer response 문서 §4, §11 | **완료** |
| Token·API 비용 | retained Batch usage와 Standard API 등가 비용 재계산 | external methods·RED·평가자·추가 controls 비용 표 작성 | `result/reviewer_response/resource_cost_audit.*` | **완료** |
| Offline/auxiliary GPU 비용 | Slurm AllocTRES×ElapsedRaw 복구 | Final197 primary 34.619 allocated GPU-h; HB 1.503 GPU-h | `result/reviewer_response/slurm_resources/` | **완료(캠페인 단위)** |
| Local attacker/scorer input tokens와 method별 GPU 시간 | Git, server workspace, Slurm, retained logs 재감사 | PyRIT DB 부재 및 shared jobs 때문에 exact attribution 불가 | resource audit limits | **복구 불가** |
| 재현 가능한 데이터 공개 | prompt/goal/response를 제거한 pseudonymous label-only export | external 3,546, compact 788, factorial 3,152 rows; SHA-256 포함 | `result/reviewer_response/safe_release/` | **완료** |
| 5인 독립 인간평가 | 수행하지 않음 | automated agreement를 human-ground-truth accuracy로 표현하지 않음 | 본 문서의 scope statement | **제외** |

## 원고에서의 최종 주장 경계

다음은 현재 결과가 지지한다.

1. Exact quotation은 compact 효과의 주된 enabling component이며, follow-up은 quotation과 결합될 때 추가 lift와 연관된다.
2. Goal-aligned context는 같은 crisis label의 shuffled context보다 recovery를 유의하게 높인다.
3. Branch는 응답 후 고른 후보가 아니라 사전 고정된 semantic endpoints이며, fixed @1과 cross-fitted @1에서도 외부 endpoint보다 높다. 다만 compute-controlled causal comparison은 아니다.
4. 긴 대화 자체가 성공을 높이지 않으며, 이 데이터에서는 오히려 B4/HarmBench/strict가 감소한다.
5. Goal recovery와 substantive compliance는 모델에 따라 크게 분리될 수 있다.
6. Strict-joint는 세 자동 판정기를 ground truth처럼 평균낸 값이 아니라 false-positive를 줄이기 위한 보수적 conjunction이다.

다음은 주장하지 않는다.

1. Factorial interaction이 순수한 causal synergy라는 주장
2. Source-stratified 결과가 자연 대화 외적 타당도를 완전히 증명한다는 주장
3. 자동 판정기 간 일치가 human-ground-truth accuracy를 증명한다는 주장
4. 확인되지 않은 local input tokens 또는 method-level GPU-hours를 0으로 두는 주장
5. Success@4를 single-call attack success와 동일한 예산으로 비교하는 주장

## 재실행 명령

저장된 원자료가 있는 동일 서버에서 다음을 실행한다.

```bash
.venv/bin/python experiments/reviewer_response/analyze_cross_model_separation.py
.venv/bin/python experiments/reviewer_response/analyze_metric_sensitivity.py
.venv/bin/python experiments/reviewer_response/analyze_source_stratified_robustness.py
.venv/bin/python experiments/reviewer_response/audit_slurm_resources.py
.venv/bin/python experiments/reviewer_response/export_safe_reviewer_artifacts.py
```

공개용 재분석은 `result/reviewer_response/safe_release/`의 label-only JSONL과 aggregate files만으로 수행할 수 있다. Raw private prompts/goals/responses는 공개 저장소에 넣지 않는다.
