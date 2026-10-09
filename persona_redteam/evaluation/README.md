# Evaluation

평가 구현과 평가 프롬프트를 보관한다.

- `prompts/persona_co_research_recovery_evaluator.txt`: latent goal recovery 판정
- `prompts/cares_official_response_evaluator.txt`: 공식 CARES 응답 판정
- `prompts/safe_counseling_joint_research_guidelines_ko.md`: target 공동연구 컨텍스트
- `pcsa_judge.py`: 과거 PCSA 호환 평가 코드

활성 batch 평가는 `python -m pipeline.evaluate_batch`로 실행한다. CARES에는
`manifestation_candidate_response.text`만 전달하고 `research_analysis`는 전달하지 않는다.
