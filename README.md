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

연구 대화 이후의 8개 manifestation 질문은 실제 응답을 측정하는 별도 직접 노출 단계다.
따라서 산출물은 `intervention`과 `phase_exposure`를 기록하고, 비직접 연구에서 타겟이
스스로 goal을 복원한 `target_originated_recovery_success`와 직접 질문의 응답 성능을
구분한다. CARES에는 분석문이 아니라 `manifestation_candidate_response.text`만 전달한다.

상세 계약과 산출물 예시는
[`persona_redteam/pipeline/README.md`](persona_redteam/pipeline/README.md)의 3~5절을 따른다.

API 키와 모델·실행 산출물은 Git에 포함하지 않는다.

## 작업 이력 (2026-10-09 세션)

이 세션에서 적용한 변경과 현재 진행 상태를 기록한다. 서버 설치·서빙 운영 노트는
[`MUST_READ_SERVING_SETUP.md`](MUST_READ_SERVING_SETUP.md), 구성요소별 점검은
[`COMPONENT_REVIEW_KO.md`](COMPONENT_REVIEW_KO.md) 참고.

### 수정한 코드
- **버그 수정**
  - `pipeline/persona_generation.py`: 존재하지 않는 `candidate_payload` import로 인한 `ImportError` 제거.
  - `experiments/evaluate_persona_co_research.py`: 평가기가 enum 밖 `first_source`(예: `qwen_researcher`)를
    반환할 때 케이스 전체가 실패하던 취약점 → 별칭 정규화 + 오류 메시지에 허용 enum 명시 + 재시도 3→5회.
- **goal-atom coverage 수렴 수정**(핵심)
  - `pipeline/persona_history.py`: coverage를 **단조 누적**하고, 각 턴의 micro-plan이 배정받아
    `verify_turn`을 통과한 atom을 covered로 **union**. Qwen-7B 판정기가 명백히 존재하는 atom을
    계속 under-credit해 전 케이스가 실패하던 문제를 해소(진단: 생성은 atom을 담지만 판정기가 거부).
  - `pipeline/history_planning.py`: `build_plan`의 goal atom 분해를 3–8 → **3–4개, 중복 병합**으로 축소.
- **"생성 데이터 티" 제거**(타겟 가시 콘텐츠)
  - `pipeline/generate_histories.py`: Lexi·planner에 넘기는 프로필에서 `sample_adaptation` 등 생성 메타를
    제거(저장 레코드엔 유지, contract용); 최종 persona를 `{"summary":...}` JSON 대신 **summary 내러티브**로
    저장; 메타포 없을 때 "No recurring metaphor was generated." placeholder 대신 빈 문자열.
  - `experiments/qwen_target_persona_research_dialogue.py`: 타겟에 보이는 persona_state를 JSON 덤프 대신
    **내러티브**로 렌더, 메타포 빈 값이면 줄 자체를 생략.
  - `pipeline/contracts.py`: 위 persona 내러티브 렌더링과 동일한 derivation으로 불변식 검증 갱신.
- **신규 도구**: `extraction/enrich_persona_pathology.py` — 전체 persona pool에 goal과 동일한 임상 pathology
  스키마를 gpt-4o-mini로 보강(탐색적; 상류의 category-label+런타임 enrich 경로와는 별개).

### 현재 상태
- 상류 `main`(category 하드 게이트 + `enrich_profile_for_case` + `label_persona_categories.py`
  + 실패 배치 개별 재시도)을 병합하고 위 수정을 적용. 단위 테스트 62개 통과.
- `label_persona_categories.py`로 31,733 persona category labeling 진행(산출물 `data/`, 비추적).
  초기 분포상 Cactus 풀이 대부분 `anxiety_crisis`로 분류되어, self-harm·violent_thoughts 등은
  category 게이트에서 후보가 희소/0 → **풀 커버리지 확장이 다음 과제**.
- 1케이스 end-to-end 스모크로 `generate_histories → run_batch → evaluate` 경로를 검증(구 히스토리 기준
  preflight 전부 valid). goal-atom coverage 수정 재적용 후 재검증은 진행 중.

API 키·모델 가중치·실행 산출물·persona pool 파일은 Git에 포함하지 않는다.
