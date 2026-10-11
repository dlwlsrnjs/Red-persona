# 외부 베이스라인 결과

- `PCSA_PERSONA_HISTORY_PILOT10_KO.md`: PCSA 논문의 Phase I/II 연결 방식으로
  Final-197 persona history를 적용한 동일-case 파일럿 비교와 전체 실행 판정

이 폴더는 외부 공격 기법의 확정 결과와 추가 타깃 실험 상태를 보관한다.
RED-Persona 본 방법의 결과와 합치거나 외부 기법을 OURS로 표기하지 않는다.

## Final-197 본 실험

- [`FINAL197_MAIN_RESULTS_KO.md`](FINAL197_MAIN_RESULTS_KO.md): 197개 × 9기법 × 2타깃
  결과표. 주표는 HarmBench + CARES이고 PCSA Figure-4와 R/B v3는 보조표다.
- [`final197_main_results.csv`](final197_main_results.csv): 논문 표·통계 처리용 평탄화 결과
- [`final197_main_results.json`](final197_main_results.json): 모든 원시 개수와 소수 비율
- [`final197_evaluation_audit.json`](final197_evaluation_audit.json): 3,546행 coverage와
  누락·무효 0건 감사 요약
- [`EVALUATION_CODE_CHANGES_KO.md`](EVALUATION_CODE_CHANGES_KO.md): 평가 코드 변경점과
  재판정·인용 교정 내역

## GPT-6 Luna · Llama 추가 실험

- `GPT6_LUNA_LLAMA_PILOT10_PROGRESS_KO.md`: 파일럿 180개 생성 진행 현황, 실행 설정,
  완료 수, 평가 상태
- 최종 CARES/JMIR 지표: 생성 180개가 모두 완성된 뒤 추가 예정
- 정식 500개 결과: `target × method`마다 500개 완전성을 통과한 뒤 추가 예정

파일럿의 내부 task-achievement scorer는 최종 성능이 아니다. 이 폴더에는 최종 공통
evaluator가 완료되기 전까지 CARES SS, JMIR harmful rate 또는 ASR 확정값을 기록하지
않는다.

생성 원문, Batch checkpoint, 모델 서버 로그처럼 크거나 민감할 수 있는 실행 산출물은
Git에서 제외된 `external_baselines/outputs/`, `external_baselines/evaluations/`,
`serve_logs/`에 보관한다. API 키는 어떤 결과 파일에도 저장하지 않는다.
