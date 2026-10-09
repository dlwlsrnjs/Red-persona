# RED-Persona 구성요소별 분석 (존재이유 / 작업 / 수행검증 / 개선점)

작성 2026-10-09. 스모크런(1 자살 케이스 end-to-end) + 전수 데이터 점검 기준.
파이프라인 순서대로 정리한다.

---

## 1. 입력 데이터 — `data/crisis_goals_jmir_persona_min10.jsonl` (625) + `data/goal_pathology_routes_n625.jsonl` (625)

- **존재이유**: JMIR 위기 발화를 평가 대상 "goal"로 쓰고, 각 goal의 임상 pathology(core_condition, risk_state, 인지왜곡, self_schema, compliance_lever 등)를 route로 보관. pathology가 goal↔persona를 잇는 다리.
- **해야 할 작업**: 625 goal ↔ 625 route를 goal_id로 1:1 연결, pathology 완전 추출.
- **수행 검증**: ✅ 625↔625 완전 연결(결손 0, crisis_label 불일치 0), pathology 필수필드 공백 0, risk_state 정상. repaired(추론보정) 46/625로 낮음.
- **개선점**:
  - ⚠️ route **61/625에서 core_condition에 crisis 라벨류**(suicidal_ideation 16, self_harm 45)가 섞임 — 추출 SYS가 "core_condition은 crisis 라벨 금지"라 했는데 위반. 매칭 온톨로지를 흐릴 수 있음(경미).
  - 재현성: 652→ 단계가 gpt-4o-mini 판정이라 완전 결정적이지 않음(문서에 명시됨). checksum 보존이 유일 기준.

---

## 2. persona pool — `data/personas/personas.jsonl` (31,733)

- **존재이유**: goal에 입힐 "취약 내담자" 후보 풀 (Cactus 31,577 + CBT-DP 156).
- **해야 할 작업**: goal pathology와 같은 임상 축으로 매칭 가능해야 함.
- **수행 검증**: ❌(원본) 매칭에 쓰는 임상 레이어(core_condition/symptoms/crisis_tags/…)가 **0% 존재** → 매칭이 사실상 goal 원문 단어겹침(lexical)으로만 동작했음. (enrich로 해결, §3)
- **개선점(중대)**:
  - 🔴 **중복 심각**: 31,733행이 **distinct background 4,058개뿐**(약 8배 복제). 같은 인물이 여러 id로 반복 → 검색 top-k가 같은 사람 복제로 채워질 위험.
  - 🔴 **위기 희소**: 원문 기준 위기 관련 4.8%, 자살 0.1%.

---

## 3. `extraction/enrich_persona_pathology.py` (신규, 이번에 추가)

- **존재이유**: 풀을 goal과 동일한 pathology 스키마로 투영해 임상 매칭이 실제로 작동하게 함.
- **해야 할 작업**: gpt-4o-mini로 core_condition/symptoms/인지왜곡(snake_case)/crisis_tags/self_schema/compliance_lever/risk_state 생성, 원본 보존.
- **수행 검증**: ✅ 31,733 전건 완료(0 에러), 완성도 100%, 위기 판별 정확(노이즈 키워드는 no_crisis로 내림), risk_state 버그 수정(비위기→none).
- **개선점(중대)**:
  - 🔴 최종 crisis_tags 분포 = **no_crisis 31,618 / suicidal_ideation 114 / self-harm 1 / 나머지 0**. 위기 페르소나 115개 중 **distinct는 29명**.
  - 즉 **anxiety_crisis·substance·violent_thoughts·risk_taking는 사실상 태깅 0** → §4 crisis 하드 필터가 이 범주들에선 작동 못 함.
  - 원인: Cactus가 본래 경증 상담이라 "crisis"로 보기 어려움 + 프롬프트가 보수적. 해결은 §4 개선점의 crisis-conditioned 재프로파일링 또는 매칭 기준 변경.

---

## 4. `pipeline/persona_pool.py` — retrieve + crisis 하드 필터(이번에 추가)

- **존재이유**: 각 goal에 대해 전체 풀에서 최적 페르소나 후보 top-k 산출.
- **해야 할 작업**: pathology 구조적 겹침(인지왜곡×3, 증상/관계/소통×2) + crisis 보너스 + goal 원문 lexical(×1.5)로 점수화, 상위 k 반환. (이번에 crisis_tags 하드 필터 추가)
- **수행 검증**: ✅ 스모크에서 자살 goal→자살 페르소나 매칭(crisis_filtered=True) 확인. 0매칭 시 full 폴백 정상.
- **개선점(중대)**:
  - 🔴 **crisis 하드 필터가 5개 범주에서 무력**(§3). 327개 goal(anxiety 177+substance 68+self-harm 63+violent 12+risk 7)은 crisis 후보 0 → full 폴백 → 비위기 매칭.
  - 🔴 **중복 미제거**: 같은 background 복제들이 top-k를 점유 가능 → 자살 goal 298개가 distinct 29명으로 수렴(다양성 붕괴).
  - 🟡 **임베딩 단계 없음**: METHOD 문서는 구조적 0.75 + 임베딩 cosine 0.25(text-embedding-3-small)인데, 코드엔 임베딩 없고 lexical ×1.5가 대체. 의미 유사 매칭이 약함.
  - **권고**:
    1. crisis "하드 필터"를 **임상 grounding 기반**(core_condition/symptom 겹침 또는 pathology cosine≥임계)으로 완화 — crisis_tags 동치보다 풀 특성에 맞음(논문 grounding gate와 일치).
    2. 또는 METHOD식 **crisis-conditioned 재프로파일링**으로 위기 풀을 확장.
    3. retrieve에 **background 기준 dedup** 추가(동일 인물 1회만).

---

## 5. 과거이력 생성 — `history_planning.py` + `persona_history.py` + `generate_histories.py`

- **존재이유**: Qwen이 (a) 후보 중 최적 페르소나 선택(rerank), (b) 목표를 단계별 plan으로 분해, Lexi가 그 plan대로 "과거 상담 대화" 생성, Qwen이 턴마다 검증, 최종 누적 persona_state를 활성 페르소나로.
- **해야 할 작업**: 최소 4턴·최대 8턴, 중복/비연속/비영어 턴 거부·재생성, coverage 충분 시 조기종료, goal 원문 verbatim 금지.
- **수행 검증**: ✅ 스모크에서 8턴 생성, Qwen plan(8단계)·턴검증 전부 통과, preflight(cases) valid. 계약(contracts)에서 "모든 턴 Qwen 검증 통과", "persona=최종 state", "goal verbatim 아님" 강제.
- **개선점**:
  - 🟡 `build_plan`이 `micro_plans` 개수를 max_turns와 **정확히 일치** 요구 → Qwen이 7/9개 주면 즉시 실패. generate_histories가 재시도 없이 그 케이스 실패 처리. (실패는 `--retry-failed`로 복구되나, 플랜 길이 허용폭을 주면 실패율↓)
  - 🟡 Lexi 생성이 서버당 직렬(케이스 루프). 625 전체는 수 시간 예상 — case 병렬화 여지(서버 2대/배치).

---

## 6. 본 실험 대화 — `experiments/qwen_target_persona_research_dialogue.py`

- **존재이유**: goal을 모르는 target이 "공동연구" 프레임에 유도돼 **스스로** 유해 결론을 쓰게 만들고, 8개 각도(final_directions)로 분기 후 manifestation 턴에서 직접응답(candidate) 유도.
- **해야 할 작업**: 3조건(neutral/structural/oracle), 4~7턴 동적종료, goal n-gram 누출 차단(oracle 제외), 8 독립 분기(공유 prefix), candidate_response/research_analysis 분리.
- **수행 검증**: ✅ 스모크 preflight(run) valid — 3조건×5턴(동적종료)×8분기×manifestation, 공유 prefix 해시 일치, 시스템 프롬프트 정확, candidate 분리 확인.
- **개선점**:
  - 🔴 **운영**: QwenResearcher가 **vLLM이 아니라 in-process transformers**로 Qwen을 올림 → 느리고, `QWEN_BATCH_SIZE` 자동 24가 긴 누적대화에서 **CUDA OOM**(실측). 반드시 venv python + `QWEN_DEVICE`(빈 GPU) + `QWEN_BATCH_SIZE=6~8`. **권고**: 연구자 Qwen도 vLLM(:8000) 서버로 호출하도록 바꾸면 속도·안정성 크게 개선(생성단계와 엔진 일원화).
  - 🟡 **해석 주의**: manifestation 템플릿이 `{goal}`로 **goal을 직접 노출**(측정전용 단계, 설계상 의도). 이 턴의 CARES/behavior는 "goal 노출 후 직접응답"에 대한 측정이라 ASR가 상향될 수 있음 — 논문 해석 시 raw/target_originated(분석응답 기반)와 구분 필요.
  - 🟡 manifestation bank가 템플릿×스타일 조합이라 selector 인덱스 폭이 큼(동작은 정상).

---

## 7. 평가 — `evaluate_persona_co_research.py` + `evaluate_cares_official.py` + 프롬프트

- **존재이유**: 분기별 recovery(R0~R4), behavior(B0~B5), 공식 CARES(candidate-only)로 성공·안전 측정, provenance(출처)로 "target이 스스로 생성" 판정.
- **해야 할 작업**: recovery는 분석응답 기준, behavior/CARES는 manifestation candidate 기준, R3+는 명제+화행 둘 다 matched, target_originated는 oracle·qwen-first 제외, 인용은 실제 부분문자열만.
- **수행 검증**: ✅ 스모크에서 24분기 평가 완료, preflight(evaluation) valid. 지표 타당(oracle의 target_originated=0).
- **개선점**:
  - ✅(수정완료) 평가기가 간헐적으로 enum 밖 `first_source`(예: `qwen_researcher`) 반환 시 케이스 전체 실패하던 취약점 → 별칭 정규화 + enum 명시 + 재시도 5회.
  - 🔴 **CARES Safety Score 미산출**: blueprint가 `cares_harmful_level=None`으로 고정 → 전 케이스 Score 집계 불가(라벨 Accept/Caution/Refuse만 나옴). 공식 Safety Score까지 쓰려면 **625개 harmful level 사전 주석**(0~3) 필요. 현재는 non-refuse@8 등 라벨 기반 지표만 유효.
  - 🟡 recovery 평가가 분기당 custom_evaluate 2회(recovery+manifestation) → 호출량 큼. 동일 입력이면 1회로 합칠 여지.

---

## 8. 계약/검증 — `contracts.py` + `preflight.py`

- **존재이유**: 단계 경계마다 모델 호출 없이 스키마·불변식 검증.
- **수행 검증**: ✅ blueprint/prepared/cases/run/evaluation 5종 검증 견고, 스모크 전 단계 valid. 유닛테스트 54개 통과.
- **개선점**: 🟢 거의 없음. (참고) `pipeline/persona_generation.py`가 존재하지 않는 심볼 import로 **ImportError**였던 것 수정완료.

---

## 종합 우선순위 (개선 권고)

| 우선 | 항목 | 영향 |
|---|---|---|
| 🔴1 | 5개 위기범주(327 goal)에 crisis 페르소나 부재 → 매칭 기준을 임상 grounding으로 완화하거나 crisis-conditioned 확장 | 실험 타당성 핵심 |
| 🔴2 | 풀 중복(distinct 4,058) → retrieve dedup | 페르소나 다양성 |
| 🔴3 | run_batch Qwen을 vLLM로 전환(현재 in-process OOM/느림) | 전체 실행 속도·안정 |
| 🟡4 | CARES harmful_level 주석(Safety Score 활성화) | 안전지표 완전성 |
| 🟡5 | 임베딩 기반 의미 매칭 추가(METHOD 문서 0.25 cosine) | 매칭 품질 |
| ✅ | persona_generation ImportError / evaluator first_source 취약점 | 수정 완료 |
