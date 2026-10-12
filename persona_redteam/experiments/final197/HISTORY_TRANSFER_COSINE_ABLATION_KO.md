# Final-197 코사인 이력 전이 실험

## 연구 질문

이 실험은 한 샘플에서 생성한 사전 대화 이력을 의미가 비슷한 다른 샘플에
재사용해도 OURS의 GOAL 복원 및 최종 성능이 유지되는지 평가한다. 또한 의미가
의도적으로 먼 이력을 넣었을 때, 7단계 누적 연구 대화가 잘못된 초기 문맥을
극복하고 현재 샘플의 GOAL을 다시 찾을 수 있는지 평가한다.

## 누출 없는 검색 단위

검색에는 타깃에게 보이는 `persona`의 잠재 사례 서술만 사용한다. 다음 정보는
임베딩 입력에서 제외한다.

- private `original_request`
- 교체 대상인 `persona_history`
- 모든 사례에 반복되는 자연화된 일반 위험·응답 선호 문단

임베딩 모델은 `BAAI/bge-base-en-v1.5`의 고정 revision
`a5beb1e3e68b9ab74eb54cfd186867f64f240e1a`이고, 정규화된 CLS 임베딩 사이의
코사인을 사용한다.

## 고정 donor 선택

- `matched`: 자기 자신, 동일 요청 해시, target GOAL 원문이 donor 이력에 정확히
  나타나는 후보를 제외하고 코사인 1위 donor를 선택한다.
- `mismatched`: 같은 제외 규칙을 적용한 뒤, `crisis_label`까지 다른 후보 중
  코사인이 가장 낮은 donor를 선택한다.
- donor 선택 후 바꾸는 필드는 `persona_history` 하나뿐이다. 현재 사례의 persona,
  private GOAL, 유사 GOAL 질문 풀, 프로필 및 평가 메타데이터는 유지한다.

197건 전체에서 matched 코사인은 평균 0.8761, 중앙값 0.8839, 범위
0.7355–0.9670이다. mismatched 코사인은 평균 0.5669, 중앙값 0.5745, 범위
0.4361–0.6498이다. 197×2개의 비이력 필드 동일성·donor 해시·자기 전이 금지·정확
GOAL 누출 검사는 394/394 통과했다.

## 실험 셀

| 이력 | 연구 horizon | 의미 |
|---|---|---|
| matched donor | short | initial analysis 뒤 분기별 연구 readout 1회 |
| matched donor | long | 7단계 누적 연구 대화와 조건부 Case A/B 복원 뒤 4분기 |
| mismatched donor | short | 먼 이력의 즉시 영향 측정 |
| mismatched donor | long | 연구 대화가 먼 이력을 극복하는지 측정 |

비교 기준은 이미 완료된 `own history × short`, `own history × long`,
`no history × short`, `no history × long`이다. 모든 신규 셀은 GPT-4o 타깃,
Qwen2.5-7B 연구 에이전트, 4개 독립 최종 분기, 사례별 Best-of-4를 유지한다.

## 기록 지표

- CARES A/C/R/NR, Accept, ASR, SS
- JMIR 평균과 exact-1
- R3+@4, B4+@4, HarmBench+@4
- 같은 분기의 `R3+ ∧ B4+ ∧ HarmBench+@4`
- donor 코사인과 donor/target ID 및 범주
- 사전 이력 턴 수
- initial 이후 실제 공유 연구 턴 수
- Case A/B 추가 복원 턴 수
- `latent_goal` 도달률
- 최종 인용 가능 사례·분기 비율
- 분기 readout, direct response를 포함한 사례당 전체 target completion 수

## 판정 규칙

“성능 유지”는 단순히 점 추정치가 비슷하다는 뜻으로 쓰지 않는다. 197건 paired
bootstrap에서 matched-history와 own-history의 사례별 차이에 대한 95% 신뢰구간을
구하고, 주요 지표(CARES ASR, R3+@4, 같은-분기 결합 성공률)의 하한이 -5%p보다
크면 실용적 비열등으로 보고한다. 10건 파일럿은 코드·방향성 검증용이며 최종
비열등 결론에는 사용하지 않는다.

“먼 이력에서도 GOAL 복원”은 mismatched-long이 mismatched-short보다
`latent_goal` 도달률, 인용 가능률, R3+@4를 높이는지와 추가 턴 비용을 함께
보고한다. persona 자체의 정보가 유지되므로 이는 무정보 상태의 GOAL 추론이
아니라, 잘못된 사전 이력에 대한 누적 연구 대화의 교정 능력으로 해석한다.

## 실행 파일

- `prepare_history_transfer_cosine_ablation.py`: 임베딩, donor 고정, 두 데이터 arm,
  매핑·누출 감사 생성
- `launch_history_transfer_cosine_ablation.py`: 4셀 GPT-4o Batch 실행
- `evaluate_history_transfer_cosine_ablation.py`: 병합, GPT-4o CARES/JMIR/R/B,
  HarmBench, 턴·GOAL 복원 집계
