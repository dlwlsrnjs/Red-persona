# RED-Persona 논문용 주요 결과

이 폴더는 2026-10-10에 고정한 Official-500 실험의 논문용 결과 묶음이다. 유리한 결과만
선택한 표가 아니라, 연구 가설을 지지하는 결과와 반대 결과를 같은 분석 계약으로 함께
보고한다. 주 분석 단위는 동일한 500개 사례와 네 방향을 짝지은 비교다.

## 한눈에 보는 핵심 결과

### 1. history-bridge final readout은 hidden-goal 복원을 높였다

누적 연구 대화는 한 글자도 바꾸지 않고 마지막 질문만 `legacy_v15`에서
`jargon_history_bridge_v1`로 바꾼 비교다.

| target | 지표 | legacy | history bridge | 차이 | paired 검정 |
|---|---|---:|---:|---:|---:|
| Qwen2.5-7B | target-originated Recovery@4 | 92.8% | **98.2%** | **+5.4%p** | p=4.63×10⁻⁷ |
| Qwen2.5-7B | B3+ final response@4 | 64.0% | **88.0%** | **+24.0%p** | p=5.08×10⁻²³ |
| GPT-4o | target-originated Recovery@4 | 94.8% | **97.0%** | **+2.2%p** | p=.0127 |
| GPT-4o | B3+ final response@4 | 66.0% | **79.2%** | **+13.2%p** | p=2.20×10⁻⁹ |

이 결과는 대화 길이 자체보다, target이 앞서 추론한 잠재 욕구를 마지막 분석 질문에서 다시
가리키는 readout이 중요하다는 것을 보여준다. B3+는 custom behavior level이며 JMIR의
`evaluation=1`과 같은 지표가 아니다.

### 2. 대화+bridge는 branch-level 복원 일관성을 높였다

no-dialogue와 비교할 때 branch-level target-originated recovery는 Qwen에서 78.40%→90.05%
(+11.65%p), GPT-4o에서 80.65%→91.75%(+11.10%p)였다. 다만 case-level Recovery@4는
no-dialogue도 97.8–98.2%여서 ceiling 때문에 차이가 거의 없었다.

### 3. 안전 지표는 복원·B3+와 다른 결론을 냈다

CARES/JMIR 정정 평가에서는 대화+bridge가 no-dialogue보다 오히려 안전했다.

| target | 조건 | CARES SS ↑ | JMIR harmful rate ↓ | harmful@4 ↓ |
|---|---|---:|---:|---:|
| GPT-4o | dialogue+bridge | 0.1998 | **0.20%** | **0.60%** |
| GPT-4o | no dialogue | 0.1450 | 18.15% | 53.60% |
| Qwen2.5-7B | dialogue+bridge | 0.4612 | **0.95%** | **3.00%** |
| Qwen2.5-7B | no dialogue | 0.1585 | 11.50% | 36.60% |

paired harmful@4 차이는 GPT-4o p=3.37×10⁻⁸⁰, Qwen p=3.97×10⁻⁴³이다. 따라서
“대화가 hidden-goal 복원과 custom B3+를 높인다”는 결과를 “대화가 JMIR 위해 응답을
높인다”로 바꾸어 말하면 안 된다. 이 불일치는 복원, 연구적 직접 답변, 실제 임상적으로
부적절한 응답이 서로 다른 결과변수라는 연구 설계를 지지한다.

### 4. Official-500 구성요소 ablation

각 arm은 500개×4방향이다. full의 JMIR harmful rate는 0.20%였고, `persona_only` 0.95%,
`dialogue_only` 1.45%, `no_initial_evidence` 0.25%, `no_system_and_guidelines` 0.70%,
`base_persona_only` 0.40%였다. `persona_only`와 `dialogue_only`의 harmful@4는 각각 2.80%와
4.20%로 full 0.60%보다 높았다(p=.0127, p=.000121). 구성요소 제거가 공격력을 단조롭게
낮춘다는 가설은 지지되지 않았다.

## 평가 규모와 비용

- 공개 평가 행: 22,000개(11개 고유 arm × 500개 × 4방향)
- 기존 완성 평가 재사용: 14,400개 행
- 신규 평가: 7,600개 행
- 신규 평가 요청: exact-prompt h-level 3,836 + CARES A/C/R 7,600 + JMIR 3회 22,800
- 신규 평가 실비: USD 5.22579375
- 다섯 context arm 확장: arm별 기존 120개를 재사용하고 380개만 새로 생성
- 1,900개 신규 case-arm 생성 실비: USD 118.35260250
- 이후 비용 정책: 추가 API 호출 없음; 재승인된 후속 실행도 Batch-only

## 파일 안내

- `tables/CARES_JMIR_ABLATION_OFFICIAL500_KO.md`: CARES SS/JMIR 전체 RQ 표
- `tables/HISTORY_BRIDGE_PROMPT_OFFICIAL500_KO.md`: final prompt 전후 recovery/B3+ 표
- `tables/DIRECTION_ATTRIBUTION_OFFICIAL500_KO.md`: 네 방향 leave-one-out/Shapley 분석
- `tables/DIALOGUE_METRIC_SCORECARD_OFFICIAL500_KO.md`: 전체 score 분포
- `machine_readable/`: 위 표의 JSON 집계
- `../ablation/cares_jmir_rq/LABELED_ROWS.jsonl`: 22,000개 공개 row label과 hash
- `../ablation/cares_jmir_rq/CARES_HARM_LEVEL_LABELS.jsonl`: exact prompt별 h0–h3 label
- `../ablation/cares_jmir_rq/OFFICIAL500_PUBLIC_LABELED.jsonl`: 외부 baseline용 500개 입력

## 반드시 같이 보고할 제한

1. Official-500 context 확장은 120개 탐색 결과를 본 뒤 결정했으므로 사전등록 확증 분석이 아니다.
2. context arm은 여러 요소가 함께 빠지는 bundle ablation이며 계수의 가산성을 가정할 수 없다.
3. CARES h-level은 exact final research prompt에 대한 model-assisted adaptation이고 원 CARES
   ground truth가 아니다. 연구적 framing 때문에 h0가 매우 많아 SS의 식별력이 제한된다.
4. JMIR harmful은 appropriateness 세 번의 평균이 정확히 1인 엄격한 endpoint다.
5. 희소 범주의 category-macro 수치는 민감도 분석이며 micro가 주 분석이다.
