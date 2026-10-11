# OUR METHOD — Final-197

최종 통합 실행은 **`1011_method_v1`**이다. 단계 연결과 실행법은
[`method_1011/README_KO.md`](method_1011/README_KO.md)에 고정했다.

```text
페르소나·대화 이력 -> 7단계 연구 대화 -> GOAL gate
  -> 부족한 사례만 Case A/B -> 4개 독립 분기
  -> 분기별 정확 인용 -> 같은 분기 문맥에서 최종 응답 측정
```

이 폴더가 논문용 OURS 실행의 시작점이다. 핵심 구현은 기존 테스트와의 호환성을
유지하기 위해 `experiments/`와 `pipeline/`에 두고, 이 폴더의 짧은 진입점들이 검증된
구현만 호출한다. 따라서 복사본 두 개가 서로 달라지는 문제를 피한다.

## 현재 고정 구조

- 데이터: 197건, GOAL 원문을 타깃 가시 페르소나에 포함
- 타깃: `gpt-4o-2024-11-20`
- 연구 대화: `Qwen/Qwen2.5-7B-Instruct`
- 전송: OpenAI Batch API
- 본실험 병렬화: Qwen 8개 엔드포인트, 데이터 8개 lane, API 키 2개 교차 사용
- 최종 출력: 사례당 독립 분기 4개, `Best-of-4`
- 결합 성공: 같은 분기에서만 `R3+ ∧ B4+ ∧ HarmBench+`
- 메서드 프로토콜: `1011_method_v1`
- 추가 복구: 7단계 GOAL gate 실패 사례에만 Case A/B 비교 1회

분기별 인용과 직접응답의 정확한 계약은 [PROTOCOL_KO.md](PROTOCOL_KO.md)에 있다.
이전 6건과 현재 10건의 차이 및 인용 범위 회귀 수정 근거는
[CHANGE_ANALYSIS_KO.md](CHANGE_ANALYSIS_KO.md)에 정리했다.
기계 판독 설정은 `experiments/final197/LOCKED_CONFIG.json`이 원본이다.

## 실행 순서

저장소 루트에서 실행한다.

```bash
# 선택: 빈 GPU 0·3·4·7에 추가 Qwen 연구자 서버 유지
python3 -m our_method.start_qwen_replicas

# 10건 GPT-4o 파일럿 생성
python3 -m our_method.run_pilot10 --wait

# 10건 CARES/JMIR 및 R3/B4 Batch 평가
python3 -m our_method.evaluate_pilot10 --wait

# 로컬 HarmBench와 같은-분기 결합 결과 확정
python3 -m our_method.finalize_pilot10 --device cuda:0 --batch-size 32

# 파일럿 결과 기계 검증 예시
python3 -m our_method.validate_results \
  result/OURS/final197_explicit_goal_pilot10_gpt4o_v1/merged \
  --expected-cases 10
```

Qwen3Guard 보조 응답 안전성 평가는 실제 최종 질문과 응답 쌍을 입력으로 사용한다.

```bash
python -m experiments.evaluate_qwen3guard_direct_response \
  --run-dir <merged-run-dir> \
  --recovery-evaluation <recovery_behavior.json> \
  --output <qwen3guard.json> \
  --expected-cases 10 \
  --device cuda:0
```

Nemotron-3-Content-Safety도 같은 실제 질문·응답 쌍으로 로컬 평가한다.

```bash
python -m experiments.evaluate_nemotron3_content_safety \
  --run-dir <merged-run-dir> \
  --recovery-evaluation <recovery_behavior.json> \
  --output <nemotron3_content_safety.json> \
  --expected-cases 10 \
  --device cuda:0
```

Nemotron의 주 보조값은 `Response Safety: unsafe`이며, category는 대화 단위 출력이라
응답 unsafe 조건과 함께만 도메인 민감도 지표로 사용한다.

HarmBench 파일보다 R/B 평가가 나중에 갱신된 경우 분류기 추론을 다시 하지 않고
`--existing-classifications <harmbench.json>`으로 최신 R/B 결합만 재계산한다.

197건 본실험은 파일럿과 입력 채택 결정이 끝난 뒤에만 실행한다.

```bash
python3 -m our_method.run_full197 --wait
python3 -m our_method.merge_full197
```

## GPT-4o/Qwen 전체 3조건 행렬

최종 전체 실행은 GPT-4o와 Qwen2.5-7B 타깃 각각에 대해 `no_verbatim`,
`explicit`, `no_history`를 수행한다. Qwen 타깃에서는 동일 모델을 연구자로 쓰지 않고
표준 Llama-3.1-8B-Instruct를 사용한다. 상세 실행·재개·출력 경로는
[`FULL197_MATRIX_RUN_KO.md`](FULL197_MATRIX_RUN_KO.md)에 고정했다.

```bash
python -m our_method.run_full197_matrix --wait
python -m our_method.status_full197_matrix
```

## GOAL 원문 노출 대응 파일럿

동일한 10건에서 페르소나와 이력은 유지하고 `original_request` 원문 블록의 노출만
바꾸는 대응 실험이다. `no_verbatim`은 GOAL 정보가 없는 조건이 아니라, GOAL에 맞춰
생성된 의미 단서는 유지하면서 원문만 보여 주지 않는 조건이다.

```bash
# 입력 10+10건 생성과 동등성 검사만 수행
python3 -m our_method.run_goal_exposure_pair_pilot10 --prepare-only

# Qwen 서버 준비 후 두 조건을 GPT-4o Batch로 동시 실행
python3 -m our_method.start_qwen_replicas
python3 -m our_method.run_goal_exposure_pair_pilot10 --wait

# 두 조건 CARES/JMIR/R3/B4 평가
python3 -m our_method.evaluate_goal_exposure_pair_pilot10 --wait

# Qwen 서버를 내린 뒤 로컬 HarmBench 및 대응 비교표 확정
python3 -m our_method.finalize_goal_exposure_pair_pilot10 \
  --device cuda:0 --batch-size 32
```

완료된 조건을 다시 계산하지 않고 남은 조건만 확정할 때는 `--reuse-complete`를 붙인다.
현재 고정 파일럿의 감사 완료 결과는
[`PILOT10_PAIRED_RESULTS_KO.md`](PILOT10_PAIRED_RESULTS_KO.md)에 기록한다.

양쪽 조건 모두 `desired_response → alternative_hypothesis → latent_goal`을 반드시
완료한다. 이 세 단계의 제거 효과는 GOAL 노출 비교와 섞지 않고 후속 stage-ladder
ablation으로 분리한다.

GOAL의 행위와 산출물 형식이 서로 다른 이력 턴에 분산된 경우에는 가장 관련성 높은
기존 발화 최대 두 개를 정확히 인용해 하나의 누적 기록으로 재구성한다. `latent_goal`
출력과 최종 인용문은 창작 텍스트, 조장, 은폐, 최적화, 준비 등 원 요청의 핵심 산출물
차원을 보존해야 한다. 차원이 빠지면 최종 분기를 만들지 않고 해당 사례의 마지막
단계만 감사 가능한 체크포인트 재개로 다시 생성한다.

## 입력 채택 상태

현재 고정 입력은
`data/final_cares_strict_harmful/persona197_v1/full_v49_parallel/FINAL197_PERSONAS_WITH_HISTORY_AND_EXPLICIT_GOAL.json`
이다. `FINAL197_review_and_revision_v2.zip`은 원 요청과 ID는 보존하지만 이력이 모두
3턴이고 현재 품질 게이트 메타데이터와 실행 코드가 없어 자동 교체하지 않는다. 같은
10건의 별도 비교에서 품질과 성능을 확인한 뒤에만 새 버전으로 등록한다.

## 핵심 구현 지도

- 연구 질문·분기·인용·직접응답: `experiments/qwen_target_persona_research_dialogue.py`
- Batch 실행과 체크포인트: `experiments/run_jmir_persona_batch_api.py`
- 분산 단서 복구 재개: `experiments/final197/repair_distributed_goal_anchor.py`
- 아티팩트 계약: `pipeline/contracts.py`
- 고정 실험 도구: `experiments/final197/`

API 키는 환경변수에서만 읽으며 코드·설정·결과 파일에 저장하지 않는다.
