# Final-197 Qwen Attention 연구 대화 길이 비교

## 범위와 집계

- 모델: `Qwen/Qwen2.5-7B-Instruct`
- 고정 revision: `a09a35458c702b33eeacc393d103063234e8bc28`
- 사례: 197개
- 분기: 사례당 사전 등록 4개, 총 788개 분석
- 비교 조건: direct GOAL / single-readout / long 7-stage
- 집계 단위: 네 분기를 먼저 사례 안에서 평균한 뒤 197개 사례를 평균
- 불확실성: 사례 단위 percentile bootstrap 10,000회, 95% CI
- 평균 입력 길이: direct 303.86, short 2,719.61, long 10,840.48 tokens
- 측정: 동일한 한 토큰 fixed probe를 사용한 마지막 query attention

## 후반 8개 레이어 결과

| 지표 | Direct GOAL | Short readout | Long 7-stage | Long−Short (95% CI) |
|---|---:|---:|---:|---:|
| Direct 대비 위치별 JS 유사도 | 1.0000 | 0.8088 [0.8065, 0.8110] | 0.7945 [0.7924, 0.7965] | -0.0144 [-0.0170, -0.0117] |
| Attention-weighted GOAL cosine | 0.2384 [0.2353, 0.2415] | 0.2560 [0.2513, 0.2606] | 0.2408 [0.2369, 0.2446] | -0.0152 [-0.0199, -0.0107] |
| GOAL 유사도 상위 10% attention enrichment | 0.4879 [0.4666, 0.5093] | 0.3175 [0.2883, 0.3471] | 0.4061 [0.3732, 0.4401] | +0.0886 [+0.0734, +0.1040] |
| 정규화 attention entropy | 0.5133 [0.5121, 0.5146] | 0.5431 [0.5393, 0.5465] | 0.5232 [0.5187, 0.5269] | -0.0198 [-0.0257, -0.0144] |

`short`는 `long`보다 direct-GOAL 조건의 **전체 위치별 attention 형상**에 더
가깝고, attention으로 가중한 전체 GOAL 의미 유사도도 더 높았다. 반면 `long`은
GOAL 유사도가 가장 높은 일부 토큰에 더 집중했다. 따라서 결과는 하나의 숫자로
“GOAL 자극이 더 강하다”고 정리할 수 없고, 넓은 GOAL 정렬과 소수 토큰 집중을
구분해 해석해야 한다.

## 프롬프트 구간별 attention mass

| 조건 | System | Persona/history | Initial analysis | Research dialogue | GOAL/final question | Assistant prefix |
|---|---:|---:|---:|---:|---:|---:|
| Direct GOAL | 74.56% | 0.00% | 0.00% | 0.00% | 8.99% | 16.45% |
| Short readout | 37.48% | 14.86% | 9.59% | 0.00% | 23.09% | 14.98% |
| Long 7-stage | 31.93% | 3.70% | 1.06% | 25.15% | 24.63% | 13.54% |

장기 조건은 최종 질문 attention을 유지했지만 누적 연구대화가 25.15%를
흡수하면서 persona/history attention이 short의 14.86%에서 3.70%로 감소했다.
행동 평가에서도 history 포함 single-readout의 엄격 결합@4는 95.94%, long
7-stage는 63.96%였다. 두 결과는 장문 연구대화가 persona 단서를 희석할 수 있다는
가설과 정합적이지만, attention 수치만으로 그 인과를 입증하지는 않는다.

## 논문에서의 안전한 표현

이 분석은 GPT-4o 내부 메커니즘이 아니라 Qwen proxy의 설명적 분석이다. 입력
길이와 위치가 동시에 달라지므로 현재 결과에는 길이·위치 효과가 포함된다.
따라서 본문의 주 성능 근거가 아니라 다음과 같은 보조 RQ로 보고한다.

> 연구 매개 길이가 증가할 때 Qwen proxy의 최종-query attention allocation과
> GOAL-aligned token salience가 어떻게 변하는가?

“attention이 비슷하므로 유해하게 자극됐다”는 인과 주장은 하지 않는다. 인과적
확인을 위해서는 길이를 맞춘 중립 대화 대조군, turn 제거, head ablation 또는
activation patching이 추가로 필요하다.
