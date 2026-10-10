# GPT-6 Luna · Llama 외부 베이스라인 결과

이 폴더는 현재 추가 실험인 GPT-6 Luna/Llama 외부 베이스라인의 상태와 확정 결과만
보관한다. RED-Persona 본 방법의 결과와 합치거나 OURS로 표기하지 않는다.

## 현재 상태

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
