# 로컬 실험 데이터

이 디렉터리는 활성 파이프라인의 비추적 원본과 산출물을 한 곳에 둔다.
본 평가는 100개 fixture가 아니라 저장소 루트 `data/crisis_goals_jmir_persona_min10.jsonl`의
전체 625개를 사용한다. `experiments/build_jmir_eval_set_full.py`가 이 파일과
저장소 루트 `data/goal_pathology_routes_n625.jsonl`을 합쳐 무표본 full blueprint를 만든다.
원출처, 2,046→813→652→625 필터, 범주별 개수와 checksum은
`docs/DATA_LINEAGE_AND_EXTRACTION_KO.md`에 기록한다.

```text
data/
  source/goals/
  source/personas/
  prepared/matched/
  prepared/blueprints/jmir_eval_full.jsonl
  prepared/cases/jmir_eval_full_pre_generation.json
  prepared/generated/
  prepared/cases/
  runs/<target_model>/
  evaluations/<target_model>/
```

전체 persona pool은 중복 복사하지 않고 다음 원본을 참조한다.

`data/source/personas/personas.jsonl` 또는 `$PERSONA_POOL_PATH`

이 파일은 31,733개 profile을 포함한다. `data/prepared/matched/validated_persona_profiles_24.jsonl`
은 과거 복구 provenance이며 새 실행 기본 pool이 아니다.
Git에 포함된 평가 프롬프트와 로컬 전체 데이터 경로를 포함한 데이터 인덱스는
`pipeline/data/manifest.json`을 기준으로 한다. 원본 goal/persona와 모델 응답에는 민감한
내용이 포함될 수 있으므로 이 README를 제외한 `data/` 내용은 Git에서 추적하지 않는다.
