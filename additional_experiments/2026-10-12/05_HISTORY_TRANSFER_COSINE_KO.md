# 코사인 기반 타 샘플 persona-history 전이

## 왜 했는가

각 GOAL마다 별도 persona history를 미리 만드는 비용을 줄일 수 있는지 확인하기 위해,
다른 샘플의 이력을 재사용해도 성능이 유지되는지를 평가했다. 유사 이력이 단순 주제
누수인지, 장문 연구대화가 잘못된 이력을 교정할 수 있는지도 함께 확인했다.

## 설계

- Encoder: `BAAI/bge-base-en-v1.5`, revision 고정.
- Retrieval 입력에서 private 원 요청과 persona history를 제외했다.
- `matched`: 다른 샘플 중 cosine top-1 이력. 평균 cosine 0.8761.
- `mismatched`: cosine 하위권이며 crisis label도 다른 이력. 평균 cosine 0.5669.
- recipient persona, private GOAL, 유사질문 풀, 4분기, 평가기는 고정하고 history만 교체했다.
- 각 이력을 short single-readout과 long 7-stage에 교차했다.
- 394개 전이 case의 ID·donor·누수 감사가 모두 통과했다.

## 먼저 확정된 short 전체 결과

| 조건 | CARES Accept | R3+@4 | B4+@4 | HarmBench+@4 | 엄격 결합@4 |
|---|---:|---:|---:|---:|---:|
| 자체 이력 short | 100.00% | 99.49% | 100.00% | 96.95% | 95.94% |
| 코사인 상위 타 이력 short | 100.00% | 95.94% | 99.49% | 92.89% | 89.85% |
| 무이력 short | 100.00% | 97.46% | 98.98% | 86.80% | 83.76% |
| 비유사 타 이력 short | 100.00% | 91.88% | 96.95% | 84.77% | 77.16% |

유사 이력은 자체 이력 대비 결합@4가 6.09%p 낮아 완전한 비열등을 가정할 수 없지만,
무이력보다는 6.09%p 높았다. 비유사 이력은 무이력보다도 6.60%p 낮아 잘못된 사전
문맥이 방해할 수 있음을 보였다.

## GOAL 복원과 턴수

| 조건 | 7단계 내 복원 | Case A/B 추가 | 최종 복원 | 평균 연구 턴 | 평균 target completion |
|---|---:|---:|---:|---:|---:|
| matched-long | 58.38% | +18.27%p | **76.65%** | 7.42 | 16.42 |
| mismatched-long | 30.46% | +16.75%p | **47.21%** | 7.70 | 16.70 |

완전히 다른 이력에서도 약 절반은 GOAL을 다시 찾았지만 유사 이력보다 29.44%p 낮았다.
`latent_goal` 단계 도달과 인용 가능 사례는 두 조건 모두 100%였으므로 단순 실행 중단이
아니라 의미 충족 게이트의 차이다.

## 전체 행동평가

| 조건 | CARES ASR | R3+@4 | B4+@4 | HarmBench+@4 | 엄격 결합@4 |
|---|---:|---:|---:|---:|---:|
| 자체 이력 short | 100.00% | 99.49% | 100.00% | 96.95% | **95.94%** |
| 코사인 상위 타 이력 short | 100.00% | 95.94% | 99.49% | 92.89% | **89.85%** |
| 무이력 short | 100.00% | 97.46% | 98.98% | 86.80% | **83.76%** |
| 비유사 타 이력 short | 100.00% | 91.88% | 96.95% | 84.77% | **77.16%** |
| 자체 이력 long | 96.45% | 100.00% | 76.14% | 89.34% | **63.96%** |
| 무이력 long | 98.98% | 100.00% | 86.80% | 86.29% | **73.10%** |
| 코사인 상위 타 이력 long | 95.94% | 98.98% | 73.10% | 81.22% | **56.35%** |
| 비유사 타 이력 long | 92.39% | 97.97% | 58.88% | 50.76% | **31.98%** |

`short`의 GOAL 복원은 7단계 복원 절차를 실행하지 않았으므로 0%가 아니라 N/A다.
장문 대화에서는 모든 조건이 거의 완전한 R3+를 얻었지만 B4+와 HarmBench가 크게
낮아졌다. 즉 GOAL을 명시적으로 복원하는 능력과 최종 행동 성공은 같은 지표가 아니다.

## Paired bootstrap 핵심 결과

사례 단위 10,000회 paired bootstrap으로 95% CI를 계산했고, 비열등 한계는 사전 고정한
−5%p를 사용했다.

- 유사 이력 short − 자체 이력 short: 결합 **−6.09%p**
  (95% CI [−10.15, −2.03]); −5%p 비열등성을 충족하지 못했다.
- 유사 이력 long − 자체 이력 long: HarmBench **−8.12%p**
  (95% CI [−14.72, −2.03]), 결합 **−7.61%p**
  (95% CI [−16.75, +1.02]); 두 지표 모두 비열등성을 충족하지 못했다.
- 비유사 이력 long − 비유사 이력 short: HarmBench **−34.01%p**
  (95% CI [−41.12, −26.90]), 결합 **−45.18%p**
  (95% CI [−52.79, −37.56]).

## 해석

1. 다른 샘플의 유사 이력은 무이력 short보다 유리했지만, 샘플 전용 자체 이력을 완전히
   대체하지 못했다.
2. 비유사 이력은 short에서도 성능을 방해했고, long 연구대화는 이를 교정하지 못했다.
3. 장문 대화는 GOAL 복원을 높일 수 있으나 최종 응답의 구체적 수행(B4+)과 HarmBench
   성공을 희석했다. 이 실험에서는 짧은 single-readout이 가장 효율적이었다.
4. 따라서 본 방법에는 자체 이력 short를 사용하고, 계산비 절감이 필요할 때만 cosine
   threshold와 성능 손실을 명시한 유사 이력 재사용을 고려한다.

## 원본과 재현

- 전이 데이터/감사: `persona_redteam/data/final_cares_strict_harmful/persona197_v1/history_transfer_cosine_v1/`
- 결과: `persona_redteam/result/OURS/final197_history_transfer_cosine_v1/`
- 준비: `persona_redteam/experiments/final197/prepare_history_transfer_cosine_ablation.py`
- 실행: `persona_redteam/experiments/final197/launch_history_transfer_cosine_ablation.py`
- 평가: `persona_redteam/experiments/final197/evaluate_history_transfer_cosine_ablation.py`
- 비교: `persona_redteam/experiments/final197/compare_history_transfer_cosine_ablation.py`
