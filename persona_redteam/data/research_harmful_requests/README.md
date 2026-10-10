# 최종 정신건강 유해 요청 코호트

## 결과

검토된 JMIR 256개와 외부 후보 221개를 합친 477개를
`gpt-4o-mini-2024-07-18`의 OpenAI Batch API로 동일하게 1차 선별한 뒤, 477개 원문을
모두 한 행씩 직접 읽어 전수 감사했다. 정규화 중복은 0건이다. 자동 판정은
`annotations_all.jsonl`에 그대로 보존하고, 전수 감사 후 최종값은
`manual_review_all.jsonl`과 최종 선별 파일에 기록했다.

| 단계/수준 | 행 수 |
|---|---:|
| 전체 출처+텍스트 후보 | 477 |
| 전수 감사 완료 | 477 |
| 자동 판정 유지 | 394 |
| 전수 감사에서 수정 | 83 |
| CARES H0 | 26 |
| CARES H1 | 30 |
| CARES H2 | 313 |
| CARES H3 | 11 |
| 요청/분야 조건 미충족(수준 미부여) | 97 |
| **최종 H1+H2** | **343** |

최종 343개의 출처 분포는 다음과 같다.

| 출처 | 최초 후보 | 최종 H1+H2 |
|---|---:|---:|
| JMIR 검토 선별본 | 256 | 235 |
| AILuminate v1.0 Demo SSH | 100 | 52 |
| BeaverTails-Evaluation Self-Harm | 50 | 38 |
| mvrcii 사용자 텍스트 고유 후보 | 71 | 18 |

서로 다른 출처를 하나의 성능 분모로 합치지 않는다. 이 표는 데이터 구성 현황이며 모델
성능 표가 아니다.

## 선별 규칙

1. 텍스트가 assistant에게 정보, 조언, 지침, 승인, 검증, 은폐 도움 또는 다른 행동을
   요구하는지 판정한다.
2. 요청 주제가 자살, 자해, 섭식장애, 물질 오남용, 유해한 대처, 정신과적 위기,
   위험한 임상 조언 또는 toxic validation인지 판정한다.
3. 1–2를 통과한 텍스트만 상호배타적 CARES input-risk H0–H3으로 판정한다.
4. H3 후보는 경계 재판정과 규모 검증을 거친다. 심각도만 높거나 한 사람을 대상으로 한
   요청은 H3가 아니다. 공개·다수 또는 제도적 규모에서 유해한 시스템을 구축·운영·확산할
   것을 요청한 경우만 H3다.
5. 이 연구의 최종 코호트는 H1과 H2의 합집합이다. H0와 H3는 삭제하지 않고 전체 판정
   파일에 남겨 선택 과정을 감사할 수 있게 한다.

판정기에 전달한 것은 원문 `user_text`뿐이다. upstream 라벨, JMIR의 기존 GPT 판정,
assistant 응답은 입력하지 않았다. 이후 전수 감사에서도 `original_request` 전체를 읽고
요청성·정신건강 범위·H0–H3의 일관성을 확인했다. 이 감사는 AI 전수 검토이며 독립적인
사람 정답 라벨은 아니다. 논문에서는 모델 보조 선별 후 AI 전수 감사라고 밝혀야 한다.

## 파일

| 파일 | 내용 |
|---|---|
| `research_candidates_477.jsonl` | 의미 판정 전 출처+텍스트 후보 |
| `annotations_all.jsonl` | 477개 전체의 모델 보조 단계별 원 판정과 출처 계보 |
| `manual_review_all.jsonl` | 477개 전체의 전수 감사 및 모델값/최종값 병기 |
| `selected_cares_level1.jsonl` | 전수 감사 후 최종 H1 30개 |
| `selected_cares_level2.jsonl` | 전수 감사 후 최종 H2 313개 |
| `selected_cares_level1_level2.jsonl` | 실험에 사용할 최종 343개 |
| `excluded.jsonl` | 요청/분야 탈락 및 H0/H3 134개 |
| `summary.json` | 모델 보조 선별 단계 요약 |
| `manual_review_summary.json` | 전수 감사 후 최종 분포와 수정 건수 |
| `manifest.json` | 최초 477개 병합·중복 감사 기록 |
| `DATA_DICTIONARY_KO.md` | 모든 칼럼·중첩 필드·결측 규칙 설명 |

재현 코드는 `official_evaluation/prepare_research_cohort.py`와
`official_evaluation/classify_research_cohort.py`, 전수 감사 반영 코드는
`official_evaluation/apply_manual_cohort_review.py`다. 수정 근거는
`official_evaluation/manual_review_overrides.json`에 case ID별로 기록했다. Batch 작업 상태와 원 출력은 Git에
넣지 않는 `official_evaluation/work/research_cohort/batch/`에 보존된다.
