# RED-Persona

현재 저장소에는 JMIR 625개 평가를 위한 seedless Qwen–Lexi–target 파이프라인만 유지한다.

- 프로젝트 설명: [`persona_redteam/README.md`](persona_redteam/README.md)
- 전체 흐름: [`persona_redteam/PIPELINE_OVERVIEW_KO.md`](persona_redteam/PIPELINE_OVERVIEW_KO.md)
- 실행 절차: [`persona_redteam/docs/JMIR_FULL_EXPERIMENT_RUNBOOK_KO.md`](persona_redteam/docs/JMIR_FULL_EXPERIMENT_RUNBOOK_KO.md)
- 새 서버 설치: [`persona_redteam/docs/NEW_SERVER_SETUP_AND_EXPERIMENT_GUIDE_KO.md`](persona_redteam/docs/NEW_SERVER_SETUP_AND_EXPERIMENT_GUIDE_KO.md)
- 데이터 lineage: [`persona_redteam/docs/DATA_LINEAGE_AND_EXTRACTION_KO.md`](persona_redteam/docs/DATA_LINEAGE_AND_EXTRACTION_KO.md)

활성 평가 입력은 `data/crisis_goals_jmir_persona_min10.jsonl`과
`data/goal_pathology_routes_n625.jsonl`이다. persona는 각 샘플마다 전체 pool에서 동적으로
검색하고 Qwen으로 rerank한다.

API 키와 모델·실행 산출물은 Git에 포함하지 않는다.
