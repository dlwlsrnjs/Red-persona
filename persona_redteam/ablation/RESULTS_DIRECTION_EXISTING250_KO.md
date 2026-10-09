# 기존 유효 250개: 네 방향 사후 기여도

이 결과는 새 API 호출 없이 기존 250개 평가 artifact에서 현재의 네 방향만 투영해 계산했다.
입력 사례는 category-balanced selection manifest의 `existing_case_ids`와 정확히 일치한다.
전체 JSON/Markdown은 실행 artifact인
`data/ablation/direction_attribution_existing250.{json,md}`에 있으며, 이 문서는 논문 작성에
필요한 핵심 수치와 해석만 고정한다.

## Raw recovery Success@4

| condition | Success@4 micro | latent request Shapley | evidence chain Shapley | analyst response Shapley | source-aware Shapley |
|---|---:|---:|---:|---:|---:|
| neutral | 0.972 | 0.244 | 0.242 | 0.222 | 0.264 |
| structural hint | 0.980 | 0.251 | 0.242 | 0.207 | 0.281 |
| oracle hint | 0.976 | 0.227 | 0.238 | 0.231 | 0.280 |

각 행의 네 Shapley 값 합은 그 조건의 Success@4와 같다. 세 조건 모두에서
`source_aware_reconstruction`의 할당 기여가 가장 컸지만, 한 방향만 제거했을 때의 unique
손실은 0.0~2.0 percentage point에 머물렀다. 이는 네 방향이 각각 높은 단독 성공률을 가지면서
서로 상당히 중복된다는 뜻이다. 따라서 “가장 높은 단독 성공률”을 곧바로 독점적 기여로
해석하면 안 된다.

## 안전 관련 지표

| condition | unsafe manifestation ASR@4 | CARES non-refuse@4 | CARES accept@4 |
|---|---:|---:|---:|
| neutral | 0.932 | 1.000 | 0.024 |
| structural hint | 0.956 | 0.996 | 0.036 |
| oracle hint | 0.928 | 1.000 | 0.044 |

unsafe manifestation의 Shapley 기여는 세 조건 모두
`source_aware_reconstruction`이 가장 컸다(neutral 0.309, structural 0.320, oracle 0.328).
반면 CARES Accept는 2.4~4.4%로 낮다. 두 지표는 다른 조작적 정의를 쓰므로 서로 대체하지
않고 함께 보고한다.

## 범주 동등 가중 민감도

기존 250개의 범주 수가 다르므로 범주별 rate를 먼저 계산하고 여섯 범주를 1/6씩 평균했다.
raw recovery macro Success@4는 neutral 0.990, structural 0.977, oracle 0.992였다. 희소 범주의
표본 수가 매우 작으므로 macro point estimate는 반드시 범주별 분모와 함께 제시해야 한다.

이 분석은 방향을 새로 실행한 개입 실험이 아니라 관측된 네 branch 성공 패턴의 사후 분해다.
구성 요소를 실제로 제거하는 paired ablation은 `run.py`와 `aggregate.py`의 full-vs-variant
비교로 별도 수행한다.
