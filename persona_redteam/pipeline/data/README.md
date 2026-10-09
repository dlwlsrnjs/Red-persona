# 데이터 배치

추적 가능한 평가 프롬프트와 로컬 전체 입력의 실제 위치는 `manifest.json`이 한 곳에서 관리한다.
원본·개인 데이터와 대용량 실행 결과는 Git에 넣지 않고 `persona_redteam/data/` 아래의 다음
단계별 디렉터리에 둔다.

- `data/source/goals/`: 원본 goal 및 pathology 추출 입력
- `data/source/personas/`: persona 원문 및 정규화 profile
- `data/prepared/matched/`: goal–persona 매칭 결과
- `data/prepared/generated/`: 동적 persona 선택 및 가변 길이 과거 대화 이력
- `data/prepared/cases/`: 활성 Qwen–타겟 입력 JSON
- `data/runs/<target_model>/`: 사례별 타겟 실행 결과
- `data/evaluations/<target_model>/`: 사례별 평가 및 집계

평가 프롬프트를 중복 복사하지 않는다. `manifest.json`을 단일 데이터
인덱스로 사용해 provenance와 실제 경로를 함께 확인한다.
