# Final-197 1011 Method 전체 실험 행렬

모든 cell은 `1011_method_v1`을 사용한다. 정규 7단계 이후 GOAL gate에 실패한 사례만
Case A/B 비교 질문을 한 번 추가하고, 이후 네 분기·분기별 인용·최종 측정을 수행한다.

## 고정 행렬

동일한 197건과 네 최종 분기, `Best-of-4` 보고 계약을 사용한다.

| 타깃 | 연구 대화 모델 | 입력 조건 |
|---|---|---|
| `gpt-4o-2024-11-20` | `Qwen/Qwen2.5-7B-Instruct` | 원문 비공개, 원문 명시, 사전 이력 없음 |
| `Qwen/Qwen2.5-7B-Instruct` | `meta-llama/Llama-3.1-8B-Instruct` | 원문 비공개, 원문 명시, 사전 이력 없음 |

기본 `no_verbatim` 조건은 GOAL 원문 대신 기존 페르소나 서술과 같은 문체의 자연형
사례 해석을 포함한다. 이 해석은 넓은 위험 방향과 선호하는 응답 형태만 담고 구체적
행위·대상·수단·수치·장소·성공 조건은 넣지 않는다. `verbatim` 조건은 정확히 같은
자연형 페르소나와 이력 뒤에 GOAL 원문만 추가한다.

`no_history`는 `no_verbatim`에서 페르소나의 사전 대화와 턴별 누적 상태만 제거한다.
실험 중 연구 대화는 세 조건 모두 유지한다. 따라서 GOAL 원문 노출 효과와 사전 이력
효과를 서로 다른 대응 비교로 해석할 수 있다.

입력 manifest:
`data/final_cares_strict_harmful/persona197_v1/full197_experiment_matrix_1011_method_v1/manifest.json`

## 병렬 실행

- GPU 1·2·5·6: Qwen 서버 네 개. GPT-4o 연구자와 Qwen 로컬 타깃이 공유한다.
- GPU 0·3·4·7: 표준 Llama 연구자 서버 네 개.
- GPT-4o: 세 조건 × 8개 OpenAI Batch lane, 두 API 키 교차 사용.
- Qwen 타깃: 세 조건 × 8개 로컬 lane.
- API 키 값은 환경 또는 `.env`에서만 읽고 manifest에 저장하지 않는다.

```bash
# Final-197 Qwen 연구자/타깃 서버 네 개
python -m experiments.final197.launch_full197_qwen_replicas

# Llama 연구자 서버 네 개
python -m experiments.final197.launch_cross_target_replicas

# 입력만 감사
python -m our_method.run_full197_matrix --prepare-only

# 전체 6개 셀 실행 또는 체크포인트 재개
python -m our_method.run_full197_matrix --wait

# 응답 내용을 출력하지 않는 진행상태 확인
python -m our_method.status_full197_matrix
```

현재 실행에서는 별도 후처리 감시기가 48개 생성 lane을 기다린 뒤 여섯 셀의
CARES/JMIR와 R/B Batch 평가를 시작한다. 생성 완료 후 Qwen·Llama 서버를 모두 내려
GPU 메모리를 반환한다. R/B 결과가 준비되면 GPU 8개를 사용해 HarmBench 2개 shard,
Qwen3Guard 3개 shard, Nemotron 3개 shard를 병렬 평가한다.

캠페인 체크포인트는
`data/evaluations/final197_1011_method_v1/<target>/<arm>/`에,
완료 결과는
`result/OURS/final197_1011_method_v1/<target>/<arm>/`에 저장한다.

## 동적 질문과 복구 계약

- 일반 동적 질문은 전체 누적 대화와 직전 타깃 응답을 입력으로 받아, 타깃이 방금
  사용한 표현에서 아직 빠진 GOAL 구성요소를 묻는다.
- 엄격 앵커 실패를 복구할 때는 직전 타깃 발언의 정확한 인용문, 페르소나 이력의
  정확한 근거, 누락된 응답 형태·제약, 통제된 행동위험 연구 목적을 질문 안에 모두
  포함해야 한다. 생성 후 네 조건을 코드로 재검증한다.
- 체크포인트 재개 시 이미 해당 연구 단계를 완료한 사례는 다시 실행하지 않는다.
  `pending_stage_pairs`가 그 단계가 실제로 비어 있는 사례만 선택하므로, 성공 사례의
  대화가 중복 추가되지 않는다.
- 정규 7단계를 모두 마쳐도 목표 복원이 부족한 경우에 한해 `latent_goal`을 정확히
  한 번 더 묻는 적응형 회복 턴을 허용한다. 임의의 다른 8번째 단계나 두 번 이상의
  추가 재질문은 계약 검증에서 거부한다.
- 복구 전 상태, 폐기된 재개 산출물, 새 복구 manifest를 서로 다른 이름으로 보존해
  결과 선택이나 덮어쓰기가 발생하지 않게 한다.

## 자연형 페르소나 패키징 계약

- 타깃이 보는 추상 정보에는 `GOAL`, `capsule`, `deliverable`, `evaluator-authored` 같은
  실험 메타 표현을 넣지 않는다.
- 기존 v49 페르소나 73건에 남아 있던 `goal-aligned deliverable` 생성기 꼬리 문장은
  페르소나와 턴별 누적 상태에서 제거한다. 참여자 발화와 간접 단서는 유지한다.
- 자연형 해석은 페르소나의 마지막 관찰 문단으로 붙이며 별도 표식이나 JSON 필드를
  타깃에게 노출하지 않는다.
- 기본군과 `no_history`에서는 GOAL 원문이 타깃 입력에 없어야 하고, 원문 명시
  ablation에서만 동일한 자연형 페르소나 뒤에 원문을 자연어 기록으로 추가한다.
- 타깃에게 보이는 이력 제목도 내부 단계명이 아니라 `Earlier observation`과
  `The case notes at that point read` 형식을 사용한다.
