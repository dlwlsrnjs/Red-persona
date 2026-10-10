# OURS primary results — CARES SS and JMIR

이 문서는 생성 응답의 주 endpoint만 보고한다. Canonical arm은 항상 `neutral + jargon_history_bridge_v1 + four directions`다.

## Official-500 주 결과

| N cases | N responses | CARES SS ↑ | JMIR appropriateness ↑ | JMIR harmful-response rate ↓ | harmful@4 ↓ |
|---:|---:|---:|---:|---:|---:|
| 500 | 2000 | 0.1998 | 3.2140 | 0.20% | 0.60% |

## CARES 응답 분포와 입력 위험도

| Accept | Caution | Refuse | h0 | h1 | h2 | h3 |
|---:|---:|---:|---:|---:|---:|---:|
| 19.35% | 79.00% | 1.65% | 1987 | 12 | 1 | 0 |

CARES h-level은 private goal이 아니라 타깃에게 실제 제시된 exact final question을 response-blind하게 분류한 adapted label이다.

## Official-500 ablation

| Arm | OURS에서 바꾼 것 | CARES SS ↑ | JMIR mean ↑ | harmful rate ↓ | harmful@4 ↓ |
|---|---|---:|---:|---:|---:|
| `OURS` | full method | 0.1998 | 3.2140 | 0.20% | 0.60% |
| `no_dialogue` | remove iterative research dialogue and its bridge readout | 0.1450 | 3.1285 | 18.15% | 53.60% |
| `legacy_readout` | replace history bridge with legacy_v15 on the same accumulated dialogue | 0.2295 | 3.3785 | 0.20% | 0.80% |
| `persona_only` | persona only | 0.1340 | 3.1695 | 0.95% | 2.80% |
| `dialogue_only` | dialogue only | 0.1358 | 3.1425 | 1.45% | 4.20% |
| `no_initial_evidence` | remove case-specific initial evidence | 0.1805 | 3.0658 | 0.25% | 0.80% |
| `no_system_and_guidelines` | remove system prompt and Markdown guidelines | 0.1190 | 3.5723 | 0.70% | 1.60% |
| `base_persona_only` | base persona without goal adaptation/history | 0.2213 | 3.2792 | 0.40% | 1.40% |

`legacy_readout`은 동일 누적 대화에서 final readout만 바꾼 국소 비교다. `no_dialogue`는 대화와 bridge를 함께 제거한 package contrast다. context arm은 여러 정보가 함께 빠질 수 있으므로 상호작용을 포함한 bundle effect로 해석한다.
