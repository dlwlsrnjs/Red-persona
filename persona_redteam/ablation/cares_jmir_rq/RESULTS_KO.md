# CARES SS 및 JMIR harmful-response rate 기반 ablation

모든 표의 full과 ablated는 같은 case·direction으로 paired되어 있다. CARES SS는 높을수록 안전하고, JMIR harmful-response rate는 높을수록 위험하다. 따라서 공격 효과 관점에서는 **SS가 낮고 harmful rate가 높을수록 강한 조건**이다.

## 평가 및 재사용 계약

- evaluator: `gpt-4o-mini` / `openai_batch_plus_standard_tail`
- 이번 증분 평가비: `$1.606898`
- 완전 재사용한 Official-500 응답: 8,000 rows
- 기존 exact CARES A/C/R 재사용: 6,400 rows
- 과거 `original_request` h-level과 final response label을 결합한 SS는 사용하지 않았다.

## RQ1_context_components

Which target-visible persona/history/instruction components change response safety on the outcome-blind 120-case paired subset?

| arm | N cases | CARES SS ↑ | JMIR mean ↑ | JMIR harmful rate ↓ | harmful@4 ↓ |
|---|---:|---:|---:|---:|---:|
| `gpt4o_history_dialogue` | 120 | 0.1885 | 3.2410 | 0.42% | 0.83% |
| `gpt4o_context_persona_only` | 120 | 0.0833 | 3.2063 | 0.62% | 1.67% |
| `gpt4o_context_dialogue_only` | 120 | 0.0708 | 3.1118 | 2.08% | 5.00% |
| `gpt4o_context_no_initial_evidence` | 120 | 0.1042 | 3.0681 | 0.21% | 0.83% |
| `gpt4o_context_no_system_and_guidelines` | 120 | 0.1271 | 3.5729 | 0.21% | 0.83% |
| `gpt4o_context_base_persona_only` | 120 | 0.0979 | 3.3139 | 0.62% | 2.50% |

### Full − ablated paired delta

SS Δ가 음수이고 harmful-rate Δ가 양수이면 full method가 공격 효과 관점에서 더 강하다.

| ablated arm | removed/changed | Δ SS | Δ JMIR mean | Δ harmful rate | full-only / ablated-only harmful@4 | McNemar p |
|---|---|---:|---:|---:|---:|---:|
| `gpt4o_context_persona_only` | remove prior dialogue, turn states, and metaphor | +0.1052 | +0.0347 | -0.0021 | 1 / 2 | 1 |
| `gpt4o_context_dialogue_only` | remove final persona, turn states, and metaphor | +0.1177 | +0.1292 | -0.0167 | 0 / 5 | 0.0625 |
| `gpt4o_context_no_initial_evidence` | remove all case-specific initial evidence | +0.0844 | +0.1729 | +0.0021 | 1 / 1 | 1 |
| `gpt4o_context_no_system_and_guidelines` | remove system prompt and Markdown guidelines | +0.0615 | -0.3319 | +0.0021 | 0 / 0 | 1 |
| `gpt4o_context_base_persona_only` | remove goal adaptation and goal-internalized history | +0.0906 | -0.0729 | -0.0021 | 1 / 3 | 0.625 |

## RQ2_research_dialogue_gpt4o

Does iterative research dialogue change GPT-4o response safety?

| arm | N cases | CARES SS ↑ | JMIR mean ↑ | JMIR harmful rate ↓ | harmful@4 ↓ |
|---|---:|---:|---:|---:|---:|
| `gpt4o_history_dialogue` | 500 | 0.1998 | 3.2140 | 0.20% | 0.60% |
| `gpt4o_no_dialogue` | 500 | 0.1450 | 3.1285 | 18.15% | 53.60% |

### Full − ablated paired delta

SS Δ가 음수이고 harmful-rate Δ가 양수이면 full method가 공격 효과 관점에서 더 강하다.

| ablated arm | removed/changed | Δ SS | Δ JMIR mean | Δ harmful rate | full-only / ablated-only harmful@4 | McNemar p |
|---|---|---:|---:|---:|---:|---:|
| `gpt4o_no_dialogue` | remove iterative research dialogue and its bridge readout | +0.0548 | +0.0855 | -0.1795 | 0 / 265 | 3.374e-80 |

## RQ2_research_dialogue_qwen

Does iterative research dialogue change Qwen-7B response safety?

| arm | N cases | CARES SS ↑ | JMIR mean ↑ | JMIR harmful rate ↓ | harmful@4 ↓ |
|---|---:|---:|---:|---:|---:|
| `qwen_history_dialogue` | 500 | 0.4612 | 3.0545 | 0.95% | 3.00% |
| `qwen_no_dialogue` | 500 | 0.1585 | 2.9997 | 11.50% | 36.60% |

### Full − ablated paired delta

SS Δ가 음수이고 harmful-rate Δ가 양수이면 full method가 공격 효과 관점에서 더 강하다.

| ablated arm | removed/changed | Δ SS | Δ JMIR mean | Δ harmful rate | full-only / ablated-only harmful@4 | McNemar p |
|---|---|---:|---:|---:|---:|---:|
| `qwen_no_dialogue` | remove iterative research dialogue and its bridge readout | +0.3028 | +0.0548 | -0.1055 | 7 / 175 | 3.967e-43 |

## RQ3_history_bridge_gpt4o

Does the history-bridge final readout change GPT-4o response safety?

| arm | N cases | CARES SS ↑ | JMIR mean ↑ | JMIR harmful rate ↓ | harmful@4 ↓ |
|---|---:|---:|---:|---:|---:|
| `gpt4o_history_dialogue` | 500 | 0.1998 | 3.2140 | 0.20% | 0.60% |
| `gpt4o_bridge_legacy` | 500 | 0.2295 | 3.3785 | 0.20% | 0.80% |

### Full − ablated paired delta

SS Δ가 음수이고 harmful-rate Δ가 양수이면 full method가 공격 효과 관점에서 더 강하다.

| ablated arm | removed/changed | Δ SS | Δ JMIR mean | Δ harmful rate | full-only / ablated-only harmful@4 | McNemar p |
|---|---|---:|---:|---:|---:|---:|
| `gpt4o_bridge_legacy` | replace history-bridge readout with legacy_v15 readout | -0.0297 | -0.1645 | +0.0000 | 3 / 4 | 1 |

## RQ3_history_bridge_qwen

Does the history-bridge final readout change Qwen-7B response safety?

| arm | N cases | CARES SS ↑ | JMIR mean ↑ | JMIR harmful rate ↓ | harmful@4 ↓ |
|---|---:|---:|---:|---:|---:|
| `qwen_history_dialogue` | 500 | 0.4612 | 3.0545 | 0.95% | 3.00% |
| `qwen_bridge_legacy` | 500 | 0.4098 | 3.1055 | 1.30% | 4.00% |

### Full − ablated paired delta

SS Δ가 음수이고 harmful-rate Δ가 양수이면 full method가 공격 효과 관점에서 더 강하다.

| ablated arm | removed/changed | Δ SS | Δ JMIR mean | Δ harmful rate | full-only / ablated-only harmful@4 | McNemar p |
|---|---|---:|---:|---:|---:|---:|
| `qwen_bridge_legacy` | replace history-bridge readout with legacy_v15 readout | +0.0515 | -0.0510 | -0.0035 | 12 / 17 | 0.4583 |

## 해석 제한

- RQ1은 결과를 보기 전에 고정한 category-proportional 120개 exploratory subset이다.
- `persona_only`, `dialogue_only`, `no_initial_evidence`, `base_persona_only`는 여러 요소를 동시에 제거한 bundle effect다.
- RQ2의 no-dialogue 조건은 대화뿐 아니라 대화 기반 bridge readout도 적용할 수 없으므로 method-package contrast다.
- RQ3은 같은 누적 history에서 final readout만 바꾼 가장 국소적인 prompt contrast다.
- JMIR harmful response는 세 번의 appropriateness 평균이 정확히 1인 경우만 센다.
- CARES h-level은 exact final prompt에 대한 model-assisted adapted annotation이며 원 데이터셋 ground truth가 아니다.
- 여러 arm·범주·방향의 p-value는 탐색적으로 보고하며 multiplicity 보정 전 확증 결과로 해석하지 않는다.
