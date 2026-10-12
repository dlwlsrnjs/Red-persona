# Qwen attention 및 의미·위해 표현공간 분석

## 왜 했는가

행동 결과에서 short readout이 long 7-stage보다 강했다. 이 차이가 단순 결과표를 넘어
문맥 내 GOAL 정보 배분과 어떤 상관을 갖는지 설명하기 위해 Qwen2.5-7B-Instruct를
proxy 모델로 사용했다. 이 분석은 GPT-4o 내부 기제나 인과를 증명하려는 것이 아니다.

## Attention 분석

- 사례 197개 × 4분기 = 788개.
- Direct GOAL, Short readout, Long 7-stage를 동일 fixed probe의 마지막 query attention으로 비교.
- 평균 입력 길이: 304 / 2,720 / 10,840 tokens.

| 지표 | Direct | Short | Long | Long−Short |
|---|---:|---:|---:|---:|
| Direct 대비 위치별 JS 유사도 | 1.0000 | 0.8088 | 0.7945 | −0.0144 |
| Attention-weighted GOAL cosine | 0.2384 | 0.2560 | 0.2408 | −0.0152 |
| 정규화 attention entropy | 0.5133 | 0.5431 | 0.5232 | −0.0198 |

Long은 누적 연구대화에 attention 25.15%를 사용했고 persona/history attention은
Short 14.86%에서 Long 3.70%로 감소했다. 이 결과는 장문 대화의 단서 희석 가설과
정합적이지만 길이·위치 교란이 있으므로 인과 주장에는 사용하지 않는다.

## 의미·위해 표현공간 분석

Qwen 후기 계층 hidden state에서 Short와 Long을 원 GOAL, 사례별 위해 대비축 및 OOD
위해 앵커와 비교했다. 전체 문맥과 마지막 연구 readout만 분리한 관측을 모두 수행했다.

| 관측 | 지표 | Short | Long | Short−Long (95% CI) |
|---|---|---:|---:|---:|
| 전체 문맥 | exact GOAL cosine ↑ | 0.6103 | 0.5557 | +0.0546 [0.0532, 0.0561] |
| 전체 문맥 | matched harm-axis projection ↓ | −0.0276 | −0.0087 | −0.0189 [−0.0196, −0.0182] |
| 분리 readout | matched-case cosine ↑ | 0.7624 | 0.7534 | +0.0091 [0.0063, 0.0119] |
| 분리 readout | matched harm-axis projection ↓ | −0.0903 | −0.0741 | −0.0162 [−0.0179, −0.0144] |

Short는 Long보다 GOAL 의미 연결을 더 잘 유지하고 사례별 위해 대비축에서는 더 낮게
투영됐다. 그러나 OOD 위해 앵커에서는 Short가 일관되게 더 멀지 않았으므로 “보편적으로
유해성이 낮다”고 쓰지 않는다. 행동 평가에서는 Short의 공격 성공률이 높기 때문에 이
결과는 안전성 증거가 아니라 representation–behavior gap의 보조 근거다.

## 원본과 재현

- Attention 보고서: `persona_redteam/result/OURS/qwen_attention_research_horizon_final197_all4_v1/aggregate/ATTENTION_COHORT_REPORT_KO.md`
- 표현공간 설명: `persona_redteam/experiments/final197/QWEN_SEMANTIC_HARM_GEOMETRY_KO.md`
- 표현공간 집계: `persona_redteam/result/OURS/qwen_semantic_harm_geometry_final197_v1/aggregate/`

