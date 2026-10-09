# Evaluation

활성 평가 프롬프트를 보관한다.

- `prompts/persona_co_research_recovery_evaluator.txt`: latent goal Recovery/Behavior 판정
- `prompts/cares_official_response_evaluator.txt`: CARES 응답 판정
- `prompts/research_prompt_banks_en.json`: 영어 Qwen 연구·4분기 질문 bank
- `prompts/safe_counseling_joint_research_guidelines.md`: target 최초 공동연구 packet

평가는 `python -m pipeline.evaluate_batch`로 실행한다. CARES에는 target이 생성한
`manifestation_candidate_response.text`만 전달하며 `research_analysis`는 전달하지 않는다.
