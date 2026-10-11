# Final-197 baseline assets

이 디렉터리는 최종 197개 요청을 9개 외부 기법과 2개 target에서 동일하게 실행하기
위한 고정 자산이다. 원 요청 데이터의 칼럼 정의는
`persona_redteam/data/research_harmful_requests/DATA_DICTIONARY_KO.md`를 따른다.

| 파일 | 행 수 | 역할 |
|---|---:|---|
| `final197_goals.jsonl` | 197 | 원 요청, 출처, 위해 수준, 위기 범주를 포함한 실행 입력 |
| `final197_cohort.jsonl` | 197 | 전체 평가 순서와 `case_id` 고정 |
| `final197_reuse43_cohort.jsonl` | 43 | 요청·persona·pathology가 기존 실행과 일치하는 재사용 사례 |
| `final197_remaining154_cohort.jsonl` | 154 | 새 target 생성을 수행할 사례 |
| `final197_persona_assignments.jsonl` | 197 | 사례별 고정 persona ID; 전체가 서로 다름 |
| `final197_pathology_routes.jsonl` | 197 | PCSA Phase 2에만 사용하는 고정 구조화 컨텍스트 |
| `reuse43_mapping.json` | 43 | 재사용 사례의 최종 ID와 원 체크포인트 ID 대응 |
| `manifest.json` | 1 | 입력·persona 풀 해시, 분포, 재사용 계약 |

재사용 43개는 원래 persona profile과 `pathology` 객체까지 보존한다. 나머지 154개는
요청 메타데이터만으로 보수적인 pathology route를 만들며 진단·의도·계획을 추론하지
않는다. Persona는 31,733개 풀에서 결정적으로 배정하고 중복을 허용하지 않는다.

`harm_level` H1/H2는 입력 파일에서 보존한 기존 수준이다. target 응답의 유해성,
HarmBench 결과, CARES 응답 범주와 같은 의미가 아니다.
