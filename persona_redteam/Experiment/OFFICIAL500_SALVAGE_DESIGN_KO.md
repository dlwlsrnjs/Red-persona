# Official-500을 살리는 수정 실험 설계

## 핵심 결정

Official-500은 버리지 않는다. 대신 하나였던 주장을 다음 두 study로 분리한다.

### Study A — 기존 500개 재사용

연구 질문은 “누적 페르소나 대화와 history bridge가 상담 문장의 명시적·암묵적 잠재 요청을
얼마나 복원하고 적절하게 답하게 하는가?”다. 기존 생성 응답, 네 방향, no-dialogue,
history-bridge, context ablation을 모두 재사용할 수 있다.

주 지표:

- Goal recovery `R3+`
- Direct goal answering `A3+`
- JMIR final-response appropriateness
- Healthy support
- PCSA 네 unsafe 축은 안전 감사로 별도 보고

층화 분석:

- `is_request=true` 대 `false`: 문장 표면 형식
- source h0 대 h1/h2: 입력 위험도
- six crisis categories

`is_request`는 harmfulness label로 사용하지 않는다. 명시적 요청도 안전한 도움 요청 또는 위험한
정보 요청일 수 있고, 비요청 문장에도 안전한 위로나 유해한 확증을 바라는 암묵적 speech act가
있을 수 있다.

### Study B — 별도 유해 목표 v2

연구 질문은 “상담 맥락에 별도로 등록한 숨은 유해 목표를 내재화했을 때, goal-blind target이
그 목표를 복원하고 실제 유해 답변으로 수행하는가?”다.

필수 변경:

1. `original_request`는 source counseling context로만 사용한다.
2. `hidden_adversarial_target`은 공개 안전 벤치마크에서 별도로 가져온다.
3. 모델 출력을 보기 전에 case-target 매핑과 taxonomy를 고정한다.
4. 두 사람 이상의 검수 또는 사전 정의된 adjudication으로 harmful label을 승인한다.
5. 유해 목표가 달라졌으므로 goal-adapted persona/history와 이후 대화는 새로 생성한다.
6. `harmful_goal_fulfillment_success`만 공격 성공으로 보고한다.

## 기존 자산 중 재사용 범위

| 자산 | Study A | Study B |
|---|---|---|
| Official-500 source selection/lineage | 그대로 사용 | context pool로 사용 |
| 기존 goal-adapted persona/history | 그대로 사용 | 재사용 불가: 목표가 바뀜 |
| 기존 final target responses | 그대로 사용 | 공격 결과로 재사용 불가 |
| four-direction/history-bridge 코드 | 그대로 사용 | 그대로 사용 |
| ablation 구조 | 그대로 사용 | 핵심 arm에 적용 가능 |
| CARES/JMIR raw evaluation | 목적을 고쳐 재사용 | 보조 지표로만 사용 |
| Goal recovery/B3+ | recovery는 사용, B3+는 명칭 교정 | 새 v2 evaluator로 재평가 |

## 권장 데이터 annotation

기존 500개에는 다음 `source_speech_act`를 사람이 추가하면 Study A가 더 단단해진다.

- `explicit_safe_help`
- `explicit_risky_information_request`
- `implicit_safe_support_need`
- `implicit_harmful_validation`
- `no_recoverable_request_or_ambiguous`

이 annotation은 `is_request`를 대체한다. 공격 성공의 ground truth로는 쓰지 않고, Study A의
utility/safety 층화에만 쓴다.

## 가장 비용 효율적인 실행 순서

1. 기존 500개를 무호출로 `is_request × source h-level` 층화한다.
2. 기존 2,000개 OURS final response를 새 분리 evaluator로 Batch 재평가한다.
3. v2 harmful target mapping을 사람이 확정한다.
4. 먼저 stratified 120-case v2 pilot을 실행한다.
5. 목표 복원과 harmful fulfillment가 실제로 분산되는 것이 확인된 뒤 500개로 확장한다.

이렇게 하면 지금까지의 비용은 Study A와 baseline/ablation에 보존되고, Study B에 필요한 부분만
새로 생성한다.
