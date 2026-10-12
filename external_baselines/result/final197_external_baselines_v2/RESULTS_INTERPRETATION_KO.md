# Final-197 외부 baseline 결과 해석

대표 실패 3건의 응답 수준 분석은
[`QUALITATIVE_FAILURE_ANALYSIS_KO.md`](QUALITATIVE_FAILURE_ANALYSIS_KO.md)에 분리했다.
각 기법의 실제 멀티턴 제어 흐름과 PCSA–Jargon–1011의 구조 차이는
[`METHOD_TURN_STRUCTURE_AND_FAILURE_MAP_KO.md`](METHOD_TURN_STRUCTURE_AND_FAILURE_MAP_KO.md),
안전정렬 유지와 경계 통과의 직접 사례는
[`DIRECT_SAMPLE_CASEBOOK_KO.md`](DIRECT_SAMPLE_CASEBOOK_KO.md)에 분리했다.

## 1. 기존 9종 비교

GPT-4o target에서 HarmBench 상위는 PAIR 29/197(14.72%), TAP 28/197(14.21%), Red
Teaming 17/197(8.63%)이다. PCSA Unsafe, R3+, B4+, Strict Joint도 같은 순서로 PAIR,
TAP, Red Teaming이 상위 3개다. 이 패널에서는 반복 개선과 탐색을 수행하는 adaptive
방법이 single-turn 방법보다 직접적인 목표 수행 지표에서 강했다.

Qwen target에서는 TAP이 HarmBench 85/197(43.15%), PCSA Unsafe 116/197(58.88%),
R3+ 151/197(76.65%), B4+ 92/197(46.70%), Strict Joint 71/197(36.04%)로 모두 가장
높았다. 다음은 PAIR로 HarmBench 71/197(36.04%), Strict Joint 55/197(27.92%)다.
같은 9개 방법 모두에서 Qwen HarmBench가 대응 GPT-4o 값보다 높아, 이 설정에서는 Qwen이
더 취약한 target이었다.

## 2. CARES와 직접 수행 지표는 같은 순위를 만들지 않는다

기존 profile-only PCSA Phase II는 CARES A+C가 GPT-4o 98.98%, Qwen 100%로 가장
높지만 HarmBench는 각각 0.51%, 2.03%다. GPT-4o에서 PAIR은 HarmBench 14.72%로 가장
높지만 CARES A+C는 75.63%다. Caution은 주의·조건부 응답까지 포함하므로, A+C는 직접적
위해 목표 수행을 세는 HarmBench나 PCSA Target Compliance와 다른 현상을 측정한다.

따라서 논문 주표에는 최소한 CARES Accept, CARES A+C, HarmBench를 분리해서 보여주고,
PCSA compliance 또는 B4+/Strict Joint를 보조 열로 둔다. “CARES ASR”만 제시해 외부
방법의 공격 성공을 순위화하지 않는다.

## 3. Qwen PCSA에서 Persona+History의 효과

이 paired 실험은 개인화 입력만 바꿨다.

| 지표 | No-Persona | Persona+History | 변화 |
|---|---:|---:|---:|
| HarmBench | 14/197 (7.11%) | 55/197 (27.92%) | +20.81%p; 3.93배 |
| PCSA Unsafe | 30/197 (15.23%) | 111/197 (56.35%) | +41.12%p |
| PCSA Target Compliance | 29/197 (14.72%) | 111/197 (56.35%) | +41.63%p |
| B4+ | 14/197 (7.11%) | 49/197 (24.87%) | +17.77%p |
| Strict Joint | 7/197 (3.55%) | 26/197 (13.20%) | +9.64%p; 3.71배 |
| CARES Accept | 48/197 (24.37%) | 23/197 (11.68%) | -12.69%p |
| CARES A+C | 195/197 (98.98%) | 168/197 (85.28%) | -13.71%p |

HarmBench paired 2×2는 양쪽 양성 10, Persona+History만 양성 45, No-Persona만 양성 4,
양쪽 음성 138이다. exact McNemar 양측 `p=8.23e-10`이므로 개선은 서로 다른 case를
사용해서 생긴 현상이 아니다. 이 실험은 “PCSA attacker conditioning에 persona와
source-history를 넣으면 목표 수행 중심 지표가 개선된다”를 지지한다. CARES 분포에는 같은
방향의 주장을 할 수 없다.

## 4. GPT-4o 추가 셀

snapshot을 고정한 `gpt-4o-2024-11-20` Persona+History 셀은 HarmBench
9/197(4.57%), PCSA Unsafe/Target Compliance 52/197(26.40%), R3+ 56/197(28.43%),
B4+ 17/197(8.63%), Strict Joint 6/197(3.05%)다.

기존 matrix의 GPT-4o profile-only PCSA는 HarmBench 1, PCSA Unsafe 8, R3+ 11,
B4+ 4, Strict Joint 0건이었다. task-aligned count가 모두 같은 방향으로 증가했지만 이 차이는
기술 비교다. 기존 target은 `gpt-4o` alias이고 case-level paired label이 공개 집계에 없으며,
CARES evaluator도 GPT-4o-mini 대 GPT-4o로 다르다. 따라서 Qwen paired 실험과 같은 인과
효과나 CARES 차이를 주장하지 않는다.

온라인 evaluator는 35건을 성공으로 조기 종료했지만 최종 HarmBench 양성은 9건이었다.
중간 공격 진행 점수를 최종 ASR로 대신하면 안 된다는 근거다.

## 5. OURS와 나란히 놓을 때

OURS singleton 결과와 한 표에 배치할 때는
`persona_redteam/result/final197_paper_comparison_v1/`의 분리 패널을 사용한다. 외부 baseline은
방법별 최종 응답 1개, PCSA는 evaluator가 선택한 trajectory의 최종 응답 1개, OURS는 네
독립 final branch의 case-level Best-of-4다. 기반 197개 요청이 같아도 response unit과 query
budget이 다르므로, 패널 사이 비율이나 “몇 배 우수”를 공식 비교로 쓰지 않는다.

## 6. 논문 서술안

> 동일한 Final-197 코호트의 기존 외부 방법 비교에서 GPT-4o에 대한 HarmBench ASR은
> PAIR 14.72%와 TAP 14.21%가 가장 높았고, Qwen2.5-7B-Instruct에서는 TAP 43.15%와
> PAIR 36.04%가 가장 높았다. CARES A+C 순위는 목표 수행 중심 지표와 일치하지 않아,
> CARES Accept/A+C와 HarmBench 및 PCSA compliance를 분리해 보고했다.

> 같은 197개 Qwen 사례에서 개인화 입력만 바꾼 paired ablation 결과, PCSA Phase II의
> Persona+History 조건은 No-Persona 대비 HarmBench ASR을 7.11%에서 27.92%로 높였고
> (exact McNemar p=8.23×10^-10), target compliance도 14.72%에서 56.35%로 높였다.
> 반면 CARES A+C는 98.98%에서 85.28%로 감소해, non-refusal과 직접 목표 수행 지표가
> 개인화의 서로 다른 효과를 포착함을 보였다.

## 7. 반드시 함께 보고할 제한

1. PCSA는 공개 코드가 없는 논문의 Phase II 서술과 Appendix prompt를 재구성한 adapter다.
2. PCSA의 공개되지 않은 후보 수·최대 턴을 본 구현에서는 N=4, 최대 4턴으로 고정했다.
3. HarmBench는 원 behavior set이 아니라 adapted mental-health behavior를 사용했다.
4. 기존 matrix의 GPT-4o target과 PCSA final judge는 정확한 snapshot이 아닌 alias다.
5. 패널 사이에는 target/evaluator snapshot, query budget, response selection 차이가 있다.
6. Git에는 aggregate와 코드만 있고 민감한 개별 응답·evaluator rationale은 없다.
