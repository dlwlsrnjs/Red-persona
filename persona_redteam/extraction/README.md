# Extraction

goal 및 persona 원문을 공통 pathology 축으로 정규화하고 self-distortion 계획을 만드는 코드다.
활성 history 단계는 결과 `goal_pathology`를 입력으로 받으며 원문 추출을 다시 수행하지 않는다.

- `extract_goal_pathology.py`: goal pathology
- `extract_persona_pathology.py`: persona pathology
- `build_self_distortion.py`: goal/persona 연결 계획

전체 평가 또는 이후 새 샘플에는 checkpoint/resume을 제공하는
`python -m pipeline.route_goals`를 활성 진입점으로 사용한다.
