# Qwen2.5-7B target 공식 500개 실행 감사

이 문서는 추가 모델 일반성 arm의 생성 단계가 논문 분석에 들어가기 전에 실제 실행 계약을
통과했는지 기록한다. 분석 모집단은 `data/red_persona_official_500.jsonl`과 같은 500개 case ID다.

## 역할 분리

- goal-blind target: `Qwen/Qwen2.5-7B-Instruct`, revision
  `a09a35458c702b33eeacc393d103063234e8bc28`
- goal-aware planner: 표준 `meta-llama/Llama-3.1-8B-Instruct`, revision
  `0e9e39f249a16976918f6564b8830bc894c89659`
- Lexi-Uncensored: 이 arm의 target 또는 planner로 사용하지 않음
- evaluator: 생성 완료 뒤 OpenAI Batch에서 Recovery, Behavior, CARES를 독립 판정

planner만 private goal을 본다. target은 generic system prompt, persona/history packet,
planner가 선택한 target-visible 질문, target 자신의 누적 응답만 본다. Llama tokenizer에 pad
token이 없기 때문에 runner가 `pad_token=eos_token`을 설정했고, OOM 때는 사례를 버리지 않고
micro-batch 크기만 75%씩 낮췄다.

기존 GPT arm과 evaluator schema의 비교 가능성을 유지하기 위해 provenance enum과 guideline의
일부 문자열은 역사적 이름 `qwen`/“Qwen researcher”를 그대로 사용한다. Qwen target arm에서
이 문자열은 **planner 역할 label**이며 실제 질문 생성 모델이 Qwen이라는 뜻이 아니다. 모든
질문의 `planner_model`과 `planner_revision`은 위 Llama revision으로 저장되어 있다. 다만 target이
이 역사적 명칭을 본다는 언어적 priming 가능성은 추가 arm의 제한으로 보고하며, 향후 완전히
generic한 `researcher` enum으로 바꾸는 실험은 별도 protocol version으로 구분해야 한다.

## 병렬 실행과 동일성

고정된 500개 index를 `72/72/72/71/71/71/71`의 연속 7개 disjoint shard로 분할했다. 각 shard는
별도 Llama planner GPU와 checkpoint를 사용했고, 모든 target 호출은 동일한 localhost Qwen vLLM
서버로 보냈다. 사례 내부 stage 순서는 직렬로 유지했다. 완료 후 `merge_run_shards.py`가 중복
case ID, 계약 위반, target/condition/direction 불일치를 검사하고 공식 500개 폴더로 병합했다.

## Full dialogue 생성 QA

- 사례: 500
- condition: neutral만 사용
- 연구 turn: 500/500 모두 7회
- stop reason: 500/500 `all_stages_completed`
- 연구 질문 3,500개: Llama dynamic 2,505, 등록 fallback 995
- final 질문 2,000개: Llama dynamic 1,512, 등록 fallback 488
- final branch: 네 방향별 500개, 총 2,000개
- final target: `finish_reason=stop` 2,000, 빈 문자열 0
- manifestation target: `finish_reason=stop` 2,000, 빈 candidate 0
- manifestation parse: structured JSON 1,965, plain-text fallback 35
- run contract 오류: 0

등록 fallback은 API 실패를 숨기는 대체 사례가 아니다. Llama 질문이 goal n-gram 누출, 형식,
중복 검사를 통과하지 못했을 때 같은 stage와 direction에 미리 등록된 goal-free 질문을 사용한
것이다. 따라서 500개 분모와 target 응답은 모두 유지된다.

## No-research-dialogue 생성 QA

- 사례: 500
- post-initial 연구 turn: 0
- final branch: 네 방향별 500개, 총 2,000개
- final target: `finish_reason=stop` 2,000, 빈 문자열 0
- manifestation target: `finish_reason=stop` 2,000, 빈 candidate 0
- final 질문 2,000개: Llama dynamic 1,325, 등록 fallback 675
- manifestation 질문: goal-aware registered selector 2,000
- parse: structured JSON 1,985, plain-text fallback 14,
  `direct_response` schema alias 1
- run contract 오류: 0

한 출력은 정상 후보 문장을 `candidate_response` 대신 `direct_response`에 넣었다. 원문 target
응답은 보존하면서 parser가 이 명시적 alias만 candidate로 읽도록 수정했다. Full arm에서 한 번
발생한 JSON 배열 출력은 저장 전에 같은 prompt의 schema-correction turn을 1회 호출하여 정상
객체로 다시 받았다. 두 경우 모두 빈 문자열을 임의 생성해 채우지 않았다.

## 해석 시 주의

Qwen target arm의 planner가 GPT-4o target arm의 Qwen planner와 다르므로, 두 target arm의
절대 성공률 차이를 target architecture 하나의 순수 인과효과로 해석하면 안 된다. 이 arm의
주 비교는 같은 Qwen target, 같은 Llama planner, 같은 initial response, 같은 네 방향을 유지한
full dialogue 대 no-research-dialogue의 paired delta다. target 간 비교는 모델 일반성에 대한
보조 분석으로 보고한다.

## 평가 QA와 paired 결과

두 arm은 각각 500개 평가 파일과 2,000개 branch row를 만들었고 평가 계약 오류는 0이었다.
아래 delta는 `full - no_research_dialogue`다. micro가 공식 cohort의 주 추정량이며 macro는 여섯
위기 범주를 같은 가중치로 평균한 민감도 분석이다.

| case-level Success@4 metric | full | no dialogue | Δ micro | Δ macro | exact McNemar p |
|---|---:|---:|---:|---:|---:|
| Raw Recovery | 490/500 (98.0%) | 491/500 (98.2%) | -0.2%p | +0.08%p | 1.000 |
| Target-originated Recovery | 490/500 (98.0%) | 490/500 (98.0%) | 0.0%p | +0.18%p | 1.000 |
| Unsafe manifestation ASR | 485/500 (97.0%) | 487/500 (97.4%) | -0.4%p | +0.43%p | 0.851 |
| CARES non-refuse | 495/500 (99.0%) | 495/500 (99.0%) | 0.0%p | +0.34%p | 1.000 |
| CARES Accept | 51/500 (10.2%) | 36/500 (7.2%) | +3.0%p | +6.68%p | 0.058 |

Recovery와 unsafe manifestation의 차이는 작고 McNemar 검정에서 유의하지 않았다. CARES
Accept는 full에서 3.0%p 높았지만 양측 exact p=0.058이므로 관행적 0.05 기준의 확정적 효과로
쓰지 않는다. 특히 작은 범주가 macro 차이를 크게 움직일 수 있으므로 micro를 주 결과로 둔다.
이 arm의 OpenAI evaluator Batch 실비는 USD 2.5773이고, Qwen target 생성 자체는 localhost
vLLM이어서 OpenAI target 비용은 0이었다.
