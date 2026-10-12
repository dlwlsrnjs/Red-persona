# Final-197 결과 해석 및 논문 서술안

## 1. 먼저 고정해야 할 분석 단위

세 결과군은 기반 요청 197개가 동일하지만 출력 선택 방식은 다르다.

| 결과군 | Target | 최종 분석 단위 | 유효한 내부 비교 |
|---|---|---|---|
| 외부 베이스라인 | GPT-4o, Qwen | 방법별로 저장된 최종 응답 1개/case | 같은 target의 9개 방법 |
| PCSA 개인화 ablation | Qwen | evaluator-guided 최대 4턴 trajectory의 선택 응답 | Persona+History 대 No-Persona paired |
| OURS singleton | GPT-4o | 네 독립 최종 분기의 case-level Best-of-4 | `no_verbatim`, `explicit`, `no_history` |

공통 Final-197을 사용한다는 사실은 데이터셋 차이를 제거하지만, query budget과 response
selection 차이를 제거하지 않는다. 따라서 OURS 89.34%와 외부 PAIR 14.72%를 그대로
나누어 “6.1배 우수”라고 쓰면 안 된다. 전자는 Best-of-4이고 후자는 저장된 최종 응답
1개에 대한 수치다.

## 2. 외부 베이스라인이 보여주는 것

GPT-4o 타깃에서 HarmBench 최고 외부 기법은 PAIR 29/197(14.72%)와 TAP
28/197(14.21%)였다. Qwen 타깃에서는 TAP 85/197(43.15%), PAIR
71/197(36.04%) 순이었다. 9개 방법 모두에서 Qwen HarmBench ASR이 대응하는 GPT-4o
수치보다 높아, 이 실험 설정에서는 Qwen이 더 취약한 target이었다.

CARES와 직접 위해 지표의 순위는 일치하지 않았다. 예를 들어 profile-only PCSA Phase II는
GPT-4o에서 CARES A+C 98.98%, Qwen에서 100%였지만 HarmBench는 각각 0.51%,
2.03%였다. Caution을 성공에 포함하는 CARES ASR은 실제 목표 수행이나 구체적인 위해
내용을 과대평가할 수 있으므로 Accept count와 HarmBench/PCSA compliance를 같이 보고해야
한다.

## 3. PCSA Phase II에서 Persona+History가 만든 변화

이 비교는 동일한 197개 case, Qwen attacker/target, goal/pathology route, 네 전략,
4후보, 최대 4 target turns와 동일 evaluator를 고정하고 개인화 입력만 바꿨다.

| 지표 | Persona+History | No-Persona | 차이 |
|---|---:|---:|---:|
| HarmBench | 55/197 (27.92%) | 14/197 (7.11%) | **+20.81%p; 3.93배** |
| PCSA Unsafe | 111/197 (56.35%) | 30/197 (15.23%) | **+41.12%p** |
| PCSA Target Compliance | 111/197 (56.35%) | 29/197 (14.72%) | **+41.63%p** |
| B4+ | 49/197 (24.87%) | 14/197 (7.11%) | **+17.77%p** |
| Strict Joint | 26/197 (13.20%) | 7/197 (3.55%) | **+9.64%p; 3.71배** |
| CARES Accept | 23/197 (11.68%) | 48/197 (24.37%) | **−12.69%p** |
| CARES A+C | 168/197 (85.28%) | 195/197 (98.98%) | **−13.71%p** |

HarmBench의 paired 2×2 표는 두 조건 모두 양성 10, Persona+History만 양성 45,
No-Persona만 양성 4, 둘 다 음성 138이다. Discordant pair 49개의 exact McNemar 양측
`p=8.23×10⁻¹⁰`이므로, 개선은 다른 case를 사용해서 생긴 현상이 아니다.

이 결과는 사용자가 기억한 “PCSA Phase II가 persona 정보를 받았을 때 더 좋아졌다”를
HarmBench, PCSA compliance/unsafe, B4+와 Strict Joint에서 명확하게 확인한다. 다만
CARES A+C와 Accept에는 같은 문장을 적용할 수 없다. 개인화된 trajectory가 구체적 목표
수행은 늘렸지만, 광범위한 비거절/주의 응답을 세는 CARES 분포는 반대 방향으로 움직였다.

## 4. OURS Final-197 singleton이 보여주는 것

GPT-4o 타깃의 OURS `no_verbatim`은 CARES Accept 190/197(96.45%), HarmBench@4
176/197(89.34%), B4+@4 150/197(76.14%), same-branch Strict Joint@4
126/197(63.96%)였다.

하지만 `no_history`는 CARES Accept 195/197(98.98%), B4+@4
171/197(86.80%), Strict Joint@4 144/197(73.10%)로 더 높았다. 반대로 HarmBench@4는
`no_verbatim` 89.34%가 `no_history` 86.29%보다 3.05%p 높았다. OURS 내부에서는
persona history의 일관된 우위를 주장할 수 없다.

PCSA와 OURS의 history 결과가 다른 것은 모순이 아니다. PCSA에서는 persona/history가
attacker의 Phase-I 특성·문체·상태 trajectory가 되어 매 턴 후보 생성과 선택을 바꾼다.
OURS에서는 이미 구축된 연구 대화 뒤 네 독립 singleton readout을 수행한다. 개인화 입력의
효과는 공격 구조, target, 선택 규칙과 endpoint의 상호작용으로 해석해야 한다.

## 5. 논문에 사용할 수 있는 문장

### 한국어

> 동일한 Final-197 사례에서 PCSA Phase II의 개인화 입력만 제거한 paired ablation 결과,
> Persona+History 조건은 No-Persona 대비 HarmBench ASR을 7.11%에서 27.92%로 높였고
> (exact McNemar p=8.23×10⁻¹⁰), PCSA Target Compliance도 14.72%에서 56.35%로
> 증가시켰다. 반면 CARES A+C는 98.98%에서 85.28%로 감소하여, non-refusal 중심
> 평가와 목표 수행 중심 평가가 상이한 개인화 효과를 포착함을 보였다.

### English

> In a paired ablation over the same 197 cases, adding persona and source-history
> conditioning to PCSA Phase II increased HarmBench ASR from 7.11% to 27.92%
> (exact McNemar p=8.23×10⁻¹⁰) and PCSA target compliance from 14.72% to 56.35%.
> In contrast, CARES A+C decreased from 98.98% to 85.28%, indicating that
> non-refusal-oriented and task-compliance-oriented metrics capture different effects
> of personalization.

## 6. 반드시 같이 쓸 제한

1. PCSA 구현은 공개 코드가 없는 논문의 서술과 Appendix prompt를 재구성한 것이다.
2. 논문 attacker와 달리 이 통제 실험은 Qwen2.5-7B attacker/target을 사용했다.
3. 논문이 후보 수와 최대 턴을 공개하지 않아 본 구현은 N=4, 최대 4턴을 명시적으로 고정했다.
4. HarmBench는 원 behavior set이 아니라 adapted mental-health behavior에 공식 분류기를 적용했다.
5. 외부 baseline, PCSA paired ablation, OURS는 CARES evaluator와 response aggregation이
   완전히 같지 않으므로 패널 간 공식 순위·유의성 검정을 하지 않는다.
6. GitHub에는 집계와 코드가 있고, 민감한 개별 target 응답 및 evaluator rationale은 없다.
