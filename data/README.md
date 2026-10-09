# Canonical experiment inputs

GitHub clone에는 원본 평가 입력과 persona pool이 포함된다. 모델이 생성하는 category sidecar와
실행 산출물은 포함하지 않으며, 아래 명령으로 별도 생성해야 한다.

- `crisis_goals_jmir_persona_min10.jsonl`: JMIR 평가 goals 625개
- `goal_pathology_routes_n625.jsonl`: 동일 625개 goal의 pathology route
- `personas/personas.jsonl`: 동적 검색에 사용하는 전체 persona pool 31,733개
- `personas/persona_category_labels.jsonl`(생성 필요): 각 persona에 Qwen이 부여한 단일 평가
  카테고리, 적합도, 위해 방향, 근거. `persona_id`로 원본 pool에 자동 병합한다.

파이프라인은 저장소 루트를 기준으로 이 경로들을 기본값으로 사용한다. 새로운 환경에서
별도 경로 설정 없이 동작하며, 외부 pool을 실험할 때만 `PERSONA_POOL_PATH`를 지정한다.
외부 category sidecar는 `PERSONA_CATEGORY_LABELS_PATH`로 지정한다. category sidecar와 라벨 생성
checkpoint는 모델 생성 산출물이므로 Git에 포함하지 않는다. 전체 31,733개 ID를 정확히 한 번씩
포함하지 않으면 history 생성 단계가 시작되지 않는다.

파일별 checksum과 lineage는 `persona_redteam/DATA_MANIFEST.json` 및
`persona_redteam/docs/DATA_LINEAGE_AND_EXTRACTION_KO.md`를 따른다.
