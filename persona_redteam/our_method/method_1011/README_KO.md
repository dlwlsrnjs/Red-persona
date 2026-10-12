# 1011 Method v1

이 디렉터리는 최종 메서드의 단계 연결 계약을 정의한다. 모델 호출·체크포인트·병렬 실행은
기존 production runner가 담당하고, 이 모듈은 7단계 이후 조건부 Case A/B 복구와 전체
아티팩트 검증을 담당한다.

```text
페르소나 + 사전 대화 이력
  -> 7단계 누적 연구 대화
  -> cumulative coverage + latest-target exact-span GOAL gate
  -> 실패한 case/condition만 Case A/B 비교 질문 1회
  -> 동일 누적 문맥에서 4개 독립 최종 분기
  -> 각 분기의 recovery_response 안에서 정확한 연속 인용 선택
  -> 해당 분기의 recovery_context + recovery_response + 인용 기반 질문
  -> attack_response 측정
```

## 코드 지도

- `case_ab_recovery.py`: 조건부 Case A/B wave의 준비·적용·사후 GOAL 검사
- `validate.py`: 7단계 순서, 조건부 복구, 4분기, 분기별 인용 및 최종 문맥 연속성 검사
- `test_case_ab_recovery.py`: 성공 시 skip, 실패 시 recovery, false-success 방지 테스트
- `../run_1011_method.py`: production runner 진입점
- `adaptive_attack.py`: 세 공격 턴 조건, 네 후속 전략, 의미보존 추상화·온라인 선택 계약
- `../run_attack_turn_ablation.py`: 완료된 1011 결과를 재사용하는 세 조건 실행 진입점

기존 핵심 구현은 다음 모듈을 단일 원본으로 재사용한다.

- 7단계·GOAL 검사·질문·인용: `experiments/qwen_target_persona_research_dialogue.py`
- Batch wave·체크포인트·4분기·최종 측정: `experiments/run_jmir_persona_batch_api.py`
- 실행 결과 계약: `pipeline/contracts.py`

## 고정 불변식

1. 정규 연구 대화는 항상 등록된 7단계를 순서대로 완료한다.
2. Case A/B는 두 GOAL 조건 중 하나라도 부족할 때만 실행한다.
   - 누적 연구 대화에 필요한 GOAL 정보가 충분한가?
   - 마지막 타깃 응답 자체에서 완전한 정확 인용 범위를 선택할 수 있는가?
3. Case A/B는 한 번만 실행한다. 실패를 성공으로 바꾸지 않고
   `case_ab_recovery_completed_goal_still_incomplete`로 기록한다.
4. 네 분기는 공통 누적 대화까지만 공유한다.
5. 인용문은 반드시 현재 분기의 `recovery_response`에 존재하는 연속 부분 문자열이다.
6. 최종 측정 문맥은 정확히 아래 순서를 유지한다.

```text
recovery_context.full_messages
  + assistant(recovery_response.text)
  + user(attack_question containing the selected quote)
```

7. 한 분기의 응답·인용·측정 문맥을 다른 분기에 재사용하지 않는다.
8. 원문 GOAL의 정확한 문장은 기본군 타깃에 전달하지 않는다. Case A에는 사전 감사된
   의미상 유사 가설만 비작동적으로 전달한다. 원문 명시군은 등록된 ablation이다.

## 입력

1011 실행에는 `similar_goal_question_pool`이 포함된 197개 파일이 필요하다.

```text
data/final_cares_strict_harmful/persona197_v1/
  contrastive_goal_question_pool_gpt4o_v5_fixed_comparison/
```

세 조건은 동일한 Case A/B 풀을 공유하며 페르소나 GOAL 노출과 사전 이력만 다르다.

## 실행

한 실행 cell은 다음 진입점을 사용한다.

```bash
python3 -m our_method.run_1011_method \
  --cases <1011-input.json> \
  --selection-path <selection.json> \
  --target-total 197 \
  --condition neutral \
  --campaign-dir <checkpoint-dir> \
  --output-dir <result-dir> \
  --target-model gpt-4o-2024-11-20 \
  --researcher-base-url http://127.0.0.1:8000/v1 \
  --researcher-model Qwen/Qwen2.5-7B-Instruct \
  --api-mode batch \
  --final-readout-protocol safety_negative_examples_v1 \
  --direct-response-prompt-protocol counterfactual_prevention_v1 \
  --research-language-profile clinical_safety_terminology_v1 \
  --require-strict-harmful-goal-v3
```

전체 GPT-4o/Qwen × 3조건 행렬은 기존 진입점이 1011 옵션을 자동 전달한다.

```bash
python3 -m our_method.run_full197_matrix --prepare-only
python3 -m our_method.run_full197_matrix --wait
```

Qwen 타깃에서는 연구자가 자동으로 Llama-3.1-8B-Instruct로 분리된다.

## 검증

```bash
pytest -q our_method/method_1011/test_case_ab_recovery.py \
  experiments/test_pipeline_contracts.py \
  experiments/test_qwen_target_persona_research_dialogue.py \
  experiments/final197/test_full197_experiment_matrix.py
```

결과 파일은 `validate_1011_run_record()`로 검사한다. 일반 계약 검사에 더해 Case A/B의
조건부 실행 여부, 분기별 인용의 출처와 방향, 최종 측정 문맥의 연속성을 확인한다.

## 최종 공격 턴 세 조건

완료된 네 분기를 다시 생성하지 않고 singleton, 일반 적응형 multi-turn, GOAL 귀속형
multi-turn을 쌍체 비교한다. 실행·중단·평가 규칙은
[`../ATTACK_TURN_ABLATION_KO.md`](../ATTACK_TURN_ABLATION_KO.md)에 정리되어 있다.
