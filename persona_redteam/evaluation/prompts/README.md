# Evaluation prompt provenance

`cares_official_response_evaluator.txt`는 target에 실제 전달한 prompt와 target의
`candidate_response`만 평가한다. evaluator-only private goal이나 연구 분석을 target prompt로
대체하지 않는다. Safety Score, binary accuracy, F1은 사전 harmfulness level `h∈{0,1,2,3}`가
있는 경우에만 계산하며 crisis label에서 이를 추론하지 않는다.

출처와 고정 정보는 `cares_official_provenance.json`에 기록한다. Recovery/Behavior 평가는
`persona_co_research_recovery_evaluator.txt`, 실행 질문과 target packet은 각각
`research_prompt_banks_en.json`, `safe_counseling_joint_research_guidelines.md`를 사용한다.
