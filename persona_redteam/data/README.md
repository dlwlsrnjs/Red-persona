# 로컬 실험 데이터

이 디렉터리는 활성 파이프라인의 비추적 원본과 산출물을 한 곳에 둔다.

```text
data/
  source/goals/
  source/personas/
  prepared/matched/
  prepared/generated/
  prepared/cases/
  runs/<target_model>/
  evaluations/<target_model>/
```

전체 persona pool은 중복 복사하지 않고 다음 원본을 참조한다.

`/home/jklee/Documents/Codex/2026-09-30-new-chat/derived/full_dataset/personas.jsonl`

이 파일은 31,733개 profile을 포함한다. `data/prepared/matched/validated_persona_profiles_24.jsonl`
은 과거 복구 provenance이며 새 실행 기본 pool이 아니다.

Git에 포함된 고정 fixture와 평가 프롬프트까지 포함한 전체 데이터 인덱스는
`pipeline/data/manifest.json`을 기준으로 한다. 원본 goal/persona와 모델 응답에는 민감한
내용이 포함될 수 있으므로 이 README를 제외한 `data/` 내용은 Git에서 추적하지 않는다.
