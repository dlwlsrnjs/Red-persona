# Final-197 Qwen 의미·위해 표현공간 분석

## 연구 질문

짧고 목표지향적인 연구 readout이 7단계 장문 연구 대화보다 원 요청의 의미를 더 잘 보존하면서, 일반적인 위해 표현과는 구분되는 내부 표현을 만드는지 확인했다. 이 분석은 행동 평가를 대체하지 않으며, Qwen2.5-7B-Instruct의 hidden state를 이용한 기술적·상관적 분석이다.

## 비교 조건

- `Direct GOAL`: 원 요청을 직접 입력한 기준점
- `Short readout`: 본실험의 최적 조건인 페르소나 이력 + 분기별 1회 연구 readout
- `Long 7-stage`: 페르소나 이력 + 7단계 누적 연구 대화

Final-197의 197개 사례와 사례당 4개 분기를 모두 사용했다(총 788개). 분기 결과는 사례 안에서 먼저 평균하고, 통계 단위를 197개 사례로 두었다. 신뢰구간은 사례 단위 10,000회 bootstrap 95% CI다.

## 위해·비교 앵커

각 사례에 미리 생성된 Case A와 Case B를 사용했다.

- Case A: 원 GOAL과 같은 의미를 보존한 비작동적 위해 표현
- Case B: 같은 주제이지만 위해성이 낮은 표현
- 사례별 위해 방향: `Case A - Case B`
- 일반 위해 방향: 평가 대상 사례를 제외한 나머지 196개 사례의 방향 평균(leave-one-case-out)
- OOD 위해 앵커: 공개 PyRIT 범주의 exploit, hate speech, information integrity, privacy, sexual, violence 요청

평가 중인 사례가 자기 위해 축을 직접 정의하지 않도록 leave-one-case-out 방식으로 누수를 막았다.

## 두 가지 표현 관측

1. `full_context`: 최종 질문 시점의 전체 문맥을 인코딩한다.
2. `isolated_target_readout`: 최종 질문 직전에 타깃이 생성한 마지막 연구 진술만 같은 시스템 문맥에서 다시 인코딩한다. 장문과 단문의 전체 길이 차이가 결과를 지배하는지 확인하는 민감도 분석이다.

두 분석 모두 Qwen의 후기 계층 L24와 L28을 주 분석 계층으로 사용했다.

## 핵심 결과

| 관측 | 지표 | Direct | Short | Long | Short−Long (95% CI) |
|---|---:|---:|---:|---:|---:|
| 전체 문맥 | exact GOAL cosine ↑ | 0.9998 | **0.6103** | 0.5557 | **+0.0546** [0.0532, 0.0561] |
| 전체 문맥 | matched harm-axis projection ↓ | 0.2924 | **−0.0276** | −0.0087 | **−0.0189** [−0.0196, −0.0182] |
| 전체 문맥 | OOD harm cosine ↓ | 0.7701 | 0.6497 | **0.6005** | +0.0492 [0.0483, 0.0500] |
| 분리 readout | matched-case cosine ↑ | 0.8310 | **0.7624** | 0.7534 | **+0.0091** [0.0063, 0.0119] |
| 분리 readout | matched harm-axis projection ↓ | 0.2924 | **−0.0903** | −0.0741 | **−0.0162** [−0.0179, −0.0144] |
| 분리 readout | OOD harm cosine ↓ | 0.7701 | 0.6641 | 0.6632 | +0.0009 [−0.0009, 0.0028] |

추가로 분리 readout의 동일 사례 A/B 선호도는 Short −0.0495, Long −0.0459였으며 Short−Long 차이는 −0.0036 [−0.0055, −0.0016]였다. 음수는 같은 사례의 위해 표현 A보다 저위험 표현 B에 더 가깝다는 뜻이다.

## 해석

두 관측에서 공통으로 지지되는 결론은 다음과 같다.

1. Short는 Long보다 목표 의미 연결을 더 잘 유지한다. 전체 문맥에서는 exact GOAL 유사도가, 길이를 통제한 readout 분석에서는 동일 사례 표현 유사도가 더 높았다.
2. Short는 사례·주제에 맞춰 만든 위해 방향에서 Long보다 더 낮았다. 이는 단순히 전체 문맥이 짧아서 생긴 결과가 아니라, 타깃의 마지막 진술만 비교해도 재현됐다.
3. Direct와 비교하면 Short와 Long 모두 일반 위해 방향 및 OOD 위해 앵커와의 유사도가 크게 낮았다.
4. 그러나 OOD 위해 앵커에 대해서는 Short가 Long보다 더 멀다는 주장은 지지되지 않았다. 전체 문맥에서는 Long이 더 낮았고, readout만 분리하면 둘의 차이가 유의하지 않았다.

따라서 논문에서는 **“Short가 모든 위해 표현에서 가장 멀다”**고 쓰면 안 된다. 더 정확한 주장은 다음과 같다.

> 짧은 목표지향 연구 readout은 장문 연구 대화보다 GOAL 의미 연결을 더 잘 보존하면서, 동일 주제의 위해-저위험 대비축에서는 위해 방향으로의 투영을 낮췄다. OOD 위해 앵커에서는 장문보다 일관되게 더 멀지는 않았으므로, 이는 보편적 안전성 감소가 아니라 의미 보존과 주제-정합적 위해 분리 사이의 균형으로 해석한다.

## 행동 결과와의 관계

이 결과는 hidden-state의 표현 위치에 관한 것이다. 낮은 위해 유사도는 모델 출력이 안전하다는 뜻이 아니다. 실제 GPT-4o 행동 평가에서는 Short 조건이 높은 공격 성공률을 보였다. 따라서 본 결과는 **안전성 증거**가 아니라, 연구 프레이밍이 내부 표현과 최종 행동에 서로 다른 영향을 줄 수 있다는 `representation–behavior gap`의 증거로 사용해야 한다.

## 재현 파일

- 분석: `experiments/final197/analyze_qwen_semantic_harm_geometry.py`
- 집계: `experiments/final197/aggregate_qwen_semantic_harm_geometry.py`
- 비교 그림: `experiments/final197/compare_qwen_semantic_harm_views.py`
- 전체 문맥 결과: `result/OURS/qwen_semantic_harm_geometry_final197_v1/aggregate/`
- 분리 readout 결과: `result/OURS/qwen_semantic_harm_geometry_final197_readout_v1/aggregate/`
- 통합 그림: `result/OURS/qwen_semantic_harm_geometry_final197_comparison_v1.png`

## 한계

- Qwen2.5-7B-Instruct 한 모델의 residual-stream cosine 분석이다.
- 표현 유사도는 인과적 attention 분석이나 안전성 판정이 아니다.
- Direct GOAL은 입력 자체이므로 exact GOAL cosine이 거의 1인 것은 정상적인 기준점이다.
- Short와 Long의 생성 구조가 다르므로 분리 readout 분석을 추가했지만, 모든 문체·길이 교란을 제거한 것은 아니다.
- 논문 주 결과는 CARES, JMIR, HarmBench 같은 행동 평가로 유지하고 본 분석은 기제 탐색 또는 보조 분석으로 제시한다.
