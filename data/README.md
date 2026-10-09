# Canonical experiment inputs

GitHub clone에는 원본 평가 입력, persona pool, API 검증을 끝낸 category sidecar가 포함된다.
생성 checkpoint와 나머지 실행 산출물은 포함하지 않는다.

데이터 계보는 JMIR *Between Help and Harm* 공개 test 입력 2,046개에서 시작한다. 6개 위기
범주 813개, 1인칭 client 발화 652개, 최소 10단어 goal 625개로 순차 정제한 뒤 pathology,
persona, Lexi prior history를 결합했다. 공식 500개는 이 종합 후보군 안에서 다시 고른
부분집합이며, 별도로 새 goal을 생성하거나 외부 샘플을 섞은 데이터가 아니다.

- `crisis_goals_jmir_persona_min10.jsonl`: JMIR 평가 goals 625개
- `goal_pathology_routes_n625.jsonl`: 동일 625개 goal의 pathology route
- `red_persona_official_500.jsonl`: 논문과 후속 실험에서 사용하는 **공식 500개 cohort index**.
  각 행에는 `case_id`, crisis category, 원본 625 내 위치, 기존 완료/추가 선택 역할만 있고
  private goal이나 persona 본문은 없다.
- `red_persona_official_500.audit.json`: 625→608→500 정제 수, 제외·보류 ID, 범주 분포,
  선택법과 SHA-256을 기록한 공식 감사 파일. 유효 608개 중 과대표집된
  `suicidal_ideation`에서만 108개를 줄여 500개로 고정했다.
- `OFFICIAL_500_COHORT_KO.md`: 공식 500의 선택 이유, 사용법, 논문 보고 문구
- `personas/personas.jsonl`: 동적 검색에 사용하는 전체 persona pool 31,733개
- `personas/persona_category_labels.jsonl`: Qwen 전체-pool 라벨을 기반으로,
  희소 범주는 GPT-4o mini의 근거 재심사와 명시적 category adaptation으로 보강한 단일 평가
  카테고리, 적합도, 위해 방향, 근거. `persona_id`로 원본 pool에 자동 병합한다.
- `personas/persona_category_labels.audit.json`: 보강된 268건에 대한 항목별 GPT-4o mini
  독립 감사 요약. 범주·위해 방향·신원 연속성·provenance·비그래픽성을 각각 검증한다.
- `personas/by_category/`: 최종 sidecar를 여섯 범주별로 분리한 결정적 JSONL view와
  행 수·분포·체크섬을 담은 `index.json`. 전체 원문 profile은 `persona_id`로 원본 pool에 join한다.

파이프라인은 저장소 루트를 기준으로 이 경로들을 기본값으로 사용한다. 새로운 환경에서
별도 경로 설정 없이 동작하며, 외부 pool을 실험할 때만 `PERSONA_POOL_PATH`를 지정한다.
외부 category sidecar는 `PERSONA_CATEGORY_LABELS_PATH`로 지정한다. 라벨 생성 checkpoint와
partial 파일은 Git에 포함하지 않는다. 최종 sidecar가 전체 31,733개 ID를 정확히 한 번씩
포함하지 않으면 history 생성 단계가 시작되지 않는다. 현재 최종 sidecar SHA-256은
`7fa62560f5c99dc1d05b7aacac17f63a92ad19f13ac1e3fda13aa5a033edf9f0`이다.

파일별 checksum과 lineage는 `persona_redteam/DATA_MANIFEST.json` 및
`persona_redteam/docs/DATA_LINEAGE_AND_EXTRACTION_KO.md`를 따른다.
논문용 영어 추출·생성 방법 문단은
`persona_redteam/docs/PERSONA_CATEGORY_EXTRACTION_AND_GENERATION.md`에 있다.

공식 분석에서 별도 목록을 임의로 만들지 말고 반드시 `red_persona_official_500.jsonl`의
`case_id`와 join한다. 전체 생성 case 본문과 API 결과는 용량·민감성 때문에 Git에 포함하지
않으며, 이 index가 공식 membership의 단일 기준이다.
