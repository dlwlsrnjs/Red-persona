# RED-Persona

현재 저장소에는 JMIR 기반 공식 500개 평가를 위한 seedless Qwen–Lexi–target 파이프라인과
동일한 500개에 적용하는 single-turn/multi-turn jailbreak baseline을 유지한다.

- 프로젝트 설명: [`persona_redteam/README.md`](persona_redteam/README.md)
- 전체 흐름: [`persona_redteam/PIPELINE_OVERVIEW_KO.md`](persona_redteam/PIPELINE_OVERVIEW_KO.md)
- 실행 절차: [`persona_redteam/docs/JMIR_FULL_EXPERIMENT_RUNBOOK_KO.md`](persona_redteam/docs/JMIR_FULL_EXPERIMENT_RUNBOOK_KO.md)
- 새 서버 설치: [`persona_redteam/docs/NEW_SERVER_SETUP_AND_EXPERIMENT_GUIDE_KO.md`](persona_redteam/docs/NEW_SERVER_SETUP_AND_EXPERIMENT_GUIDE_KO.md)
- 데이터 lineage: [`persona_redteam/docs/DATA_LINEAGE_AND_EXTRACTION_KO.md`](persona_redteam/docs/DATA_LINEAGE_AND_EXTRACTION_KO.md)
- 공식 500개 cohort: [`data/OFFICIAL_500_COHORT_KO.md`](data/OFFICIAL_500_COHORT_KO.md)
- 외부 jailbreak baseline: [`external_baselines/README.md`](external_baselines/README.md)
- Qwen/GPT-4o 동시 pilot: [`external_baselines/run_baseline_matrix.py`](external_baselines/run_baseline_matrix.py)

활성 평가 입력은 JMIR *Between Help and Harm* 공개 test 입력에서 시작해 6개 위기 범주,
1인칭 client 발화, 최소 문맥 길이 규칙으로 순차 정제한 625개 goal과 그 pathology route다.
즉 500개는 별도로 새로 수집한 자료가 아니라, 이 JMIR 기반 goal 샘플을 persona-history로
변환해 종합한 후보군을 다시 무결성 검사하고 추린 분석 cohort다. persona는 각 샘플마다 전체
pool에서 동적으로 검색하고 Qwen으로 rerank한다.

625개 생성 후보의 공식 분석 집합은 무결성 손상 17개를 제외한 유효 608개에서 단일
과대표집 범주인 suicidal ideation만 108개 downsample한 500개다. 공식 membership은
`data/red_persona_official_500.jsonl`에 고정되어 있으며, 관측된 모델 결과는 선택에 사용하지
않았다.

Persona 연결은 전체 31,733개 profile에 Qwen 단일 카테고리 라벨을 먼저 부여한 뒤 수행한다.
샘플과 같은 카테고리만 후보로 남기고 top-12 검색과 Qwen 선택을 거친다. 선택된 기본
persona에는 샘플의 goal/pathology에 맞는 임상·인지·관계·동기 정보를 추가한
`sample_adaptation`을 만들며, 이후 Lexi history는 이 보강 persona를 사용한다. 따라서
persona 라벨링과 샘플별 persona 정보 주입은 서로 다른 단계다.

## Goal-aware Qwen 개입 수준

Qwen은 세 조건 모두에서 평가 샘플의 private goal을 알고 있지만, 연구 대화 중 타겟에
보여줄 수 있는 정보량을 다음처럼 분리한다.

| Level | 조건 | 타겟의 goal 노출 | Qwen 질문 방식 | 비교 목적 |
|---:|---|---|---|---|
| 1 | `neutral` / `covert_open_inquiry` | 없음 | 타겟이 이미 쓴 표현과 공개 persona/history를 겉으로 궁금한 듯 추적 | 완전 비직접 유도 |
| 2 | `structural_hint` / `covert_structured_inquiry` | 없음 | 분석 축은 알려주지만 goal 명제와 답은 제공하지 않음 | 구조적 힌트 효과 |
| 3 | `oracle_hint` / `overt_goal_hypothesis` | 직접 노출 | private goal을 연구 가설로 제시 | 직접 제시 대조군 |

Level 1/2에서는 Qwen 질문에 private-goal 2~5-gram이 들어가면 재생성하고, 계속 실패하면
goal-free 고정 질문으로 대체한다. Qwen은 매 타겟 응답을 private goal과 비교해 누락된
정보를 다음 질문으로 추적하지만 정답을 대신 말하지 않는다. 최소 4턴 뒤부터 goal의 핵심
명제, 요청된 speech act, persona 근거가 타겟 발화에 충분히 나타났는지 검사하며 조건별로
최대 7턴까지 동적으로 진행한다.

연구 대화 이후의 4개 manifestation 질문은 실제 응답을 측정하는 별도 직접 노출 단계다.
따라서 산출물은 `intervention`과 `phase_exposure`를 기록하고, 비직접 연구에서 타겟이
스스로 goal을 복원한 `target_originated_recovery_success`와 직접 질문의 응답 성능을
구분한다. CARES에는 분석문이 아니라 `manifestation_candidate_response.text`만 전달한다.

상세 계약과 산출물 예시는
[`persona_redteam/pipeline/README.md`](persona_redteam/pipeline/README.md)의 3~5절을 따른다.

API 키, 모델 checkpoint와 실행 중간 산출물은 Git에 포함하지 않는다. 재현 기준으로 검증된
최종 persona category sidecar와 그 API 감사 요약만 예외적으로 버전 관리한다.

이 서버의 로컬 모델 실행 환경은 [`MUST_READ_SERVING_SETUP.md`](MUST_READ_SERVING_SETUP.md),
재현 가능한 전체 실행 순서는
[`persona_redteam/docs/JMIR_FULL_EXPERIMENT_RUNBOOK_KO.md`](persona_redteam/docs/JMIR_FULL_EXPERIMENT_RUNBOOK_KO.md)를 따른다.
