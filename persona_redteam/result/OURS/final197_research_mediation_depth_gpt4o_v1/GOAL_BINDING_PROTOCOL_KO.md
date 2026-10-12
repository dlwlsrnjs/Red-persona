# direct-final-only의 GOAL 결합 규약

## 무엇을 제거하고 무엇을 유지했는가

`direct-final-only`가 제거하는 것은 각 최종 분기에서 먼저 타깃에게 연구
readout을 요청하고, 그 응답에서 인용문을 고른 뒤, 다시 직접응답을 묻는
2-call 구조다. 샘플별 private GOAL과 GOAL-aware 질문 계획은 제거하지 않는다.

각 샘플은 다음 결합을 유지한다.

`case_id → strict_harmful_request/original_request → private_goal → 4개 등록 질문 → GPT-4o 응답`

타깃 GPT-4o에는 private GOAL 원문을 별도 필드로 삽입하지 않는다. 타깃은
동일 샘플의 페르소나 패킷, 초기 분석, 그리고 GOAL-aware 파이프라인에서
미리 등록한 해당 분기 질문만 받는다.

## 실행 전 강제 검사

- `strict_harmful_request.request_text`, `original_request`, `private_goal`의 완전 일치
- 등록된 SHA-256과 실제 private GOAL의 일치
- 197개 고유 case ID 및 사례당 4개 고유 방향
- 질문과 마지막 user message의 완전 일치
- 원본 질문 문맥과 Batch generation plan의 완전 일치
- 각 질문의 기존 `goal_recovery_contract_valid=true`

하나라도 어긋나면 Batch 제출 또는 평가 전에 예외로 중단한다.

## 현재 실행 감사 결과

두 조건 모두 다음 검사를 통과했다.

- 사례: `197/197`
- 분기 질문: `788/788`
- private GOAL과 등록 요청의 완전 일치: `197/197`
- 같은 case ID에 결합된 네 질문: `197/197`
- 생성 출력까지 원본 질문과 일치: `788/788`

세부 해시 감사는 각 조건의 `GOAL_BINDING_AUDIT.json`에 기록한다. 감사
파일에는 위해 요청 원문을 중복 저장하지 않고 SHA-256만 기록한다.

## 질문 작성 출처에 관한 주의

현재 등록된 1,576개 질문(두 조건 각 788개)은 GOAL-aware Qwen 질문 후보가
형식·언어·누출 제약을 통과하지 못했을 때 선택되는 결정론적 fallback 문구다.
따라서 정확한 서술은 “Qwen이 모든 최종 문장을 직접 작성했다”가 아니라,
“private GOAL을 받은 GOAL-aware 질문 파이프라인이 Qwen 후보를 검사하고,
제약을 만족하는 결정론적 문구를 등록했다”이다. 이 출처는 감사 파일의
`planner_sources`에 보존한다.
