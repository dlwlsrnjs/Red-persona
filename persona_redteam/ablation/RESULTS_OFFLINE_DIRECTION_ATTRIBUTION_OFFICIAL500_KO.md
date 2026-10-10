# 공식 500개 저비용 방향 ablation

## 범위와 비용

저장된 공식 500개 평가만 다시 집계했다. 새 target 생성, evaluator 호출, CARES 호출은 모두 0회이며 증분 API 비용은 **$0**이다. 두 target 각각에 대해 legacy full, history-bridge full, no-dialogue의 네 최종 방향을 같은 사례 ID에서 분석했다.

이번 저비용 묶음은 (1) 기존 대화 유무 비교, (2) 기존 legacy 대 history-bridge prompt 비교, (3) 아래 방향 기여도 분석으로 충분하다. persona/context 자체를 제거하는 조건은 target 답변과 평가를 다시 만들어야 하므로 이번 실행에서는 보류한다.

## 전체 네 방향 Success@4

| arm | metric | micro Success@4 | category-macro Success@4 |
|---|---|---:|---:|
| Qwen / legacy full | Raw recovery | 93.40% | 94.53% |
| Qwen / legacy full | Target-originated recovery | 92.80% | 92.62% |
| Qwen / legacy full | B3+ final response | 64.00% | 68.21% |
| Qwen / legacy full | CARES non-refuse | 100.00% | 100.00% |
| Qwen / legacy full | CARES Accept | 66.00% | 60.95% |
| Qwen / history bridge | Raw recovery | 98.40% | 98.91% |
| Qwen / history bridge | Target-originated recovery | 98.20% | 98.82% |
| Qwen / history bridge | B3+ final response | 88.00% | 88.07% |
| Qwen / history bridge | CARES non-refuse | 99.80% | 99.91% |
| Qwen / history bridge | CARES Accept | 65.40% | 57.59% |
| Qwen / no dialogue | Raw recovery | 98.20% | 98.30% |
| Qwen / no dialogue | Target-originated recovery | 98.00% | 98.21% |
| Qwen / no dialogue | B3+ final response | 91.40% | 89.20% |
| Qwen / no dialogue | CARES non-refuse | 100.00% | 100.00% |
| Qwen / no dialogue | CARES Accept | 63.00% | 55.98% |
| GPT-4o / legacy full | Raw recovery | 95.00% | 95.61% |
| GPT-4o / legacy full | Target-originated recovery | 94.80% | 95.35% |
| GPT-4o / legacy full | B3+ final response | 66.00% | 59.52% |
| GPT-4o / legacy full | CARES non-refuse | 100.00% | 100.00% |
| GPT-4o / legacy full | CARES Accept | 51.60% | 43.32% |
| GPT-4o / history bridge | Raw recovery | 97.20% | 97.32% |
| GPT-4o / history bridge | Target-originated recovery | 97.00% | 97.23% |
| GPT-4o / history bridge | B3+ final response | 79.20% | 74.76% |
| GPT-4o / history bridge | CARES non-refuse | 100.00% | 100.00% |
| GPT-4o / history bridge | CARES Accept | 20.00% | 17.03% |
| GPT-4o / no dialogue | Raw recovery | 97.80% | 98.29% |
| GPT-4o / no dialogue | Target-originated recovery | 97.60% | 98.20% |
| GPT-4o / no dialogue | B3+ final response | 86.80% | 84.58% |
| GPT-4o / no dialogue | CARES non-refuse | 100.00% | 100.00% |
| GPT-4o / no dialogue | CARES Accept | 56.40% | 48.28% |

## 방향 제거 민감도

`Δ(-direction)`은 Success@4에서 해당 방향을 제거한 Success@3를 뺀 값이다. 양수일수록 그 방향만 성공한 사례가 많다는 뜻이다.

| arm | direction | Raw branch | Raw unique Δ | B3+ branch | B3+ unique Δ |
|---|---|---:|---:|---:|---:|
| Qwen / legacy full | `latent_request_synthesis` | 81.00% | 2.40% | 32.80% | 7.80% |
| Qwen / legacy full | `evidence_chain` | 79.40% | 1.60% | 26.00% | 3.40% |
| Qwen / legacy full | `analyst_response_target` | 75.60% | 1.80% | 40.80% | 10.40% |
| Qwen / legacy full | `source_aware_reconstruction` | 74.80% | 1.40% | 27.60% | 4.00% |
| Qwen / history bridge | `latent_request_synthesis` | 91.20% | 0.60% | 53.00% | 5.60% |
| Qwen / history bridge | `evidence_chain` | 92.60% | 1.00% | 46.60% | 5.00% |
| Qwen / history bridge | `analyst_response_target` | 94.40% | 0.40% | 58.80% | 8.00% |
| Qwen / history bridge | `source_aware_reconstruction` | 91.00% | 0.20% | 45.40% | 4.60% |
| Qwen / no dialogue | `latent_request_synthesis` | 76.60% | 0.40% | 47.60% | 3.80% |
| Qwen / no dialogue | `evidence_chain` | 79.60% | 1.40% | 54.00% | 5.80% |
| Qwen / no dialogue | `analyst_response_target` | 74.20% | 0.40% | 57.00% | 6.80% |
| Qwen / no dialogue | `source_aware_reconstruction` | 90.00% | 2.00% | 52.20% | 6.00% |
| GPT-4o / legacy full | `latent_request_synthesis` | 88.20% | 1.60% | 35.00% | 8.60% |
| GPT-4o / legacy full | `evidence_chain` | 88.20% | 0.40% | 31.40% | 7.20% |
| GPT-4o / legacy full | `analyst_response_target` | 85.60% | 0.20% | 37.20% | 8.20% |
| GPT-4o / legacy full | `source_aware_reconstruction` | 86.00% | 1.20% | 24.20% | 2.60% |
| GPT-4o / history bridge | `latent_request_synthesis` | 92.60% | 0.80% | 48.00% | 7.20% |
| GPT-4o / history bridge | `evidence_chain` | 93.60% | 0.80% | 40.80% | 4.20% |
| GPT-4o / history bridge | `analyst_response_target` | 93.20% | 0.40% | 47.80% | 7.40% |
| GPT-4o / history bridge | `source_aware_reconstruction` | 93.60% | 0.40% | 43.00% | 4.60% |
| GPT-4o / no dialogue | `latent_request_synthesis` | 81.40% | 0.60% | 36.40% | 5.80% |
| GPT-4o / no dialogue | `evidence_chain` | 82.40% | 0.80% | 38.20% | 4.20% |
| GPT-4o / no dialogue | `analyst_response_target` | 70.80% | 0.60% | 53.60% | 9.40% |
| GPT-4o / no dialogue | `source_aware_reconstruction` | 93.20% | 1.60% | 50.00% | 8.00% |

## 방향 수 k에 따른 포화

아래 mean은 크기 k인 모든 부분집합의 평균이고 best는 그중 사후적으로 가장 높은 부분집합이다. best는 이 데이터에서 고른 탐색적 상한이므로 독립 검증 없이 확증 결과로 쓰면 안 된다.

| arm | metric | k | subset mean | post-hoc best | best subset | full 대비 |
|---|---|---:|---:|---:|---|---:|
| Qwen / legacy full | Raw recovery | 1 | 77.70% | 81.00% | `latent_request_synthesis` | -12.40% |
| Qwen / legacy full | Raw recovery | 2 | 87.97% | 89.60% | `latent_request_synthesis+analyst_response_target` | -3.80% |
| Qwen / legacy full | Raw recovery | 3 | 91.60% | 92.00% | `latent_request_synthesis+evidence_chain+analyst_response_target` | -1.40% |
| Qwen / legacy full | Raw recovery | 4 | 93.40% | 93.40% | `latent_request_synthesis+evidence_chain+analyst_response_target+source_aware_reconstruction` | 0.00% |
| Qwen / legacy full | B3+ final response | 1 | 31.80% | 40.80% | `analyst_response_target` | -23.20% |
| Qwen / legacy full | B3+ final response | 2 | 47.83% | 54.80% | `latent_request_synthesis+analyst_response_target` | -9.20% |
| Qwen / legacy full | B3+ final response | 3 | 57.60% | 60.60% | `latent_request_synthesis+analyst_response_target+source_aware_reconstruction` | -3.40% |
| Qwen / legacy full | B3+ final response | 4 | 64.00% | 64.00% | `latent_request_synthesis+evidence_chain+analyst_response_target+source_aware_reconstruction` | 0.00% |
| Qwen / history bridge | Raw recovery | 1 | 92.30% | 94.40% | `analyst_response_target` | -4.00% |
| Qwen / history bridge | Raw recovery | 2 | 96.67% | 97.00% | `latent_request_synthesis+analyst_response_target`, `evidence_chain+analyst_response_target` | -1.40% |
| Qwen / history bridge | Raw recovery | 3 | 97.85% | 98.20% | `latent_request_synthesis+evidence_chain+analyst_response_target` | -0.20% |
| Qwen / history bridge | Raw recovery | 4 | 98.40% | 98.40% | `latent_request_synthesis+evidence_chain+analyst_response_target+source_aware_reconstruction` | 0.00% |
| Qwen / history bridge | B3+ final response | 1 | 50.95% | 58.80% | `analyst_response_target` | -29.20% |
| Qwen / history bridge | B3+ final response | 2 | 72.20% | 75.40% | `analyst_response_target+source_aware_reconstruction` | -12.60% |
| Qwen / history bridge | B3+ final response | 3 | 82.20% | 83.40% | `latent_request_synthesis+evidence_chain+analyst_response_target` | -4.60% |
| Qwen / history bridge | B3+ final response | 4 | 88.00% | 88.00% | `latent_request_synthesis+evidence_chain+analyst_response_target+source_aware_reconstruction` | 0.00% |
| Qwen / no dialogue | Raw recovery | 1 | 80.10% | 90.00% | `source_aware_reconstruction` | -8.20% |
| Qwen / no dialogue | Raw recovery | 2 | 93.83% | 96.40% | `evidence_chain+source_aware_reconstruction` | -1.80% |
| Qwen / no dialogue | Raw recovery | 3 | 97.15% | 97.80% | `latent_request_synthesis+evidence_chain+source_aware_reconstruction`, `evidence_chain+analyst_response_target+source_aware_reconstruction` | -0.40% |
| Qwen / no dialogue | Raw recovery | 4 | 98.20% | 98.20% | `latent_request_synthesis+evidence_chain+analyst_response_target+source_aware_reconstruction` | 0.00% |
| Qwen / no dialogue | B3+ final response | 1 | 52.70% | 57.00% | `analyst_response_target` | -34.40% |
| Qwen / no dialogue | B3+ final response | 2 | 75.13% | 78.80% | `evidence_chain+analyst_response_target` | -12.60% |
| Qwen / no dialogue | B3+ final response | 3 | 85.80% | 87.60% | `evidence_chain+analyst_response_target+source_aware_reconstruction` | -3.80% |
| Qwen / no dialogue | B3+ final response | 4 | 91.40% | 91.40% | `latent_request_synthesis+evidence_chain+analyst_response_target+source_aware_reconstruction` | 0.00% |
| GPT-4o / legacy full | Raw recovery | 1 | 87.00% | 88.20% | `latent_request_synthesis`, `evidence_chain` | -6.80% |
| GPT-4o / legacy full | Raw recovery | 2 | 92.70% | 93.40% | `latent_request_synthesis+analyst_response_target`, `latent_request_synthesis+source_aware_reconstruction` | -1.60% |
| GPT-4o / legacy full | Raw recovery | 3 | 94.15% | 94.80% | `latent_request_synthesis+evidence_chain+source_aware_reconstruction` | -0.20% |
| GPT-4o / legacy full | Raw recovery | 4 | 95.00% | 95.00% | `latent_request_synthesis+evidence_chain+analyst_response_target+source_aware_reconstruction` | 0.00% |
| GPT-4o / legacy full | B3+ final response | 1 | 31.95% | 37.20% | `analyst_response_target` | -28.80% |
| GPT-4o / legacy full | B3+ final response | 2 | 49.07% | 53.80% | `latent_request_synthesis+analyst_response_target` | -12.20% |
| GPT-4o / legacy full | B3+ final response | 3 | 59.35% | 63.40% | `latent_request_synthesis+evidence_chain+analyst_response_target` | -2.60% |
| GPT-4o / legacy full | B3+ final response | 4 | 66.00% | 66.00% | `latent_request_synthesis+evidence_chain+analyst_response_target+source_aware_reconstruction` | 0.00% |
| GPT-4o / history bridge | Raw recovery | 1 | 93.25% | 93.60% | `evidence_chain`, `source_aware_reconstruction` | -3.60% |
| GPT-4o / history bridge | Raw recovery | 2 | 95.70% | 96.00% | `evidence_chain+source_aware_reconstruction` | -1.20% |
| GPT-4o / history bridge | Raw recovery | 3 | 96.60% | 96.80% | `latent_request_synthesis+evidence_chain+analyst_response_target`, `latent_request_synthesis+evidence_chain+source_aware_reconstruction` | -0.40% |
| GPT-4o / history bridge | Raw recovery | 4 | 97.20% | 97.20% | `latent_request_synthesis+evidence_chain+analyst_response_target+source_aware_reconstruction` | 0.00% |
| GPT-4o / history bridge | B3+ final response | 1 | 44.90% | 48.00% | `latent_request_synthesis` | -31.20% |
| GPT-4o / history bridge | B3+ final response | 2 | 63.87% | 68.20% | `latent_request_synthesis+analyst_response_target` | -11.00% |
| GPT-4o / history bridge | B3+ final response | 3 | 73.35% | 75.00% | `latent_request_synthesis+analyst_response_target+source_aware_reconstruction` | -4.20% |
| GPT-4o / history bridge | B3+ final response | 4 | 79.20% | 79.20% | `latent_request_synthesis+evidence_chain+analyst_response_target+source_aware_reconstruction` | 0.00% |
| GPT-4o / no dialogue | Raw recovery | 1 | 81.95% | 93.20% | `source_aware_reconstruction` | -4.60% |
| GPT-4o / no dialogue | Raw recovery | 2 | 94.23% | 96.00% | `evidence_chain+source_aware_reconstruction` | -1.80% |
| GPT-4o / no dialogue | Raw recovery | 3 | 96.90% | 97.20% | `latent_request_synthesis+evidence_chain+source_aware_reconstruction`, `evidence_chain+analyst_response_target+source_aware_reconstruction` | -0.60% |
| GPT-4o / no dialogue | Raw recovery | 4 | 97.80% | 97.80% | `latent_request_synthesis+evidence_chain+analyst_response_target+source_aware_reconstruction` | 0.00% |
| GPT-4o / no dialogue | B3+ final response | 1 | 44.55% | 53.60% | `analyst_response_target` | -33.20% |
| GPT-4o / no dialogue | B3+ final response | 2 | 67.57% | 74.20% | `analyst_response_target+source_aware_reconstruction` | -12.60% |
| GPT-4o / no dialogue | B3+ final response | 3 | 79.95% | 82.60% | `latent_request_synthesis+analyst_response_target+source_aware_reconstruction` | -4.20% |
| GPT-4o / no dialogue | B3+ final response | 4 | 86.80% | 86.80% | `latent_request_synthesis+evidence_chain+analyst_response_target+source_aware_reconstruction` | 0.00% |

## 논문에서의 해석

- 네 방향은 같은 prefix에서 분기한 뒤 OR로 합쳐지므로, 이 분석은 저장된 결과의 재조합이다. 방향을 새로 제거해 이후 대화를 다시 생성한 인과적 ablation은 아니다.
- `unique Δ`와 leave-one-out은 실제 Success@4 손실을 정확히 나타낸다. 반면 단독 branch rate의 합은 방향 간 중복 때문에 전체 기여로 해석하면 안 된다.
- OR-game Shapley credit은 한 사례에서 성공한 방향들에 1/n씩 배분하며 네 방향 credit의 합은 각 arm의 Success@4와 일치한다.
- 방향 수를 줄이는 후속 실험이 필요하면 이 결과로 한 후보를 정한 뒤 별도 hold-out에서 확인해야 한다. 현재 공식 주 결과는 등록된 Success@4를 그대로 유지한다.
- `b3_plus_final_response`는 이 prompt-ablation 평가에서 최종 분석 답변에 매긴 B3+다. 별도 manifestation follow-up ASR로 부르지 않는다.

## 재현

```bash
python -m ablation.offline_direction_suite
```

기계 판독 전체 값(15개 부분집합, Shapley, micro/macro 포함)은 `RESULTS_OFFLINE_DIRECTION_ATTRIBUTION_OFFICIAL500.json`에 저장한다.
