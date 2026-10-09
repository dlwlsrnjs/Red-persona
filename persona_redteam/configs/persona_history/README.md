# Persona history 프롬프트

이 폴더는 모델 프롬프트와 코드의 경계다. 코드는 `pipeline/persona_history.py`, 실행기는
`pipeline/generate_histories.py`에 있으며 이 폴더에는 사용자가 편집하는 프롬프트만 둔다.

- `generation_prompt.template.txt`: Lexi가 과거 대화 한 턴과 persona state를 생성
- `coverage_prompt.template.txt`: 최소 4턴 이후 정보 충분성을 판정

템플릿은 `$goal_json`, `$goal_pathology_json`, `$persona_profile_json`, `$history_json`,
`$current_persona_state_json`, `$current_micro_plan_json`, `$stage`, `$turn_index`, `$min_turns`,
`$max_turns`를 사용할 수 있다. 실제 모델에 전달되는 두 template의 본문과 생성 데이터는
영어를 사용한다. 원본 template을 직접 덮어쓰기보다
별도 `prompts/` 파일로 복사해 실행 인자로 전달한다.

상세 계약과 예시는 `docs/PERSONA_HISTORY_PROMPT_HOOKS_KO.md`에 있다.
