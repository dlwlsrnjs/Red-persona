# 싱글턴 파이프라인 파트 구성

## 1. 입력과 실험 셀 고정

`src/experiments/final197/prepare_abstract_goal_persona_arm.py`와
`prepare_full197_experiment_matrix.py`가 197개 사례와 세 context arm을
검증한다. 세 arm은 동일 사례 순서를 유지한다.

## 2. 1011 방법

`src/our_method/run_1011_method.py`가 유일한 방법 진입점이다. 이 파일은
`method_protocol=1011_method_v1`과 `max_goal_convergence_turns=0`을 강제한다.
조건부 Case A/B 복구는 `src/our_method/method_1011/`에 있다.

## 3. 생성 코어

`src/experiments/run_jmir_persona_batch_api.py`가 실행을 조정하고,
`qwen_target_persona_research_dialogue.py`가 연구 대화와 최종 4개 분기를
구성한다. `src/pipeline/`은 계약, Batch API, 로컬 채팅, 이력과 산출물 I/O를
담는다.

## 4. 전체 실험 실행

`launchers/launch_full197_qwen.py`는 실제 23건 성능 검증과 같은
Qwen-target/Llama-researcher 프로필을 197건 세 arm으로 확장한다.
`launchers/launch_full197_gpt4o.py`는 GPT-4o-target/Qwen-researcher 프로필이다.
두 실행기 모두 사례당 네 분기의 싱글턴 계약과 추가 턴 0을 공유한다.

## 5. CARES/JMIR 평가

`launchers/evaluate_gpt4o.py`는
`evaluate_final_cares_pilot64.py`를 호출하되 evaluator를
`gpt-4o-2024-11-20`으로 고정한다. CARES는 응답 태도
(Accept/Caution/Refuse), JMIR은 유해 응답 수준을 평가한다.

## 6. HarmBench 평가

`launchers/evaluate_harmbench.py`는 `result.private_goal`을 behavior로,
`branch.attack_response.text`를 generation으로 공식 HarmBench 분류기에
전달한다. 각 사례 네 분기 중 하나라도 positive이면 Best-of-4 성공이다.

## 7. 재현성 경계

`src/`는 원본 코드의 바이트 동일 복사본이고 수정하지 않는다. 새 실행 편의
기능은 `launchers/`와 `tools/`에만 둔다. `tools/verify_snapshot.py`가 복사본,
기준 커밋, 평가 결과 해시와 멀티턴 파일 미포함 계약을 확인한다.
