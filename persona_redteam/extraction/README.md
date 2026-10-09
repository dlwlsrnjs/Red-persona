# Extraction

- `extract_goal_pathology.py`: goal을 공통 pathology schema로 정규화하는 구현
- `python -m pipeline.route_goals`: 625개 및 새 샘플의 checkpoint/resume 가능한 활성 진입점

고정 persona 후보나 self-distortion 계획은 생성하지 않는다. route에는 goal pathology와
동적 전체-pool 검색 정책만 기록하고, persona 선택은 history 생성 시점에 수행한다.
