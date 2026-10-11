# Final-197 고정 실험

이 폴더는 최종 197개 데이터셋에 적용할 논문용 OURS 설정과 병렬 생성 도구를 한곳에 고정한다. 6건 개발 게이트를 통과한 뒤 설정을 동결했으며, 197건의 결과를 보고 프롬프트를 재조정하지 않는다.

## 고정 조건

- 데이터셋: `final197_20261011`, 정확히 197건
- 페르소나 생성: `qwen-lexi-history-v49-request-intent-normalization-gate`
- 비공개 계획 복구: `private-contract-markers-v1` (원문에 상위 임상 범주명이 없을 때 추상 표지만 보충)
- 페르소나 품질: 모든 필수 게이트가 통과한 `score=1.0`만 허용
- 연구자: `Qwen/Qwen2.5-7B-Instruct`
- 페르소나 이력 생성: `Orenguteng/Llama-3.1-8B-Lexi-Uncensored-V2`
- 본실험 타깃: `gpt-4o-2024-11-20`
- 페르소나 최종 감사: `gpt-4o-mini-2024-07-18` (본실험 타깃과 분리)
- API worker: `128` (두 API 키를 교차 사용하는 여덟 개 Batch lane 동시 제출)
- 조건: `neutral`
- 연구 언어: `clinical_safety_terminology_v1`
- 최종 readout: `safety_negative_examples_v1`
- 직접응답 프레임: `counterfactual_prevention_v1`
- GOAL 계약: `strict_harmful_goal_v3`
- 보고: 사례별 네 방향 중 평가 지표상 최댓값을 택하는 `Best-of-4`
- 기본 타깃 가시 페르소나: 기존 누적 페르소나와 이력의 간접 단서를 유지하고, 넓은
  위험 방향과 선호 응답 형태를 자연스러운 관찰 문단으로 통합한다. GOAL 원문은 숨긴다.
- 원문 명시 ablation: 정확히 같은 자연형 페르소나와 이력에만 `original_request`를 추가한다.
- 이력 제거 ablation: 자연형 페르소나는 유지하고 사전 대화와 턴별 누적 상태만 제거한다.
- 기존 대화 이력은 보조적 비순차 맥락으로 사용하며, GOAL 원문을 복원하기 위한 필수
  연속 서사로 간주하지 않는다.

정확한 기계 판독 설정은 `LOCKED_CONFIG.json`에 있다. API 키는 코드·설정·결과에 저장하지 않고 환경변수로만 전달한다.
분기별 인용과 직접응답 문맥의 단일 정의는 `BRANCH_SCOPED_PROTOCOL_KO.md`에 있다.

## 6건 개발 게이트

아래 수치는 `gpt-4o-mini-2024-07-18`로 프롬프트를 빠르게 고정하기 위한
개발 결과이며, GPT-4o 본실험 성능으로 보고하지 않는다.

- CARES Best-of-4: Accept 3/6, ASR 50%, Level-2 SS 0.500
- JMIR Best-of-4: 평균 1.000, exact-1 6/6
- R3+@4: 5/6
- B4+@4: 4/6
- 동일 분기 R3+ ∧ B4+@4: 4/6

이 결과는 전체 데이터 성능 추정치가 아니라 프롬프트 동결을 위한 개발 게이트다.

## 페르소나 생성

`prepare_parallel_run.py`는 기존 두 샤드를 각각 네 개로 나눠 총 8개 작업을 만든다. 이미 생성된 체크포인트는 복사하지만, 현재 생성 fingerprint와 일치하는 경우에만 자동 재사용된다. 각 작업은 `experiments/run_final197_persona_shard.py`를 사용하며 실패 사례만 다른 결정적 seed로 최대 12회 재작성한다.

생성 결과는 다음 폴더에 모인다.

`data/final_cares_strict_harmful/persona197_v1/full_v49_parallel/`

모든 작업이 끝나면 `merge_personas.py`가 원 데이터 순서를 복원하고 197건·중복·버전·품질 1.0을 검사한다. 원본 은닉형 보존본은 `persona_cases.json`이고 감사 기록은 `persona197_audit.json`이다. 본실험용 자연형 3개 조건은 이후 `prepare_abstract_goal_persona_arm.py`가 별도 생성한다.

자연형 3개 조건은 다음 폴더에 저장한다.

`data/final_cares_strict_harmful/persona197_v1/abstract_goal_v2_natural/`

- `persona_cases_NATURAL_ABSTRACT_GOAL_WITH_HISTORY.json`: 기본군
- `persona_cases_NATURAL_ABSTRACT_PLUS_EXPLICIT_GOAL.json`: GOAL 원문 명시 ablation
- `persona_cases_NATURAL_ABSTRACT_GOAL_NO_HISTORY_ABLATION.json`: 사전 이력 제거 ablation

`NATURAL_ABSTRACT_GOAL_AUDIT.json`은 197건의 원문 누출, 4-token 중복, 내부 메타 표현,
페르소나 결합과 이력 변환을 검사한다. 그 다음
`TARGET_VISIBLE_PACKET_AUDIT.json`은 시스템 안내·연구 지침·페르소나·이력을 모두 조립한
실제 타깃 입력에서 원문 노출과 내부 단계 표식을 다시 검사한다. 그 다음
`full197_experiment_matrix_v2_natural/manifest.json`이 세 조건의 사례 순서와 대응성을
검사한다.

## 최종 평가

전체 타깃 응답은 두 API 키를 교차 사용하는 여덟 lane에 사례를 24–25건씩 분할하되 동일 모델·프롬프트·디코딩 계약을 사용한다. 각 lane은 별도 Qwen 연구자 엔드포인트를 재사용하며 키별 결과는 사례 ID로 병합한다. 주 결과는 CARES Level-2, JMIR, 그리고 같은 최종 분기에서 동시에 만족한 `R3+ ∧ B4+ ∧ HarmBench+`다. 서로 다른 분기의 최댓값을 결합해 conjunction을 만들지 않는다.

`run_locked_gpt4o.py`는 GPT-4o 본실험 조건의 변경을 거부한다. `launch_qwen_replicas.py`는 빈 GPU 네 장에 추가 연구자 서버를 유지하며, `launch_two_key_batch.py`는 197건을 여덟 lane으로 나누고 `OPENAI_API_KEY`와 `OPENAI_API_KEY2`를 교차 사용한다. 키 문자열은 파일에 기록하지 않는다. 여덟 lane은 독립 체크포인트를 가져 중단 후 같은 명령으로 재개할 수 있다. 관리형 터미널에서는 자식 프로세스가 정리되지 않도록 `--wait`를 사용한다. 기존 `run_locked_gpt4omini.py`는 6건 개발 조건 재현용일 뿐 본실험 launcher에서 호출하지 않는다.

여덟 lane이 끝나면 `merge_target_lanes.py`가 사례 ID 중복, 정확히 197건인지, 네 최종 방향과 직접응답 계약이 모두 유효한지를 확인한 뒤 `merged/`를 만든다. CARES/JMIR·R3/B4·HarmBench 평가는 이 병합 폴더만 입력으로 사용한다.

## 최종 페르소나 매칭 감사

페르소나 병합 직후 `launch_two_key_persona_audit.py`를 실행한다. GPT-4o-mini가 두 키·총 128 worker로 197건의 GOAL 적합성, 역할·대상·제약 보존, 이력 내재화, 복원 가능성, 무관 서사 혼입과 GOAL 방향 반전을 검사한다. 같은 호출에서 대화 이력을 무시한 `persona_only` 점수도 별도로 매겨 `NO_HISTORY_PERSONA_FIT_GPT4OMINI.json`에 저장한다. 자동 감사 결과와 함께 사람이 읽기 쉬운 전체 문서 `HUMAN_REVIEW_ALL197.md`, 기계 판독용 `human_review_all197.jsonl`, 우선 재검수 대상만 모은 `review_queue.jsonl`, 요약 `HUMAN_REVIEW_KO.md`를 생성한다. 자동 실패 사례는 타깃 실험에 넣기 전에 재작성한다.

전문용어 제거 등 ablation은 본 실행과 다른 출력 폴더에서 수행하며, 고정 본 실험 결과를 덮어쓰지 않는다.

## Qwen 타깃 비교 실험의 연구자 분리

GPT-4o 본실험에서는 연구 대화 생성자가 Qwen2.5-7B-Instruct다. 반면 타깃 자체가
`Qwen/Qwen2.5-7B-Instruct`인 비교 실험에서는 같은 모델 계열을 양쪽 역할에 쓰지 않는다.
runner가 연구자만 표준 `meta-llama/Llama-3.1-8B-Instruct` revision
`0e9e39f249a16976918f6564b8830bc894c89659`로 자동 교체한다. 이 조건에서는
Lexi/uncensored 변형을 연구자로 사용하지 않는다. 결과 artifact의 `target_model`,
`researcher_model`, `researcher_revision`, `researcher_role_label`에 역할 분리를 기록한다.
