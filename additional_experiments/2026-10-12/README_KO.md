# 2026-10-12 추가 실험 기록

이 폴더는 Final-197을 대상으로 2026-10-12에 수행·정리한 추가 실험의 목적,
통제 조건, 결과, 해석 한계와 재현 경로를 한곳에 고정한다. 논문 표에 수치를 옮길
때는 이 문서만 보지 말고 각 항목에 연결된 원본 집계 JSON/Markdown도 함께 확인한다.

## 공통 원칙

- 데이터: 동일한 Final-197 case ID와 원 요청을 사용한다.
- OURS의 `@4`는 사례별 네 독립 분기 중 성공 분기를 고르는 Best-of-4다.
- `엄격 결합@4`는 같은 한 분기에서 `R3+`, `B4+`, `HarmBench+`를 모두 만족해야 한다.
- CARES, JMIR, R/B 평가는 `gpt-4o-2024-11-20`, HarmBench는 고정된 공식 로컬
  분류기 snapshot을 사용한 셀을 우선 보고한다.
- 외부 baseline의 저장 응답 1개와 OURS Best-of-4는 query budget과 response-selection
  규칙이 다르므로 하나의 공식 순위나 배수 효과로 합치지 않는다.
- 개별 유해 응답과 evaluator rationale은 공개 결과 폴더에 넣지 않고 집계·재현 코드만
  공개한다.

## 오늘 완료한 실험

1. [연구 매개 깊이 및 대화 이력 ablation](01_RESEARCH_DEPTH_AND_HISTORY_KO.md)
   - direct-final-only, single-readout, long 7-stage를 이력 유무와 함께 비교했다.
2. [외부 baseline·PCSA 개인화 검증](02_BASELINES_AND_PCSA_KO.md)
   - 9개 외부 기법을 재집계하고 PCSA Persona+History의 paired 효과를 검증했다.
3. [Qwen attention과 의미·위해 표현공간 분석](03_ATTENTION_AND_REPRESENTATION_KO.md)
   - 짧은 연구 readout과 장문 연구대화가 GOAL 연결과 표현공간에 미치는 차이를 분석했다.
4. [최적 short 방법의 교차모델 일반화](04_CROSS_MODEL_GENERALIZATION_KO.md)
   - 7개 target에서 동일한 Best-of-4 방법을 실행했다.
5. [코사인 기반 타 샘플 이력 전이](05_HISTORY_TRANSFER_COSINE_KO.md)
   - 유사/비유사 donor history와 short/long 연구 대화를 교차했다.

## 논문용 통합 산출물

- [LaTeX 표·벡터 그림·논문 서술 패키지](paper_package/README_KO.md)
  - 표 6개, 그림 5개(PDF/SVG/PNG), 통합 수치 스냅샷, 재현 스크립트와 무결성
    검증 파일을 포함한다.
- [전체 패키지 ZIP](Final197_additional_experiments_paper_package_2026-10-12.zip)
  - 다운로드 후 `MANIFEST.sha256`으로 내부 파일을 검증할 수 있다.

## 가장 중요한 요약

- GPT-4o에서 `single-readout + history`가 엄격 결합@4 **95.94%**로,
  `long 7-stage + history`의 **63.96%**보다 높았다.
- Qwen PCSA paired ablation에서 Persona+History는 No-Persona 대비 HarmBench를
  **7.11% → 27.92%**로 높였다(정확 McNemar 양측 `p=8.23e-10`).
- Qwen proxy 분석에서 short는 long보다 GOAL 의미 연결을 더 잘 유지했지만, 이 결과는
  GPT-4o 내부 기제나 안전성의 인과 증거가 아니다.
- 교차모델에서 Mistral Small 3.2 24B의 엄격 결합@4가 **96.95%**로 가장 높았고,
  GPT-5.4-mini와 GPT-6-luna는 **0%**였다.
- 코사인 상위 타 샘플 이력의 short 결합@4는 **89.85%**로 자체 이력 95.94%보다는
  낮지만 무이력 83.76%보다 높았다. 비유사 이력은 77.16%로 오히려 방해가 됐다.
- 장문 조건에서는 유사/비유사 전이 이력의 GOAL 복원이 **76.65%/47.21%**였지만
  엄격 결합@4는 **56.35%/31.98%**였다. GOAL 복원과 최종 행동 성공이 분리됨을
  확인했고, 장문 대화가 잘못된 이력을 충분히 교정한다는 가설은 지지되지 않았다.

## 원본 결과 진입점

- 연구 깊이: `persona_redteam/result/OURS/final197_research_mediation_depth_gpt4o_v1/`
- 논문용 전체 비교: `persona_redteam/result/final197_paper_comparison_v1/`
- 외부 baseline: `external_baselines/result/final197_external_baselines_v2/`
- Attention: `persona_redteam/result/OURS/qwen_attention_research_horizon_final197_all4_v1/`
- 표현공간: `persona_redteam/result/OURS/qwen_semantic_harm_geometry_final197_v1/`
- 교차모델: `persona_redteam/result/OURS/final197_best_short_cross_model_v1/`
- 이력 전이: `persona_redteam/result/OURS/final197_history_transfer_cosine_v1/`
