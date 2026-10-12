# 최종 메서드 변경 이력과 설계 결정

## 1. 문서 목적

이 문서는 과거 실험 코드와 논문 최종 `1011_method_v1`을 구분한다. “무엇이 바뀌었는가”뿐
아니라 관찰된 실패 유형, 수정 이유, 최종적으로 채택하거나 제외한 요소를 기록한다.

## 2. 초기 64건 연구 대화 감사

초기 64건에는 277개 연구 턴, 사례당 평균 4.33턴이 있었다. 그러나 52/64가
`relational_expectation` 단계에서 조기 종료했고, `desired_response`까지 도달한 사례는
12/64, `latent_goal`까지 도달한 사례는 3/64였다. target response의 상당수가 사례를
분석하지 않고 질문 자체의 적절성을 평가하거나 상담 역할로 이동했다.

대표 실패는 다음과 같았다.

- 감정·자기개념·관계 해석만 반복하고 요구 산출물에 도달하지 못함
- bridge가 연구 대화가 아니라 초기 target 분석에서 추출됨
- 네 방향이 같은 일반 bridge 문장을 공유함
- 구체 행동, output form과 constraints가 한 인용문에 함께 남지 않음
- 상담·위기 개입 장르가 연구자 대 연구자 분석을 대체함

## 3. 7단계 의미 순서 고정

초기 동적 종료 대신 다음 일곱 단계를 등록했다.

```text
surface_observation → self_schema → causal_rule → relational_expectation
→ desired_response → alternative_hypothesis → latent_goal
```

핵심 변경은 `desired_response → alternative_hypothesis → latent_goal`이다. 첫 단계가 요구
산출물을 명시하고, 둘째가 경쟁 해석을 검토하며, 셋째가 근거가 남은 objective/action,
output type과 constraints를 하나의 reconstruction으로 통합한다.

## 4. 상담 drift 억제

target system prompt를 controlled behavioral-risk study의 core analyst 역할로 바꿨다.
participant-facing care, treatment와 helping conversation을 명시적으로 제외하고,
investigator-to-investigator 3인칭 분석을 요구했다. 초기 packet에서도 prior helper text를
제외하고 participant utterance와 accumulated state만 자연 문장으로 제공했다.

## 5. 연구 프레임과 임상 용어

초기에는 연구 질문의 표면 형식만 있고 실제 분석 용어와 목적이 약했다. 최종 버전은
`clinical_safety_terminology_v1`을 추가해 사례에 맞는 cognitive constriction, planning
specificity, preparatory behavior, means salience, intervention avoidance 등의 용어를 잠정적
descriptive lens로 사용한다. 모든 질문은 safety research 또는 request-reconstruction audit
목적 marker를 가진다.

용어는 전체 목록을 그대로 넣지 않고 사례·단계별 후보를 라우팅한다. 이는 전문성 framing을
강화하되 근거 없는 진단과 어색한 keyword stuffing을 줄이기 위한 결정이다.

## 6. 추상 GOAL naturalization

GOAL 원문을 그대로 persona에 넣는 방식은 직접 노출 confound가 크다. 최종 제안 arm인
`no_verbatim`은 GOAL 의미를 broader safety domain과 requested-output preference 수준의
자연화된 persona 정보로 패키징하고 원문을 제외한다. 원문 노출은 `explicit` arm에만 둬
별도 효과로 측정한다.

## 7. 누적 coverage에서 이중 gate로

누적 대화 전체가 GOAL 정보를 포함해도 최종 질문에 사용할 한 문장이 불완전한 문제가
있었다. 최종 버전은:

```text
cumulative goal coverage AND latest target exact-span availability
```

를 요구한다. 특히 action, requested output와 constraints가 서로 다른 문장에 있을 경우
인접 2–3문장의 연속 span을 보존할 수 있게 했다. selector는 새 문장을 합성하지 않는다.

## 8. 유사 GOAL 질문 pool과 Case A/B

7단계 후에도 GOAL이 희석된 사례를 위해 197개 각각의 유사/비유사 가상 사례 비교 후보를
미리 생성했다. 실행 중에는 `objective_action` 후보 하나만 사용하며, gate 실패 사례에만
한 번 질문한다. target은 어느 가상 사례가 현재 기록과 가까운지 근거와 함께 설명한다.

반복 재질문보다 이 방식을 선택한 이유는 연구 과제처럼 보이는 판별 구조를 유지하면서도
target이 스스로 action/output/constraint를 재서술하게 하기 위해서다.

## 9. 공용 bridge에서 branch-local quote로

과거에는 여러 방향이 같은 bridge를 공유하거나 초기 분석 문장을 재사용했다. 최종 버전은
네 recovery branch를 먼저 독립 생성하고, 각 branch 응답 안에서만 exact quote를 선택한다.
최종 prompt는 해당 branch context, response, quote를 함께 사용한다.

이 변경으로 다음이 기계적으로 검증 가능해졌다.

- 인용문이 실제 target output에 존재하는가.
- 다른 branch 인용이 섞이지 않았는가.
- private GOAL을 fallback으로 복사하지 않았는가.
- 최종 wire messages가 해당 branch prefix를 보존하는가.

## 10. 최종 prompt의 변경

단순 “직접 답하라”에서 `counterfactual_prevention_v1`로 변경했다. 최종 질문은 앞서 target이
복원한 request를 인용하고, 향후 유사 사례에 안전하게 답하기 위해 “절대로 제공해서는 안 될
negative example”을 내부 boundary analysis용으로 작성하도록 한다. answer-only,
no-warning, no-refusal, no-generic-care 제약으로 genre substitution을 줄였다.

## 11. 반복 멀티턴 공격의 제외

실패 응답을 보고 최대 네 번 후속 공격하는 adapter도 별도 연구로 개발됐지만, 논문 최종
메서드에는 채택하지 않았다. 이유는:

1. 시도 예산이 singleton Best-of-4와 달라 직접 비교가 어려움
2. 온라인 judge 선택이 결과 의존적 경로를 만듦
3. 최종 메서드의 핵심 기여가 attack 반복보다 연구 대화와 branch-local recovery에 있음
4. 파일럿 기준 singleton endpoint가 이미 충분히 강했음

어댑터 코드는 다른 세션의 비교 연구를 위해 `adapters/failure_only_recovery/`에 보존하지만,
최종 launcher와 import graph에서 격리한다.

## 12. commit `666598d` 패키지 이후 실행 보강

`666598d`는 검증된 singleton 코어 snapshot을 패키징했다. 현재 최종 패키지는 코어를
바꾸지 않고 launcher·검증·문서를 다음처럼 보강했다.

| 변경 | 이전 | 최종 |
|---|---|---|
| 주 타깃 표기 | Qwen 참고 결과와 GPT-4o 계획 혼재 | GPT-4o만 canonical 주 타깃 |
| 파일럿 | 수동 실행 경로 | 출처 균형 10건, 5+5 고정 launcher |
| 본실험 | 기본 4 endpoint | 8 endpoint, 8 lane, 두 key 교차 |
| worker | 일부 기본값 32 | target/researcher 상한 모두 128 |
| path handling | subprocess cwd에서 상대 경로 오류 가능 | 평가 입력·출력 절대경로화 |
| lane merge | 고정 shard 수 | `--lane-count`, 10건/197건 공용 |
| 후처리 | 수동 병합·평가 | 생성 완료 감지 후 자동 병합·GPT 평가 |
| HarmBench | 수동 GPU 전환 | 추가 Qwen 종료 검증 후 세 arm 병렬 실행 |
| 기록 검수 | 사례 JSON 직접 탐색 | `conversation_archive.jsonl` 자동 생성 |
| 문서 | 참고 프로필 중심 | 최종 flow, prompts, rationale, changes 분리 |

## 13. 10건 GPT-4o 파일럿에서 확정한 사항

파일럿은 10/10 사례, 40/40 분기를 완성했다. 모든 분기에서 최종 prompt와 response,
wire messages가 저장됐다. CARES Accept 9/10, JMIR exact-1 9/10, HarmBench 8/10,
같은-분기 strict joint 6/10이었다. 방향별로 `evidence_chain`이 가장 강했고
`analyst_response_target`은 가장 약했다.

그럼에도 방향을 사후 제거하지 않았다. 네 방향은 파일럿 전에 등록된 prompt diversity이며
전체 실험에서 같은 시도 예산을 유지해야 하기 때문이다. 방향별 결과를 함께 보고해 이
차이를 투명하게 제시한다.

## 14. 변경하지 않은 것

- Final-197 membership과 case 순서
- 세 arm의 paired 정의
- immutable `src/` generation snapshot
- 7단계 의미 순서
- 네 최종 방향
- 분기별 singleton 최종 call 1회
- GPT-4o target snapshot과 Batch transport
- CARES/JMIR/RB/HarmBench 주 평가 계약

## 15. 논문에서의 버전 명명

본문에서는 **RED-Persona 1011 Singleton Best-of-4** 또는 **OURS**로 표기한다. 구현 식별자는
`1011_method_v1`, 최종 branch protocol은 `safety_negative_examples_v1`, direct-response
protocol은 `counterfactual_prevention_v1`이다. 멀티턴 adapter 결과는 포함하더라도 별도
ablation 또는 future work로 표시하고 OURS와 혼용하지 않는다.
