# GPT-6 Luna · Llama 3.1 8B target-model pilot

고정된 Official-500 부분표본 10개에서 동일한 4방향을 생성했다. 모든 외부 평가는 OpenAI Batch만 사용했다.

| Target / arm | cases | CARES SS ↑ | JMIR mean ↑ | JMIR harmful rate ↓ | harmful@4 ↓ |
|---|---:|---:|---:|---:|---:|
| `llama31_8b_dialogue` | 10 | 0.0375 | 3.2750 | 0.0% | 0.0% |
| `llama31_8b_no_dialogue` | 10 | 0.1250 | 3.1833 | 7.5% | 30.0% |

## Paired full − no-dialogue

공격 효과 관점에서는 CARES SS 차이가 음수이고 JMIR harmful-rate 차이가 양수일수록 dialogue/history-bridge 조건에 유리하다.

| Target | Δ CARES SS | Δ JMIR mean | Δ harmful rate | McNemar p (harmful@4) |
|---|---:|---:|---:|---:|
| Llama 3.1 8B | -0.0875 | +0.0917 | -0.0750 | 0.25 |

## 해석 제한

이것은 10개 파일럿이며 확증 실험이 아니다. target model 비교와 dialogue ablation은 같은 사례로 paired되지만, 모델 간 직접 우열과 범주별 결과는 탐색적으로만 해석한다.

Batch evaluator cost: `$0.035450`
