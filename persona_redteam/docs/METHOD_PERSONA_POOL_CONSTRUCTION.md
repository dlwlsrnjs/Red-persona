# Persona pool construction, category gating, and sample adaptation

이 문서는 현재 활성 625-case 파이프라인의 persona 구성 방법을 설명한다. 과거의
2,357-persona/embedding 기반 실험에는 적용되지 않는다.

## 1. 원본 pool

활성 pool은 `../data/personas/personas.jsonl`의 31,733개 profile이다.

| source | rows | retained fields |
|---|---:|---|
| Cactus | 31,577 | background, concerns, cognitive patterns, communication style/examples |
| CBT-Bench CBT-DP reference | 156 | reference persona narrative and provenance |

원본 profile은 Git에 포함하며 SHA256과 출처는 `DATA_MANIFEST.json` 및
`DATA_LINEAGE_AND_EXTRACTION_KO.md`에 기록한다. 이 원본 pool에는 활성 matcher가 기대하는
`core_condition`, `symptoms`, `functional_impairments`, `crisis_tags`가 기본적으로 존재하지
않는다.

## 2. Qwen category sidecar

`pipeline.label_persona_categories`가 각 persona에 초기 평가 범주 하나를 부여한다. 출력
`../data/personas/persona_category_labels.jsonl` 중 API 검증을 끝낸 최종본과
`persona_category_labels.audit.json`은 재현 기준으로 Git에 포함한다. 생성 checkpoint,
partial sidecar와 후보 풀은 실행별 provenance로만 보존하며 Git에 포함하지 않는다.

희소 범주는 `pipeline.rebalance_persona_categories`가 GPT-4o mini로 후보를 만들고,
`pipeline.audit_persona_category_rebalance`가 각 항목을 독립 심사한다. 최종 정책은 원문상의
인접 신호만으로 재지정한 행을 보수적으로 원복하고, 서로 다른 base identity를 유지한 명시적
`category_base_adaptation`만 부족분에 사용한다. 이는 원문 사실이 아닌 category-conditioned
construction으로 별도 model·method·confidence provenance를 기록한다. 유효한 구성형 행은
`desire|enacted|historical` 중 명확한 위해 방향을 가져야 한다.

현재 최종본은 31,733행이며 범주별 개수는 anxiety 31,046, risk-taking 102, self-harm 101,
substance 216, suicidal ideation 168, violent thoughts 100이다. 보강된 268행은 모두 구성형이고,
self-harm/suicidal/violent의 고유 base family가 각각 100개다. GPT-4o mini 항목별 감사 결과는
268/268 통과이며 sidecar SHA-256은
`7fa62560f5c99dc1d05b7aacac17f63a92ad19f13ac1e3fda13aa5a033edf9f0`이다.
범주별 정리본은 `../data/personas/by_category/`에 있으며, 논문에 바로 사용할 수 있는 영어
추출·생성 문단은 `docs/PERSONA_CATEGORY_EXTRACTION_AND_GENERATION.md`에 별도로 고정했다.

허용 범주는 JMIR 평가의 여섯 범주와 동일하다.

- `anxiety_crisis`
- `risk_taking_behaviours`
- `self-harm`
- `substance_abuse_or_withdrawal`
- `suicidal_ideation`
- `violent_thoughts`

각 row는 `persona_id`, `goal_category`, `category_fit`(`direct|adjacent|weak`),
`harm_direction`(`desire|enacted|fear|historical|none`), 근거와 labeler version을 가진다.
위해 욕구와 우발적 위해에 대한 공포, 죽고 싶은 욕구와 죽음에 대한 공포를 구분하도록
지시한다. 어느 위험 범주에도 맞지 않는 persona는 `anxiety_crisis/weak`로 남긴다.

History 생성은 sidecar가 원본 31,733개 ID를 정확히 한 번씩 포함할 때만 시작한다. sidecar
경로와 checksum은 history fingerprint에 포함한다.

## 3. Category-gated retrieval

샘플의 `crisis_label`과 동일한 `goal_category`만 후보로 허용한다. 다른 범주의 persona는
점수가 높아도 후보가 될 수 없다. 동일 범주 안에서는 다음을 합산한다.

1. 사용 가능한 structured field의 weighted Jaccard overlap
2. 원문 goal token이 persona narrative에 나타나는 비율 × 1.5
3. category fit bonus: direct 0.30, adjacent 0.10, weak 0.00

현재 활성 검색에는 embedding이나 cosine threshold가 없다. `category_fit`은 가산 bonus이며
lexicographic hard ordering이 아니므로 lexical/structured 점수가 높은 weak persona가 direct
persona보다 앞설 수 있다. 상위 12개를 만든 뒤 Qwen이 private goal과 goal pathology를 보고
기본 persona 하나를 선택한다.

## 4. Sample-specific adaptation

Qwen은 선택된 기본 persona의 안정적인 정체성과 말투를 유지하면서 현재 샘플의 goal과
pathology에 필요한 presenting concern, 임상·인지·기능·관계 축, self-schema,
goal-relevant needs와 harm direction을 생성한다. 결과는 `sample_adaptation` provenance와 함께
보존한다. private goal 전체를 그대로 복사한 결과는 거부하지만, 의미 보존을 위한 paraphrase는
설계상 허용한다.

따라서 이 단계는 원본 corpus에서 임상 필드를 단순 추출하는 과정이 아니라 **goal-conditioned
persona construction**이다. 생성된 임상 축을 원문에 직접 관찰된 사실로 표현해서는 안 된다.

## 5. Goal-atom history construction

Qwen은 private goal을 3–4개의 비중복 `G1..Gn` information atom과 최대 12개 micro-plan으로
분해한다. Lexi가 각 micro-plan을 이전 상담 exchange로 렌더링하고, Qwen 검증을 통과한 turn만
누적한다. Coverage는 turn별 판정과 검증된 micro-plan atom을 단조 누적하며, 모든 atom이
persona-grounded evidence로 포함될 때 history를 종료한다. 최대 turn까지 충족하지 못한 사례는
성공 산출물에 포함하지 않고 `.failed.json`에 진단을 남긴다.

최종 target-visible persona는 마지막 `persona_state.summary`의 자연어 내러티브이며,
생성 provenance와 JSON wrapper는 target에게 노출하지 않는다.

## 6. 필수 보고 항목과 한계

- category sidecar의 model/revision, checksum, 범주·fit·harm-direction 분포
- category label 실패 및 재시도 수
- base persona와 sample adaptation의 ID·provenance
- history 생성 성공/실패율과 실패 사례를 포함한 end-to-end denominator
- goal atom 수, turn 수, 재계획·검증·coverage audit
- branch-level 지표와 case-level Success@4의 동시 보고

단일 category 강제, `anxiety_crisis/weak` catch-all, corpus 중복, 희소한 위험 persona,
goal-conditioned adaptation과 goal-atom 주입은 모두 결과 해석의 한계다. 특히 target이 goal을
복원하더라도 corpus persona만의 자연 발생 효과로 해석할 수 없으며, goal-blind selection/history
대조군과 함께 보고해야 한다.
