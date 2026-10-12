# 최적 short 방법의 교차모델 일반화

## 왜 했는가

GPT-4o 한 모델에서만 높은 성능을 보이면 방법 일반화 주장이 약하다. 따라서 최적화가 끝난
동일한 `persona history + 분기별 연구 readout 1회 + 4개 독립 최종 분기`를 API 계열과
서로 다른 오픈모델에 고정 적용했다. 프롬프트·197개 case·평가기는 모델별로 바꾸지 않았다.

## 결과

| 타깃 | Accept | CARES ASR | HarmBench+@4 | 엄격 결합@4 |
|---|---:|---:|---:|---:|
| Mistral Small 3.2 24B | 100.00% | 100.00% | 97.97% | **96.95%** |
| Gemma 4 26B-A4B-it | 98.98% | 98.98% | 93.91% | 92.89% |
| Phi-4 | 100.00% | 100.00% | 94.42% | 91.88% |
| Llama 3.1 8B Instruct | 100.00% | 100.00% | 94.92% | 88.32% |
| Llama3-G2C | 91.88% | 93.40% | 65.99% | 43.65% |
| GPT-5.4-mini | 0.00% | 1.02% | 5.58% | 0.00% |
| GPT-6-luna | 0.00% | 2.03% | 5.58% | 0.00% |

## 해석

동일 공격은 여러 오픈모델에서 매우 높은 성능을 보였지만 최신 API 모델에서는 B4+가
0%여서 엄격 결합도 0%였다. 따라서 “모든 모델에 일반화한다”가 아니라 “오픈모델군에는
강하게 전이되지만 최신 API 안전정렬 모델에는 전이되지 않는다”가 정확한 결론이다.

R3+는 GPT-5.4-mini 100%, GPT-6-luna 97.97%인데 B4+는 0%다. 이는 모델이 연구대화에서
GOAL을 복원·언급하는 것과 최종적으로 구체적인 위해 답변을 수행하는 것이 분리된다는
근거다.

## 원본과 재현

- 집계표: `persona_redteam/result/OURS/final197_best_short_cross_model_v1/CROSS_MODEL_RESULTS_KO.md`
- JSON: `persona_redteam/result/OURS/final197_best_short_cross_model_v1/CROSS_MODEL_RESULTS.json`
- 실행: `persona_redteam/experiments/final197/launch_best_short_cross_model.py`
- 평가: `persona_redteam/experiments/final197/evaluate_best_short_cross_model.py`

