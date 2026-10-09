# 평가 데이터 출처와 추출 계보

이 문서는 현재 본 실험 입력인 JMIR 625개, 그 상위 원본 2,046/813/652개, 전체 persona
pool 31,733개와 본 평가 pathology route 625개가 어디에서 왔고 어떤 규칙으로
생성됐는지 구분한다. 행 수와 체크섬은 `DATA_MANIFEST.json` 및 각 단계 report를 기준으로
한다. 원문 payload와 모델 실행 결과는 민감성·용량·라이선스 때문에 Git에서 제외한다.

## 1. 전체 흐름

```text
JMIR 저자 공개 test 입력 + merged crisis labels
  2,046 rows
  → six crisis labels only
  813 rows
  → GPT-4o-mini first-person client-utterance classification
  652 rows
  → deterministic minimum-length rule: Unicode word count >= 10
  625 rows (main evaluation set)
  → join with goal pathology routes by goal_id
  625 full evaluation blueprints
  → full persona pool retrieval + Qwen reranking + Lexi history generation
  625 generated evaluation cases
```

## 2. 2,046개 JMIR 원본

- 논문: *Between Help and Harm: An Evaluation of Mental Health Crisis Handling by LLMs*
- 저자 저장소: <https://github.com/ellisalicante/LLMs-Mental-Health-Crisis>
- 로컬 계보 파일: `goals/crisis_goals_jmir_n2046.jsonl`
- 행 수: 2,046
- SHA256: `df04f0e1740618d01c9260d5884916fab5fc0e9c1caefcd721d63609081c0422`
- 크기: 2,406,201 bytes

저자 공개 test 입력을 merged crisis label과 원본 ID로 연결한 단계다. 저장 필드는
`goal_id`, 원문 `goal`, `crisis_label`, `source_hf`를 포함한다. 현재 저장소에는 이 import를
처음 수행한 완전한 downloader/joiner가 없으므로, manifest의 checksum과 일치하는 보존
파일이 정확한 재현 기준이다. 이 한계를 숨기지 않는다.

## 3. 2,046 → 813 crisis subset

`no_crisis` 1,231개와 label 누락 2개를 제거하고 아래 여섯 crisis label만 유지했다.

| label | rows |
|---|---:|
| suicidal_ideation | 380 |
| anxiety_crisis | 177 |
| substance_abuse_or_withdrawal | 77 |
| self-harm | 139 |
| violent_thoughts | 21 |
| risk_taking_behaviours | 19 |
| 합계 | 813 |

- 파일: `goals/crisis_goals_jmir_n813.jsonl`
- SHA256: `879ca00b9e57e7ffc62a2fcaa19dc5186572fd5790ac5f2f2f79938383d4c09a`

이 단계는 label에 따른 결정적 필터다. 새로운 위기 문장을 생성하거나 원문을 다시 쓰지
않는다.

## 4. 813 → 652 first-person client utterances

- 코드: `goals/filter_client_utterances.py`
- 모델: `gpt-4o-mini`, temperature 0
- 입력: 각 `goal`의 첫 400문자
- 출력 필드: `is_client_utterance`, `is_request`
- 유지 규칙: `is_client_utterance == yes`
- 파일: `goals/crisis_goals_jmir_client.jsonl`
- SHA256: `9088ed6845a0eab01c199384acf8612fcf03820887b6950f9634974bd054d40b`

분류 프롬프트는 자신의 정신적 고통을 상담자에게 말하는 1인칭 client utterance인지
판정한다. 타인 위해 지시, 제3자 질문, 추상적 의견·상식 문장은 `no`로 분류한다. 5회 실패한
호출은 `None`으로 남아 유지되지 않는다. 따라서 이 단계는 모델 판정이며 완전히 결정적인
사람 라벨이 아니다. 정확한 652개를 재현하려면 보존 파일 checksum을 사용해야 한다.

| label | 813 | kept 652 |
|---|---:|---:|
| suicidal_ideation | 380 | 312 |
| anxiety_crisis | 177 | 177 |
| substance_abuse_or_withdrawal | 77 | 76 |
| self-harm | 139 | 68 |
| violent_thoughts | 21 | 12 |
| risk_taking_behaviours | 19 | 7 |

652개 중 `is_request=true`는 258개, disclosure는 394개다.

## 5. 652 → 625 main evaluation goals

- 코드: `goals/filter_persona_goal_length.py`
- 규칙 버전: `persona-goal-length-v1`
- tokenizer: Unicode word token과 내부 ASCII/curly apostrophe
- 유지 규칙: `word_count(goal) >= 10`
- 유지: 625개
- 제외: 27개
- 파일: `goals/crisis_goals_jmir_persona_min10.jsonl`
- SHA256: `b87a5dd018db36e9706a4dedfcda11635a7891d57f5015ca2f652c4f7e8246fd`
- report: `goals/crisis_goals_jmir_persona_min10.report.json`

짧은 문장은 persona-grounded goal internalization을 평가할 문맥이 부족하다는 사전 규칙으로
제외했다. 이 단계는 모델 호출이 없는 결정적 필터이며, 제외된 27개는 원문 전체와 word
count 및 제외 사유를 별도 JSONL에 보존하도록 구현돼 있다.

| label | kept 625 |
|---|---:|
| suicidal_ideation | 298 |
| anxiety_crisis | 177 |
| substance_abuse_or_withdrawal | 68 |
| self-harm | 63 |
| violent_thoughts | 12 |
| risk_taking_behaviours | 7 |

## 6. Goal pathology와 625개 활성 route

- 파일: 저장소 루트 `data/goal_pathology_routes_n625.jsonl`
- 행 수: 625
- SHA256: `fa31b91fa19c2e78f295e9365465d8c3eb0a946234bec8af0bc33efb659a059e`
- 생성기: `pipeline/route_goals.py`
- 모델: `gpt-4o-mini-2024-07-18`
- 구성: 검증된 기존 30개 재사용 + 누락 595개 checkpoint 추출
- 현재 검색기: `pipeline/persona_pool.py`

Goal pathology는 core condition, risk state, symptoms, functional impairments, cognitive
distortions, stressors, relational stance, communication style, self schema, compliance lever를
구조화한다. `pipeline.persona_pool`이 원문 goal과 pathology로 전체 pool을 점수화하고,
Qwen이 top-k를 최종 rerank한다. route 파일의 과거 생성 호출과 profile payload는 Git에
포함하지 않으므로 동일 checksum의 route 파일이 정확한 historical join 기준이다.

현재 seedless 파이프라인은 고정 persona 후보를 route에 저장하지 않는다. route의
`pathology`를 가져오고, 실행 시 31,733개 전체 pool을 다시 검색한 뒤 Qwen이 rerank한다.
새 샘플도 `pipeline.route_goals --prepared-output ...`으로 같은 경로에 바로 연결된다.

## 7. 전체 persona pool 31,733개

- 기본 로컬 파일: `data/source/personas/personas.jsonl`
- 대체 경로: 환경변수 `$PERSONA_POOL_PATH`
- manifest: 같은 디렉터리의 `manifest.json`
- 총 31,733개
- Cactus: 31,577개
- CBT-Bench CBT-DP reference: 156개

Cactus 원본은 `LangAGI-Lab/cactus`의 `cactus.json`, CBT-DP는
`Psychotherapy-LLM/CBT-Bench`의 reference JSON 10개에서 왔다. upstream 행은 모두
유지하고 synthetic name은 파생 prompt에서 제거했다. 현재 loader는 원본 `id`, background,
concerns, communication style, cognitive patterns, style examples, locale, provenance,
consent/license 필드를 보존하면서 matcher용 alias만 추가한다.

실행 시 `pipeline/persona_pool.py`가 goal pathology와 원문 goal을 사용해 전부 점수화하고
top-k를 만든다. Qwen은 이 top-k를 sample별로 다시 rerank한다. 준비 단계의 고정 persona
seed나 기존 route의 첫 후보는 사용하지 않는다.

## 8. 전체 625개 blueprint 생성

- 코드: `experiments/build_jmir_eval_set_full.py`
- 입력 1: 저장소 루트 `data/crisis_goals_jmir_persona_min10.jsonl`
- 입력 2: 저장소 루트 `data/goal_pathology_routes_n625.jsonl`
- join key: `goal_id`
- 출력: `data/prepared/blueprints/jmir_eval_full.jsonl`
- 표본추출: 없음

625개 중 pathology route가 하나라도 없으면 builder는 실패한다. 누락 사례를 버리거나 100개
fixture로 대체하지 않는다. 이후 `pipeline.prepare adapt`는 persona/metaphor seed 없이
goal, crisis label, pathology provenance만 가진 pre-generation case를 만든다.

## 9. 재현 명령

필요한 두 historical payload의 checksum을 먼저 확인한 뒤 실행한다.

```bash
sha256sum ../data/crisis_goals_jmir_persona_min10.jsonl
sha256sum ../data/goal_pathology_routes_n625.jsonl

python3 experiments/build_jmir_eval_set_full.py
python3 -m pipeline.preflight \
  --blueprint data/prepared/blueprints/jmir_eval_full.jsonl
python3 -m pipeline.prepare adapt \
  --input data/prepared/blueprints/jmir_eval_full.jsonl \
  --output data/prepared/cases/jmir_eval_full_pre_generation.json
python3 -m pipeline.preflight \
  --prepared-cases data/prepared/cases/jmir_eval_full_pre_generation.json
```

현재 Git 작업공간에는 625개 goal과 완성된 625개 pathology route가 포함된다. persona pool과
모델 생성 결과는 별도 비추적 데이터로 유지한다.
