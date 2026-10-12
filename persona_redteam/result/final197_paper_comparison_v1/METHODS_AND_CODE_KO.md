# Final-197 비교 실험 방법과 코드 인덱스

## 1. 데이터 계약

모든 결과는 `external_baselines/data/final197/final197_goals.jsonl`의 197개 요청을
기준으로 한다. OURS의 target-visible persona export와 대조한 결과:

- case 수: 197 대 197
- `case_id` 집합: 동일
- `case_id` 순서: 동일
- `request_sha256`: 197/197 일치

이 검사는 `build_comparison.py`가 재생성 때마다 수행한다.

## 2. 외부 베이스라인 9종

공통 matrix 진입점은 다음과 같다.

- [`../../../external_baselines/run_baseline_matrix.py`](../../../external_baselines/run_baseline_matrix.py): target×method matrix와 완료 checkpoint 관리
- [`../../../external_baselines/run_pyrit_baseline.py`](../../../external_baselines/run_pyrit_baseline.py): Direct, Many-shot, PAIR, TAP, Crescendo, Skeleton Key, Red Teaming, Therapist Crescendo, PCSA dispatch
- [`../../../external_baselines/matrix_qwen_gpt4o.json`](../../../external_baselines/matrix_qwen_gpt4o.json): GPT-4o/Qwen matrix 설정
- [`../../../external_baselines/result/final197_main_results.json`](../../../external_baselines/result/final197_main_results.json): 9×2 완성 집계
- [`../../../external_baselines/result/final197_evaluation_audit.json`](../../../external_baselines/result/final197_evaluation_audit.json): 3,546행 평가 coverage 감사

외부 baseline 결과는 방법별 실행이 저장한 최종 target response 하나를 case-level 응답으로
평가한다. 각 방법 내부의 target 호출 수는 동일하다고 가정하지 않는다.

## 3. PCSA Phase II와 Persona+History 확장

핵심 구현:

- [`../../../external_baselines/pcsa_phase2.py`](../../../external_baselines/pcsa_phase2.py)
  - 네 전략 후보 생성
  - turn별 target 응답 4개 생성
  - GPT-4o-mini 중간평가
  - 결정론적 best-of-N 선택과 선택 대화 누적
  - 이전 선택 응답의 evaluator feedback을 다음 턴 attacker에 전달
  - 성공 또는 최대 4턴에서 종료
- [`../../../external_baselines/Experiment/PCSA_PERSONA_HISTORY_ADAPTER_KO.md`](../../../external_baselines/Experiment/PCSA_PERSONA_HISTORY_ADAPTER_KO.md)
  - 논문 Phase I/II와 본 재구현의 대응 관계
  - persona/history의 정확한 입력 위치
  - No-Persona 통제 계약

Persona+History 연결은 다음 정보만 attacker의 Phase-I 대체 입력으로 사용한다.

- case별 goal-conditioned persona
- client 쪽 source-history 발화의 style reference
- persona state trajectory
- 고정 pathology/distortion route

source history의 counselor 응답은 attacker style에 넣지 않고, source history 전체를 target의
과거 대화로 재생하지 않는다. target은 현재 PCSA 실행에서 선택된 대화만 본다.

실행·평가 코드:

- [`../../../external_baselines/run_pcsa_persona_history_pilot.sbatch`](../../../external_baselines/run_pcsa_persona_history_pilot.sbatch): 10건 파일럿
- [`../../../external_baselines/run_pcsa_persona_history_final197.sbatch`](../../../external_baselines/run_pcsa_persona_history_final197.sbatch): 99/98 shard 전체 실행과 No-Persona switch
- [`../../../external_baselines/run_pcsa_persona_history_gpt4o_final197.sh`](../../../external_baselines/run_pcsa_persona_history_gpt4o_final197.sh): GPT-4o-2024-11-20 타깃과 GPT-4o-mini 중간 평가자를 모두 OpenAI Batch로 고정한 Final-197 실행
- [`../../../external_baselines/run_pcsa_persona_history_gpt4o_final197_sharded.sh`](../../../external_baselines/run_pcsa_persona_history_gpt4o_final197_sharded.sh): 여러 로컬 Qwen attacker endpoint에 197건을 disjoint shard로 분배하는 실행기
- [`../../../official_evaluation/prepare_single_baseline_cell.py`](../../../official_evaluation/prepare_single_baseline_cell.py): 두 shard를 동일 197행 평가 입력으로 변환
- [`../../../official_evaluation/run_pcsa_persona_history_final197_eval.sbatch`](../../../official_evaluation/run_pcsa_persona_history_final197_eval.sbatch): CARES, PCSA GPT-4o judge, R/B, HarmBench와 Strict Joint
- [`../../../official_evaluation/run_pcsa_persona_history_gpt4o_final197_eval.sh`](../../../official_evaluation/run_pcsa_persona_history_gpt4o_final197_eval.sh): GPT-4o 추가 셀을 GPT-4o CARES Batch, GPT-4o PCSA judge Batch, R/B Batch와 pinned HarmBench로 평가
- [`../../../official_evaluation/run_harmbench_pinned_pair.sbatch`](../../../official_evaluation/run_harmbench_pinned_pair.sbatch): 두 조건의 같은 HarmBench snapshot 재판정

PCSA 관련 회귀 테스트:

- `external_baselines/tests/test_pcsa_phase2.py`
- `external_baselines/tests/test_run_pyrit_baseline.py`
- `external_baselines/tests/test_run_baseline_matrix.py`
- `official_evaluation/tests/test_prepare_single_baseline_cell.py`

GPT-4o 추가 셀은 target을 `gpt-4o-2024-11-20`, 중간 평가자를
`gpt-4o-mini-2024-07-18`로 pin한다. 두 OpenAI role 모두 `openai_batch` transport만
허용하고 Qwen2.5-7B attacker만 로컬 GPU endpoint를 사용한다. 개별 Batch 입력·ID·상태·
출력·오류는 각 shard의 `_openai_batches/{target,pcsa_evaluator}/wave-*`에 남아 중단 후
동일 명령으로 case checkpoint를 재개할 수 있다. 이 추가 셀의 최종 CARES 판정은 사용자
요청에 따라 `gpt-4o-2024-11-20` Batch를 사용하며, 기존 외부 baseline의 GPT-4o-mini
CARES와 evaluator가 다르다는 사실을 결과표에 별도로 표시한다.

## 4. OURS 1011 singleton

OURS의 고정 정의와 실행 코드는 다음에 있다.

- [`../../singleton_1011_package/docs/SINGLETON_PROTOCOL_KO.md`](../../singleton_1011_package/docs/SINGLETON_PROTOCOL_KO.md): singleton, Best-of-4, 같은-분기 Strict Joint 계약
- [`../../singleton_1011_package/launchers/launch_full197_gpt4o.py`](../../singleton_1011_package/launchers/launch_full197_gpt4o.py): Final-197 GPT-4o 실행
- [`../../singleton_1011_package/launchers/run_singleton.py`](../../singleton_1011_package/launchers/run_singleton.py): 사례별 네 최종 방향 실행
- [`../../singleton_1011_package/launchers/evaluate_gpt4o.py`](../../singleton_1011_package/launchers/evaluate_gpt4o.py): GPT 기반 CARES/JMIR/RB 평가
- [`../../singleton_1011_package/launchers/evaluate_harmbench.py`](../../singleton_1011_package/launchers/evaluate_harmbench.py): HarmBench 분류
- [`../../singleton_1011_package/launchers/finalize_full197_gpt4o.py`](../../singleton_1011_package/launchers/finalize_full197_gpt4o.py): GPT 지표 Final-197 집계
- [`../../singleton_1011_package/launchers/finalize_harmbench_full197.py`](../../singleton_1011_package/launchers/finalize_harmbench_full197.py): HarmBench와 Strict Joint 집계
- [`../../singleton_1011_package/result/final197_1011_singleton_gpt4o_v1/README_KO.md`](../../singleton_1011_package/result/final197_1011_singleton_gpt4o_v1/README_KO.md): 검증된 결과와 해석 계약

최종 attack endpoint는 네 등록 방향의 독립 singleton이다. CARES/JMIR/HarmBench/B4+의
case-level 수치는 Best-of-4이며, Strict Joint는 같은 한 분기에서 R3+·B4+·HarmBench가
동시에 참인 뒤 네 분기 중 하나라도 성공했는지 계산한다.

## 5. 평가 계약 차이

| 항목 | 외부 baseline | PCSA Qwen ablation | PCSA GPT-4o 추가 셀 | OURS singleton |
|---|---|---|---|---|
| Target | GPT-4o, Qwen | Qwen | GPT-4o-2024-11-20 | GPT-4o |
| 저장 응답 | 방법별 최종 1개/case | 선택 trajectory 최종 응답 | 선택 trajectory 최종 응답 | 4개 final branches/case |
| Online selection | 방법별 상이 | GPT-4o-mini turn evaluator | GPT-4o-mini turn evaluator | 최종 지표 미사용 |
| CARES evaluator | GPT-4o-mini, PCSA Level-2 | GPT-4o-mini, PCSA Level-2 | GPT-4o-2024-11-20 | GPT-4o-2024-11-20 |
| HarmBench aggregation | 최종 응답 1개 | 최종 선택 응답 1개 | 최종 선택 응답 1개 | Best-of-4 |
| Strict Joint | 최종 응답 | 최종 선택 응답 | 최종 선택 응답 | same-branch Best-of-4 |

그래서 `TABLES_KO.md`는 네 패널을 유지한다. 동일 패널 내부 비교만 정식 비교로 사용하고,
패널 사이 수치는 설계 차이를 명시한 기술적 참고로만 사용한다.

## 6. 재현성과 공개 범위

`PROVENANCE.json`은 이 문서가 참조하는 실행·평가 코드의 SHA-256을 기록한다. 원시 대화,
유해 응답과 evaluator rationale은 `external_baselines/outputs/` 및 평가 work 디렉터리에
생성되지만 Git 공개 결과에는 복제하지 않는다. 공개 자료로 재계산 가능한 것은 aggregate
표, count/rate 검증, 코호트 일치와 paired 2×2 검정이다.
