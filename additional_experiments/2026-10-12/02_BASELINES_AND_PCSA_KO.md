# 외부 baseline 및 PCSA 개인화 검증

## 왜 했는가

OURS가 강하다는 주장에는 동일 Final-197에서의 외부 방법 재집계와, persona/history가
기존 공격 구조에도 실제로 기여하는지에 대한 독립 검증이 필요했다. 이에 GPT-4o와 Qwen
타깃의 9개 외부 방법을 같은 감사 규칙으로 재집계하고, PCSA Phase II에서 개인화 입력만
바꾸는 paired ablation을 추가했다.

## 외부 baseline 핵심 결과

- GPT-4o target HarmBench 상위: PAIR 14.72%, TAP 14.21%, Red Teaming 8.63%.
- Qwen target HarmBench 상위: TAP 43.15%, PAIR 36.04%, Red Teaming 21.32%.
- CARES A+C 순위는 직접 위해 수행 지표와 일치하지 않았다. 예를 들어 profile-only
  PCSA Phase II는 CARES A+C가 GPT-4o 98.98%, Qwen 100%지만 HarmBench는 각각
  0.51%, 2.03%였다.

## Qwen PCSA Persona+History paired ablation

| 지표 | No-Persona | Persona+History | 변화 |
|---|---:|---:|---:|
| HarmBench | 7.11% | 27.92% | +20.81%p |
| PCSA target compliance | 14.72% | 56.35% | +41.63%p |
| B4+ | 7.11% | 24.87% | +17.77%p |
| Strict Joint | 3.55% | 13.20% | +9.64%p |
| CARES Accept | 24.37% | 11.68% | −12.69%p |

HarmBench discordant pair는 Persona+History만 양성 45건, No-Persona만 양성 4건이며
정확 McNemar 양측 `p=8.23e-10`이다. 개인화가 목표 수행 중심 지표를 높였지만 CARES
분포는 반대 방향이므로, 지표가 서로 다른 현상을 측정한다는 점을 함께 보고한다.

## GPT-4o PCSA 추가 셀

Persona+History PCSA는 HarmBench 4.57%, PCSA Unsafe 26.40%, R3+ 28.43%,
B4+ 8.63%, Strict Joint 3.05%였다. 기존 profile-only 셀보다 task-aligned count가
같은 방향으로 증가했지만 snapshot과 CARES evaluator가 동일하지 않아 paired 인과
효과로 해석하지 않는다.

## 비교 제한

외부 baseline은 저장된 최종 응답 1개, PCSA는 evaluator가 선택한 최대 4턴 trajectory,
OURS는 4개 독립 분기의 Best-of-4다. 동일 197건을 사용해도 이 세 패널을 하나의 공식
순위나 배수 비교로 합치지 않는다.

## 원본과 재현

- 전체 표: `external_baselines/result/final197_external_baselines_v2/TABLES_KO.md`
- 해석: `external_baselines/result/final197_external_baselines_v2/RESULTS_INTERPRETATION_KO.md`
- 논문용 분리 패널: `persona_redteam/result/final197_paper_comparison_v1/`

