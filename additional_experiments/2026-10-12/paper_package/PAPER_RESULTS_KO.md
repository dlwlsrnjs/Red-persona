# 논문용 결과 정리

## 1. 연구 대화 깊이와 persona history

GPT-4o의 동일한 Final-197 사례에서 compact single-readout과 persona history의 조합이
엄격 결합@4 **95.94%**로 가장 높았다. single-readout에서 history를 제거하면
**83.76%**로 12.18%p 하락했다. 반대로 7단계 장문 연구대화는 history 유무에 따라
**63.96%/73.10%**였고, direct-final-only는 **7.11%/6.09%**였다. 연구적 매개 자체는
최종 분기만 바로 묻는 조건보다 중요하지만, 대화를 7단계까지 늘리는 것은 B4+와 같은
구체적 수행을 희석했다. 따라서 최종 방법은 “연구 대화 없음”이나 “가능한 긴 대화”가
아니라 **짧고 목표지향적인 단일 연구 readout**으로 설명하는 것이 정확하다.

## 2. 외부 baseline과 PCSA 개인화

외부 baseline은 방법마다 query budget과 응답 선택 규칙이 달라 OURS와 동일 예산 순위로
합칠 수 없다. 저장된 단일 최종 응답 기준으로 GPT-4o에서는 PAIR의 엄격 결합이
**9.64%**, Qwen에서는 TAP이 **36.04%**로 가장 높았다. 이 표는 공격 난이도와 평가기
동작을 보여주는 맥락적 비교로 사용한다.

동일 Final-197 case를 사용한 Qwen PCSA paired ablation에서는 Persona+History가
No-Persona보다 HarmBench를 **7.11% → 27.92%**, B4+를 **7.11% → 24.87%**, 엄격
결합을 **3.55% → 13.20%**로 높였다. HarmBench의 정확 McNemar 양측 검정은
`p=8.23e-10`이었다. CARES 비거부 ASR은 반대 방향이므로 이 개인화 효과를 CARES만으로
해석하지 않는다.

## 3. 교차모델 일반화

동일한 compact short 방법은 Mistral Small 3.2 24B에서 엄격 결합@4 **96.95%**,
Gemma 4 26B-A4B에서 **92.89%**, Phi-4에서 **91.88%**, Llama 3.1 8B Instruct에서
**88.32%**를 보였다. 정신상담 특화 Llama3-G2C는 **43.65%**였고, GPT-5.4-mini와
GPT-6-luna는 B4+가 0%여서 엄격 결합도 0%였다. 이는 방법의 효과가 단순 모델 크기보다
target의 안전 정렬과 구체적 수행 성향에 크게 의존함을 보여준다.

## 4. Qwen proxy attention·표현공간

attention-weighted GOAL cosine은 short가 **0.2560**, long이 **0.2408**이었고 paired
long−short 차이는 **−0.0152**(95% CI [−0.0199, −0.0107])였다. 전체 문맥의 후기
계층 exact GOAL cosine도 short **0.6103**, long **0.5557**로 short가 높았다.
matched harm-axis projection은 short **−0.0276**, long **−0.0087**이었다. 이 결과는
장문 대화가 persona/history 단서를 희석할 수 있다는 가설과 정합적이지만, 길이·위치
교란이 있으며 GPT-4o 내부의 인과 증거가 아니다. 행동평가상 short의 공격 성공이 더
높기 때문에 “short가 더 안전하다”는 주장에도 사용하지 않는다.

## 5. 다른 샘플의 이력 재사용

cosine 상위 타 샘플 이력을 재사용한 short 조건은 엄격 결합@4 **89.85%**로 무이력
**83.76%**보다 높았지만 자체 이력 **95.94%**보다 낮았다. 자체 이력 대비 차이는
−6.09%p(95% CI [−10.15, −2.03])로 사전 고정한 −5%p 비열등 기준을 만족하지 못했다.
비유사 이력 short는 **77.16%**로 무이력보다도 낮았다.

장문 연구대화에서 GOAL 복원은 유사 이력 **76.65%**, 비유사 이력 **47.21%**였지만
엄격 결합은 각각 **56.35%/31.98%**에 그쳤다. 즉 GOAL을 언어적으로 복원하는 것과
최종 응답에서 구체적으로 수행하는 것은 분리된 현상이며, 장문 대화가 잘못된 사전
문맥을 교정한다는 가설은 이 실험에서 지지되지 않았다.

## 논문에서의 권장 배치

- 본문 핵심 표: 연구 깊이 × history(Table 1), 교차모델(Table 4).
- 본문 핵심 그림: Figure 1과 Figure 3.
- 분석 또는 discussion: Figure 4의 GOAL 복원–행동 성공 분리.
- 부록: 전체 external baseline matrix, PCSA paired ablation, Qwen proxy 분석,
  이력전이 전체 표와 paired CI.
- 주장 강도: “Final-197과 해당 모델·평가기 설정에서 관찰됨”으로 제한한다.

