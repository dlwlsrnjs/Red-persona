# Canonical experiment inputs

GitHub clone에 포함되는 활성 입력은 모두 이 디렉터리에 있다.

- `crisis_goals_jmir_persona_min10.jsonl`: JMIR 평가 goals 625개
- `goal_pathology_routes_n625.jsonl`: 동일 625개 goal의 pathology route
- `personas/personas.jsonl`: 동적 검색에 사용하는 전체 persona pool 31,733개

파이프라인은 저장소 루트를 기준으로 이 경로들을 기본값으로 사용한다. 새로운 환경에서
별도 경로 설정 없이 동작하며, 외부 pool을 실험할 때만 `PERSONA_POOL_PATH`를 지정한다.

파일별 checksum과 lineage는 `persona_redteam/DATA_MANIFEST.json` 및
`persona_redteam/docs/DATA_LINEAGE_AND_EXTRACTION_KO.md`를 따른다.
