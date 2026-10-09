# Persona history 프롬프트 연결 규격

프롬프트 본문은 파이썬 코드에 넣지 않는다. 아래 template을 복사해 별도 파일에서 수정한다.

- `configs/persona_history/generation_prompt.template.txt`
- `configs/persona_history/coverage_prompt.template.txt`

## 생성 프롬프트

사용 가능한 치환 변수는 `$goal_json`, `$goal_pathology_json`,
`$persona_profile_json`, `$history_json`, `$current_persona_state_json`,
`$current_micro_plan_json`, `$stage`, `$turn_index`, `$min_turns`, `$max_turns`다.
리터럴 `$`는 `$$`로 쓴다.

`--plans`로 Qwen 계획 JSON을 지정하면 샘플의 `micro_plans`가 턴 순서대로 연결된다.
`$current_persona_state_json`은 첫 턴에는 `{}`, 이후에는 직전 턴의 누적 상태다.
`$current_micro_plan_json`과 `$stage`는 현재 턴 계획을 가리킨다. 외부 계획 파일이 없으면
활성 생성기가 Qwen으로 최대 turn 수 전체의 계획을 동적으로 만든다. 계획보다 생성 턴이 더
많은 비활성/직접 API 사용에서는 마지막 계획을 유지하며, 계획 자체가 없으면 각각 `{}`와
`unplanned`를 쓴다.

모델 출력 계약은 다음 JSON 객체다.

```json
{
  "user": "The client's utterance in this prior exchange.",
  "assistant": "The counselor's response at that time.",
  "persona_state": {"summary": "The state accumulated through this turn."}
}
```

`persona_state`는 델타가 아니라 지금까지 누적된 전체 상태여야 한다. 마지막 턴의 값이 이후
Qwen–타겟 실험에서 활성 `persona`가 된다. 각 턴의 세 필드가 없거나 비어 있으면 실행을
실패 처리한다.

## Qwen coverage 프롬프트

동일한 변수를 사용할 수 있다. 활성 CLI는 이 프롬프트를 goal-aware Qwen에 전달한다.
최소 턴 전에는 호출하지 않으며, 최소 턴 이후 매 턴 호출한다.
출력 계약은 다음과 같다.

```json
{
  "sufficient": false,
  "missing": ["An information dimension that is still missing."],
  "reason": "Brief evidence-based judgment."
}
```

`sufficient=true`이면 해당 샘플의 이력 생성이 종료된다. 계속 false이면 `--max-turns`에서
종료되고 `stop_reason=max_turns_reached`가 기록된다.

## 실행 순서

먼저 최신 adapter를 다시 실행해 각 case provenance에 `goal_pathology`를 포함시킨다.

```bash
python3 -m pipeline.prepare adapt \
  --input data/prepared/blueprints/jmir_eval_full.jsonl \
  --output data/prepared/cases/jmir_eval_full_pre_generation.json
```

그 다음 사용자가 작성한 두 프롬프트를 지정한다.

```bash
python3 -m pipeline.generate_histories \
  --cases data/prepared/cases/jmir_eval_full_pre_generation.json \
  --profiles data/source/personas/personas.jsonl \
  --generation-prompt prompts/persona_history_generation.txt \
  --coverage-prompt prompts/persona_history_coverage.txt \
  --plans data/prepared/plans/jmir_eval_full_qwen_plans.json \
  --model Orenguteng/Llama-3.1-8B-Lexi-Uncensored-V2 \
  --base-url http://127.0.0.1:8002/v1 \
  --qwen-model Qwen/Qwen2.5-7B-Instruct \
  --qwen-base-url http://127.0.0.1:8000/v1 \
  --min-turns 4 --max-turns 8 \
  --checkpoint-dir data/prepared/generated/jmir_eval_full_checkpoints \
  --output data/prepared/generated/jmir_eval_full_with_history.json
```

이 출력 파일을 `pipeline.run_batch --cases`에 전달하면 전체 과거 대화가 최초 타겟
컨텍스트에 포함된다.
