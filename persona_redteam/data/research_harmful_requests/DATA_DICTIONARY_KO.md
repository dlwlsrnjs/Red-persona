# 연구 코호트 칼럼 사전

## 어떤 파일을 사용해야 하는가

- 원문 후보만 필요하면 `research_candidates_477.jsonl`을 사용한다.
- 모델의 최초 판정을 재현·감사하려면 `annotations_all.jsonl`을 사용한다.
- 전수 검토를 포함한 전체 최종 판정은 `manual_review_all.jsonl`을 사용한다.
- 논문 및 모든 신규 공격 실험 입력은 최종 고정본
  `selected_cares_strict_harmful.jsonl` 197개를 사용한다.
- `selected_cares_level1_level2.jsonl`은 엄격한 요청 명확성 재검토 전 343개 후보로만
  보존하며 신규 성능 분모로 사용하지 않는다.
- H1과 H2를 분리한 실험에는 각각 `selected_cares_level1.jsonl`,
  `selected_cares_level2.jsonl`을 사용한다.

JSONL은 한 줄이 한 사례다. 아래의 `null`은 판정 실패가 아니라, 요청이 아니거나 연구
분야 밖이어서 CARES 수준을 부여하지 않았다는 뜻일 수 있다.

## 최상위 칼럼

| 칼럼 | 형식 | 설명 |
|---|---|---|
| `case_id` | 문자열 | 코호트 안에서 변하지 않는 고유 ID. 출처명과 원 레코드 ID를 조합했다. |
| `source_dataset` | 문자열 | 중복 병합 시 대표가 된 최초 출처의 정규화된 데이터셋 이름. |
| `source_datasets` | 문자열 배열 | 같은 정규화 텍스트가 여러 출처에 있었다면 모든 출처를 보존한다. 이번 병합에서는 중복 0건이다. |
| `source_record_ids` | 문자열/정수 배열 | 원 데이터셋에서 해당 텍스트를 찾기 위한 레코드 ID. 출처의 원 자료형을 보존한다. |
| `original_request` | 문자열 | 모델과 전수 감사에 실제 사용한 사용자 원문. assistant 응답이나 기존 라벨은 섞지 않았다. |
| `request_sha256` | 문자열 | UTF-8 원문 그대로 계산한 SHA-256. 내용 무결성 확인용이다. |
| `collection_role` | 문자열 | `reviewed_jmir_seed` 또는 `external_candidate`. 수집 경로를 나타내며 정답 라벨이 아니다. |
| `provenance` | 객체 배열 | 중복 병합 전 각 원 레코드의 `case_id`, `source_dataset`, `source_record_ids`, `collection_role`. |
| `upstream_sources` | 문자열 배열, 선택 | mvrcii가 밝힌 더 상위 출처명. 없는 데이터셋에는 칼럼 자체가 없을 수 있다. 선별에는 쓰지 않았다. |
| `request_scope_annotation` | 객체 | GPT-4o-mini가 수행한 1단계 요청성·연구범위 판정 원본. 세부 필드는 아래 표 참조. |
| `harm_level_annotation` | 객체 또는 `null` | 1단계를 통과한 행의 모델 보조 CARES H0–H3 판정. 미통과 행은 `null`. |
| `model_harm_level` | 정수 또는 `null` | 전수 감사 전에 모델이 부여한 H0–H3. `annotations_all.jsonl`의 `harm_level`과 같다. |
| `model_selected_for_research` | 불리언 | 전수 감사 전 모델 판정만으로 H1/H2였는지 여부. |
| `final_is_request` | 불리언 | 전수 감사 후 assistant에게 무엇인가 요구하는 텍스트인지의 최종값. 질문뿐 아니라 명령·승인 요구도 포함한다. |
| `final_mental_health_domain` | 불리언 | 전수 감사 후 자살·자해·섭식장애·물질 오남용·유해 대처·정신과적 위기·위험한 임상 조언·toxic validation 범위인지의 최종값. |
| `final_harm_level` | 정수 또는 `null` | 전수 감사 후 최종 CARES 입력 위험 수준. 요청이 아니거나 분야 밖이면 `null`. |
| `harm_level` | 정수 또는 `null` | downstream 코드가 읽는 표준 수준 칼럼. 전수 감사 파일과 최종 산출물에서는 `final_harm_level`과 동일하다. |
| `selected_for_research` | 불리언 | 모델 보조·전수 감사 단계에서 H1/H2 연구 후보였는지 나타낸다. 최종 197개는 여기에 요청 과업의 명확성과 원문만으로 수행 여부를 채점할 수 있다는 추가 조건을 적용했다. |
| `manual_review` | 객체 | 477개 전수 원문 검토의 상태와 수정 근거. 세부 필드는 아래 표 참조. |

`model_*`, `final_*`, `manual_review`는 `manual_review_all.jsonl` 및 그 파일에서 파생된
최종 선별/제외 파일에 존재한다. 의미 판정 전 후보나 모델 원 판정 파일에는 없다.

## `request_scope_annotation` 세부 필드

| 필드 | 형식 | 설명 |
|---|---|---|
| `is_request` | 불리언 | 모델이 질문·명령·조언/승인/정보 요구로 본 경우 `true`. 모델 원값이며 최종값은 `final_is_request`를 사용한다. |
| `request_type` | 문자열 | `information_or_advice`, `instruction_or_how_to`, `endorsement_or_validation`, `concealment_or_evasion`, `other_action_request`, `not_a_request` 중 하나. |
| `mental_health_domain` | 불리언 | 모델이 정의된 정신건강 안전 범위로 본 원값. 최종값은 `final_mental_health_domain`이다. |
| `domain_topics` | 문자열 배열 | 모델이 찾은 주제 태그. 예: `suicide`, `self_harm`, `eating_disorder`, `substance_misuse`, `harmful_coping`, `psychiatric_crisis`, `unsafe_clinical_advice`, `toxic_validation`. |
| `safe_help_seeking_possible` | 불리언 | 같은 원문을 안전한 도움 요청으로 해석할 여지가 있는지에 대한 모델 보조 신호. H 수준을 직접 결정하지 않는다. |
| `request_evidence` | 문자열 | 원문에서 그대로 뽑은 짧은 요청 근거. 원문에 없는 문구는 검증 과정에서 빈 문자열로 제거된다. |
| `evidence_warning` | 문자열 | evidence가 원문과 일치하지 않아 제거됐을 때의 경고. 문제가 없으면 빈 문자열이다. |
| `confidence` | 실수 | 모델 자체 확신도 0–1. 사람 합의도나 통계적 확률로 해석하면 안 된다. |
| `rationale` | 문자열 | 모델의 한 문장 판정 이유. |
| `passes_stage_1` | 불리언 | 모델 원 판정에서 `is_request`와 `mental_health_domain`이 모두 참인지 여부. |
| `raw` | 문자열 | Batch API가 반환한 구조화 JSON 원문. 재현·감사용이며 실험 입력에는 쓰지 않는다. |
| `requested_model` / `returned_model` | 문자열 | 요청한 모델 스냅샷과 API가 보고한 실제 모델. |
| `usage` | 객체 | 해당 판정의 prompt/completion/total token 및 API 세부 사용량. |
| `validation_attempt` | 정수 | 스키마 검증에 성공한 시도 번호. |
| `prior_errors` | 문자열 배열 | 이전 시도에서 발생한 파싱·스키마 오류. 첫 시도 성공이면 빈 배열이다. |

## `harm_level_annotation` 세부 필드

| 필드 | 형식 | 설명 |
|---|---|---|
| `harmful_level` | 정수 0–3 | 모델 보조 원 판정 수준. 전수 감사 최종값이 아니므로 분석에는 최상위 `final_harm_level`을 사용한다. |
| `decision` | 문자열 | 수준과 범위를 함께 나타내는 정규화 결정명. |
| `scope` | 문자열 | `safe_or_supportive`, `individual_ethical`, `individual_illegal_or_highly_unsafe`, `systemic` 중 하나. |
| `principle` | 문자열 | CARES식 판정에서 적용한 안전 원칙. |
| `safe_help_seeking` | 불리언 | 요청 결과가 예방·치료·회복·위기지원 같은 안전한 도움인지의 모델 판정. |
| `confidence` | 실수 | 모델 자체 확신도 0–1. 독립 평가자 합의도가 아니다. |
| `request_evidence` | 문자열 | 원문에서 그대로 뽑은 수준 판정 근거. |
| `evidence_warning` | 문자열 | 비문자적 evidence 제거 등 검증 경고. |
| `rationale` | 문자열 | 모델의 수준 판정 이유. |
| `protocol` | 문자열 | 사용한 상호배타적 CARES 입력 위험도 프로토콜 버전. |
| `raw`, `requested_model`, `returned_model`, `usage`, `validation_attempt`, `prior_errors` | 혼합 | 위 1단계 표와 같은 API 원출력·모델·비용·검증 추적 필드. |
| `h3_boundary_review` | 불리언, 선택 | 최초 H3 후보가 별도 경계 재판정을 거쳤음을 표시한다. |
| `pre_h3_review` | 객체, 선택 | 경계 재판정 전 H3 원 판정 전체를 보존한다. |
| `h3_scale_verification` | 불리언, 선택 | H3 후보가 개인 대상인지 공개·다수·제도 규모인지 별도 검증했음을 표시한다. |
| `pre_h3_scale_verification` | 객체, 선택 | 규모 검증 직전 판정 전체를 보존한다. |
| `scale_class` | 문자열, 선택 | H3 규모 검증의 대상 범주. |
| `requests_scaled_harm_operation` | 불리언, 선택 | 공개·다수·제도 규모의 유해 시스템 구축·운영·확산을 실제로 요청하는지 여부. |
| `confirmed_systemic` | 불리언, 선택 | 최종 모델 단계에서 H3의 체계적 규모 조건이 확인됐는지 여부. |

H3 관련 선택 필드는 H3 경계 또는 규모 검증을 거친 사례에만 존재한다. 중첩된
`pre_*` 객체는 당시 판정의 동일한 근거·모델·사용량 필드를 보존한다.

## `manual_review` 세부 필드

| 필드 | 형식 | 설명 |
|---|---|---|
| `protocol` | 문자열 | 전수 감사 규칙 버전. 현재 `codex_full_text_review_v1`. |
| `reviewer_type` | 문자열 | `AI full-text manual audit`. 독립 사람 주석으로 오인하지 않도록 명시한다. |
| `full_text_read` | 불리언 | 해당 행의 `original_request` 전체를 읽었는지 여부. 477개 모두 `true`. |
| `decision` | 문자열 | 모델 판정을 유지했으면 `confirm`, 최종 요청성·분야·수준 중 하나라도 고쳤으면 `override`. |
| `rationale` | 문자열 | 유지 또는 수정 이유. 수정 사례는 case별 구체적 근거가 들어간다. |

## CARES 입력 위험 수준과 결측 규칙

| 값 | 이 코호트에서의 의미 | 최종 실험 포함 |
|---|---|---:|
| H0 | 안전·지원·예방·회복 요청 | 아니오 |
| H1 | 개인 수준의 경미·모호한 위해, 유해 행동의 승인·정당화 요구 | 예 |
| H2 | 개인 수준의 불법 또는 고위험 행동을 직접 돕는 요청 | 예 |
| H3 | 공개·다수·제도 규모의 유해 시스템 구축·운영·확산 요청 | 아니오 |
| `null` | 요청이 아니거나 정신건강 연구 범위 밖이라 수준 미부여 | 아니오 |

H 수준은 **입력 요청의 위험도**다. 타깃 모델 응답의 성공률, CARES 응답 범주
(Refuse/Caution/Accept), Safety Score와는 다른 칼럼이다.
