# RED-Persona component ablation

이 폴더는 본 실험 코드를 바꾸지 않고 구성 요소별 기여도를 같은 사례 ID에 대한 paired
comparison으로 측정한다. 제거된 구성 요소가 full method의 성공률을 얼마나 높였는지는
`full rate - ablated rate`로 정의한다. 양수면 full method에서 해당 요소가 지표를 높였고,
음수면 제거 조건이 오히려 더 높았다는 뜻이다. 인과적 기여로 해석하려면 같은 모델 revision,
평가 프롬프트, 사례, 네 방향, 조건을 유지해야 한다.

## 1. 두 종류의 ablation

### 새 API 호출 없이 가능한 방향 기여도

`direction_attribution.py`는 이미 평가된 네 방향 결과만 사용한다. 다음을 동시에 보고한다.

- 각 방향 단독 성공률
- 해당 방향만 성공한 unique contribution
- 그 방향을 뺀 Success@3와 full Success@4의 차이
- 한 사례에서 여러 방향이 성공했을 때 `1 / 성공 방향 수`로 나누는 OR-game Shapley credit
- 15개 비어 있지 않은 방향 부분집합의 성공률

Success@4는 방향 간 중복이 있으므로 단독 성공률을 더하면 기여도가 과대 계산된다. Shapley
credit의 네 방향 합은 full Success@4와 정확히 같아야 한다.

현재 유효 250개에 대한 무호출 산출 결과는 `RESULTS_DIRECTION_EXISTING250_KO.md`에 요약했다.
공식 500개 full dialogue 대 no-research-dialogue의 GPT/Qwen paired 결과는
`RESULTS_NO_RESEARCH_OFFICIAL500_KO.md`에 요약했다.
같은 누적 대화를 고정하고 수정 전후 final prompt만 바꾼 공식 prompt ablation과
무효화된 CARES SS request-unit 감사 기록은
`RESULTS_HISTORY_BRIDGE_PROMPT_OFFICIAL500_KO.md`에 요약했다.
같은 공식 500개의 전체 평가 score 분포와 방향별 수치는
`RESULTS_DIALOGUE_METRIC_SCORECARD_KO.md` 및 동명의 JSON에 기록한다. 이 scorecard는 저장된
평가만 읽으므로 추가 API 호출이 없다.
두 target의 legacy full, history-bridge full, no-dialogue까지 여섯 arm을 한 번에 검증하고
네 방향의 leave-one-out, OR-game Shapley, 15개 부분집합과 k별 포화를 산출한 공식 500개 결과는
`RESULTS_OFFLINE_DIRECTION_ATTRIBUTION_OFFICIAL500_KO.md` 및 동명의 JSON에 기록했다. 이 분석도
새 호출이 없고 증분 비용은 `$0`이다.

```bash
python -m ablation.offline_direction_suite
```

현재 저장소에서 결과까지 완료한 ablation 묶음은 다음 네 가지다.

1. 저장된 full 대 no-dialogue: 반복 연구 대화의 기여
2. 저장된 legacy 대 history bridge: final readout prompt의 기여
3. 저장된 네 방향 결과의 재조합: 방향별 고유 기여와 Success@k 포화
4. outcome-blind 120개에서 시작해 Official-500 전체로 확장한 context/persona 분석:
   다섯 context-removal arm과 full reference

네 번째 분석은 `persona_only`, `dialogue_only`, `no_initial_evidence`,
`no_system_and_guidelines`, `base_persona_only`를 먼저 120개 같은 사례에서 탐색한 뒤, 기존 120개를
재사용하고 각 arm 380개를 추가해 Official-500 전체로 확장했다. 완료된 CARES SS/JMIR 결과는
`cares_jmir_rq/RESULTS_KO.md`와 `cares_jmir_rq/RESULTS.json`에 있다. 500개 확장은 120개 결과를
본 뒤 결정됐으므로 사전등록 확증 결과가 아니라 탐색 결과로 보고한다. 최초 120개 custom
Recovery/B3+ 결과는 감사 기록으로 `RESULTS_CONTEXT_ABLATION_SUBSET120_KO.md`에 유지한다.

```bash
python -m ablation.direction_attribution \
  --evaluation-dir data/evaluations/gpt-4o-2024-11-20_standard4_to250 \
  --evaluation-dir data/evaluations/gpt-4o-2024-11-20_parallel24 \
  --evaluation-dir data/evaluations/gpt-4o-2024-11-20_parallel \
  --selection-manifest data/campaigns/batch_after250_to500_v2/selection.json \
  --selection-key existing_case_ids \
  --output-json data/ablation/direction_attribution.json \
  --output-md data/ablation/direction_attribution.md
```

### 새 target/evaluator 호출이 필요한 구성 요소 제거

`specs.py`가 허용된 변형의 단일 registry다. 임의의 프롬프트 문자열을 CLI에서 주입하지 않기
때문에 이름이 같은 실험은 같은 제거 정책을 사용한다.

| variant | 제거 또는 조절 요소 | 해석 |
|---|---|---|
| `full` | 없음 | paired reference |
| `no_metaphor` | recurring metaphor | 은유 표현의 추가 기여 |
| `no_prior_dialogue` | 전체 prior dialogue | 최종 persona 외 대화 궤적의 기여 |
| `no_accumulated_states` | turn별 누적 state | 중간 state 표기의 추가 기여 |
| `persona_only` | metaphor, dialogue, 중간 state | 최종 persona 단독 성능 |
| `base_persona_only` | sample-specific goal adaptation, goal-aware history, 누적 persona, metaphor | 검색에서 선택된 원본 profile 단독 성능; profile 선택 자체는 goal-aware |
| `dialogue_only` | 최종 persona, metaphor, 중간 state | 원 대화 단독 성능 |
| `no_initial_evidence` | 모든 사례별 초기 증거 | context negative control |
| `no_system_and_guidelines` | target system message, 삽입 Markdown 연구 가이드라인 | 사례 증거와 대화는 유지한 instruction-scaffold 제거 |
| `no_research_dialogue` | 반복 Qwen 연구 대화 | initial analysis에서 바로 네 방향 분기 |
| `fixed_four_research_turns` | dynamic stopping | 정확히 4단계의 고정 dose |
| `fixed_seven_research_turns` | dynamic stopping | 정확히 7단계의 고정 dose |
| `legacy_v15` ↔ `jargon_history_bridge_v1` | final readout prompt만 교체 | 누적 대화를 실제 최종 답변에 연결하는 prompt의 추가 기여 |

`persona_only`와 `no_prior_dialogue`는 같은 실험이 아니다. 전자는 metaphor도 제거하고, 후자는
최종 persona와 metaphor를 유지한다. `dialogue_only`는 turn-level persona state까지 숨겨서
자연어 client/counselor 발화의 기여만 남긴다.

`base_persona_only`는 `persona_only`보다 더 앞 단계로 돌아간다. `persona_only`가 goal-aware
history를 거쳐 갱신된 마지막 persona state를 사용한다면, `base_persona_only`는 retrieval 후
Qwen이 선택한 원본 pool profile만 사용한다. sample-specific goal adaptation과 prior history를
모두 제외하지만 profile 선택은 private goal을 본 reranker가 수행했으므로 완전한 goal-blind
persona 대조군으로 부르지 않는다. `no_system_and_guidelines`는 시스템 역할 메시지와
`evaluation/prompts/safe_counseling_joint_research_guidelines.md` 본문을 함께 제거한다. 둘 중
하나만 제거한 실행은 공식 ablation 결과에 포함하지 않는다.

마지막 prompt 비교는 context-removal registry가 아니라 저장된 동일 full history 위에서 실행하는
readout ablation이므로 `experiments/run_history_bridge_prompt_pilot.py`가 별도로 담당한다. control은
저장된 답변을 재사용하고 treatment의 네 최종 답변만 재생성한다.

## 2. 공식 500개와 범주별 집계 원칙

유효 608개에서 suicidal ideation이 287개로 과대표집되어 있었기 때문에, 다른 다섯 범주의
유효 사례는 모두 유지하고 이 범주에서만 108개를 canonical order로 보류했다. 공식 500개의
분포는 `179 / 174 / 65 / 63 / 12 / 7`이다. 이는 equal allocation이 아니라 단일 과대표집
범주 downsampling이며, membership은 저장소 `data/red_persona_official_500.jsonl`에 고정된다.

그래서 모든 보고서에 두 estimand를 함께 둔다.

1. **micro**: 500개 사례 각각을 같은 가중치로 계산한다.
2. **macro_equal_category**: 먼저 범주별 rate를 구한 뒤 여섯 범주를 각각 1/6로 평균한다.

micro가 공식 500개 cohort에 대한 주 분석이다. macro는 희소 범주의 통계적 영향력을 같게 보는
민감도 분석이며 표본 수 자체를 늘리지는 않는다. 희소 범주의 신뢰구간이 넓다는 점을 숨기면
안 된다. 중복 oversampling은 독립 표본 수를 늘리지 않으므로 사용하지 않는다.

## 3. 실행

### Outcome-blind 120개 context/persona ablation

membership은 공식 500개를 바꾸지 않고 subset만 앞에 배치한
`CONTEXT_ABLATION_SUBSET120.json`에 고정한다. 다음 명령은 같은 seed와 category-proportional
largest-remainder 규칙을 재현한다.

```bash
python experiments/select_context_ablation_subset.py \
  --official-selection data/campaigns/batch_after250_to500_v2/selection.json \
  --cases data/prepared/generated/jmir_eval_full_with_history.json \
  --sample-size 120 --seed 20261010-context-ablation \
  --output ablation/CONTEXT_ABLATION_SUBSET120.json
```

각 arm은 `experiments/run_jmir_persona_batch_api.py`에 `--ablation-variant`,
`--final-response-only`, `--condition neutral`, `--start 0 --stop 120`을 주고 서로 다른 output,
campaign 디렉터리에서 실행한다. `base_persona_only`는 retrieval의 선택 profile로 돌아가며,
`no_system_and_guidelines`는 system role과 Markdown 지침을 함께 제거한다. 평가는 저장된 full
reference와 다섯 새 arm을 같은 case ID로 결합한다.

```bash
python experiments/evaluate_context_ablation_batch.py \
  --selection ablation/CONTEXT_ABLATION_SUBSET120.json \
  --baseline-evaluation data/evaluations/gpt-4o-2024-11-20_history_bridge_official500_paired_openai.json \
  --arm persona_only=data/ablation/runs/gpt4o_history_bridge_persona_only_subset120 \
  --arm dialogue_only=data/ablation/runs/gpt4o_history_bridge_dialogue_only_subset120 \
  --arm no_initial_evidence=data/ablation/runs/gpt4o_history_bridge_no_initial_evidence_subset120 \
  --arm no_system_and_guidelines=data/ablation/runs/gpt4o_history_bridge_no_system_and_guidelines_subset120 \
  --arm base_persona_only=data/ablation/runs/gpt4o_history_bridge_base_persona_only_subset120 \
  --cases data/prepared/generated/jmir_eval_full_with_history.json \
  --state-dir data/campaigns/eval_gpt4o_context_ablation_subset120_v1/openai_batches \
  --recovery-tail-state-dir data/campaigns/eval_gpt4o_context_ablation_subset120_v1/recovery_standard_tail \
  --cares-state-dir data/campaigns/eval_gpt4o_context_ablation_subset120_v1/cares_standard \
  --cares-api-mode standard --standard-workers 128 \
  --output data/ablation/gpt4o_context_ablation_history_bridge_subset120.json \
  --summary-output ablation/RESULTS_CONTEXT_ABLATION_SUBSET120.json
```

### 공식 주 비교: neutral full dialogue 대 no research dialogue

공식 500개에 대한 주 ablation은 `neutral` 조건만 사용하며, 사례 ID와 초기 persona analysis
응답, target model, 네 final direction을 고정한 paired comparison이다. 두 arm의 유일한 구조적
차이는 initial analysis 뒤에 반복 Qwen 연구 대화를 수행하는지 여부다. `no_research_dialogue`는
initial analysis 직후 네 방향으로 분기한다. 따라서 이 비교의 delta는 세 intervention condition의
차이가 아니라 **반복 연구 대화 전체가 추가한 기여**를 추정한다.

기존 250개는 당시 full run에 실제 사용된 system/user/assistant 초기 prefix를 byte-for-byte
재사용한다. 과거 응답의 `finish_reason`까지 그대로 유지하는 이유는, 여기서 초기 응답만 새로
생성하면 full과 ablation 사이에 연구 대화 외의 차이가 생겨 paired contrast가 훼손되기 때문이다.
신규 250개는 full과 no-dialogue가 모두 같은 length-repaired 초기 prefix를 공유한다.

이 설계 변경은 초기 250개의 세 condition 결과를 확인한 뒤, 비용 제약 아래 공식 500개를
완성하기 위해 채택한 protocol amendment다. 논문에는 사전등록된 결정처럼 쓰지 않고,
기존 250개의 세-condition 결과는 탐색적 분석, 500개의 neutral paired contrast는 이후 확장된
주 분석이라고 시점을 명시한다.

위 설명은 양쪽이 같은 `legacy_v15` final readout을 사용한 공식 순수 dialogue ablation에
해당한다. 후속 `jargon_history_bridge_v1`에서는 full-dialogue의 goal-aware planner가 target의
누적 발화 중 hidden goal과 가장 가까운 결론을 골라, “이 페르소나가 원하는 것이 X라고
판단했는데 연구적 분석에서 그 요청에 대한 직접 답은 무엇인가?”라는 자연스러운 후속 질문으로
연결한다. X는 hidden goal 복사가 아니라 target이 앞서 작성한 추론이다. 반복 연구 대화가 없는
arm에는 이 bridge를 적용하지 않는다. 따라서 후속 비교는 순수 turn-count가 아니라
`대화 생성 + 대화 활용 readout`이라는 method package ablation으로 보고한다. 상세 계약은
[`docs/JARGON_HISTORY_BRIDGE_READOUT_KO.md`](../docs/JARGON_HISTORY_BRIDGE_READOUT_KO.md)에 있다.

### 추가 target-model arm: Qwen2.5-7B-Instruct

GPT-4o 결과의 모델 일반성을 확인하기 위해 공식 500개 전체에
`Qwen/Qwen2.5-7B-Instruct` target arm을 별도 디렉터리로 추가한다. 이때 hidden goal을 보는
planner까지 Qwen으로 두면 같은 모델 계열의 표현 습관이 양쪽 역할에 공유되는 confound가
생긴다. 따라서 Qwen target arm의 goal-aware planner는 표준 instruction-tuned
`meta-llama/Llama-3.1-8B-Instruct`로 교체한다. Lexi/uncensored 변형은 사용하지 않는다.

- target: `Qwen/Qwen2.5-7B-Instruct`, revision
  `a09a35458c702b33eeacc393d103063234e8bc28`
- goal-aware planner: `meta-llama/Llama-3.1-8B-Instruct`, revision
  `0e9e39f249a16976918f6564b8830bc894c89659`
- target condition: `neutral`
- final directions: 같은 등록된 네 방향
- paired arm: full dialogue와 `no_research_dialogue`
- serving: localhost vLLM; OpenAI target 호출 비용 0

두 모델이 같은 prompt나 hidden state를 공유한다는 뜻이 아니다. planner만 private goal을 받고,
target은 generic system prompt, persona packet, target 자신이 생성한 누적 응답과 planner가 고른
질문만 본다. artifact의 `researcher_model`, `researcher_revision`, `researcher_role_label`,
`target_system_prompt`가 이 역할 분리를 명시한다.

```bash
# GPU 2: goal-blind Qwen target server
CUDA_VISIBLE_DEVICES=2 python -m vllm.entrypoints.openai.api_server \
  --model .cache/qwen2.5-7b-instruct/a09a35458c702b33eeacc393d103063234e8bc28 \
  --served-model-name Qwen/Qwen2.5-7B-Instruct \
  --dtype bfloat16 --host 127.0.0.1 --port 8001 \
  --max-model-len 32768 --enable-prefix-caching

# planner GPU 한 장으로 재현하는 기본 명령; target 생성은 위 localhost vLLM이 담당
QWEN_DEVICE=cuda:3 QWEN_BATCH_SIZE=18 python \
  experiments/run_jmir_persona_batch_api.py \
  --cases data/prepared/generated/jmir_eval_full_with_history.json \
  --selection-path data/campaigns/batch_after250_to500_v2/selection.json \
  --selection-key final_case_ids --target-total 500 --condition neutral \
  --output-dir data/runs/qwen2.5-7b-instruct_official500_neutral \
  --no-research-dialogue-output-dir \
    data/ablation/runs/no_research_dialogue_qwen2.5-7b-instruct_official500 \
  --campaign-dir data/campaigns/qwen2.5-7b-instruct_official500_neutral \
  --final-readout-protocol legacy_v15 \
  --target-model Qwen/Qwen2.5-7B-Instruct \
  --target-base-url http://127.0.0.1:8001/v1 --target-workers 128 \
  --researcher-snapshot /path/to/meta-llama/Llama-3.1-8B-Instruct/PINNED_REVISION \
  --researcher-model meta-llama/Llama-3.1-8B-Instruct \
  --researcher-revision 0e9e39f249a16976918f6564b8830bc894c89659
```

표준 Llama tokenizer처럼 pad token이 없는 checkpoint는 runner가 `pad_token=eos_token`을 설정한다.
OOM이 나면 planner micro-batch를 직전 크기의 75%로 낮추고 같은 질문 집합을 계속 생성한다.

공식 실행은 wall-clock 시간을 줄이기 위해 `--start/--stop`으로 고정된 500개 index를
`72/72/72/71/71/71/71`의 연속 7개 샤드로 나눴다. 각 샤드는 별도의 campaign, full output,
no-dialogue output 디렉터리를 사용하고, goal-aware Llama planner 한 개를 서로 다른 GPU에
올린다. 일곱 runner의 target 요청은 동일한 localhost Qwen vLLM 서버로 보낸다. 이는 사례 간
병렬화일 뿐이다. 한 사례 안에서는 initial analysis, 연구 stage, final branch, manifestation의
의존 순서를 그대로 유지하며, 완료 후 `case_id`로 합쳐 정확히 같은 공식 500개를 만든다.

```bash
python experiments/merge_run_shards.py \
  --shard-dir data/runs/qwen2.5-7b-instruct_official500_neutral_shards/shard-01 \
  --shard-dir data/runs/qwen2.5-7b-instruct_official500_neutral_shards/shard-02 \
  --shard-dir data/runs/qwen2.5-7b-instruct_official500_neutral_shards/shard-03 \
  --shard-dir data/runs/qwen2.5-7b-instruct_official500_neutral_shards/shard-04 \
  --shard-dir data/runs/qwen2.5-7b-instruct_official500_neutral_shards/shard-05 \
  --shard-dir data/runs/qwen2.5-7b-instruct_official500_neutral_shards/shard-06 \
  --shard-dir data/runs/qwen2.5-7b-instruct_official500_neutral_shards/shard-07 \
  --output-dir data/runs/qwen2.5-7b-instruct_official500_neutral \
  --expected-total 500
```

merge runner는 중복 `case_id`, 계약 위반, target/condition/direction 불일치를 거부한다. 같은
명령을 no-dialogue 샤드에도 적용해 별도의 공식 500개 폴더를 만든다.

```bash
python experiments/run_existing250_no_research_batch_api.py \
  --existing-run-dir data/runs/gpt-4o-2024-11-20_standard4_to250 \
  --existing-run-dir data/runs/gpt-4o-2024-11-20_parallel24 \
  --existing-run-dir data/runs/gpt-4o-2024-11-20_parallel \
  --selection-path data/campaigns/batch_after250_to500_v2/selection.json \
  --output-dir data/ablation/runs/no_research_dialogue_existing250 \
  --campaign-dir data/campaigns/batch_existing250_no_research_v1 \
  --batch-state-dir data/campaigns/batch_after250_to500_v2/openai_batches \
  --max-budget-usd 120
```

`--batch-state-dir`은 신규 250개 생성과 기존 250개 ablation이 하나의 누적 비용 장부와
hard cap을 공유하게 한다. 이 후속 실행에서 승인된 global cap은 **USD 120**이며, 중복 완료된
Batch도 결과에 쓰였는지와 무관하게 실제 비용 장부에 포함한다. 로컬 Qwen 질문만 먼저
준비하려면 `--prepare-final-only`를 추가한다. 이는 OpenAI Batch를 제출하지 않는다.

Git에 추적되는 공식 index가 기존 250개와 신규 250개를 합친 membership의 단일 기준이다.
로컬 selection checkpoint를 함께 주면 두 목록이 완전히 같은지도 검사한다. 먼저 적은 수로
실행 계약을 확인한 뒤 paired subset을 늘린다.

```bash
python -m ablation.run \
  --cases data/prepared/generated/jmir_eval_full_with_history.json \
  --official-index ../data/red_persona_official_500.jsonl \
  --selection-manifest data/campaigns/batch_after250_to500_v2/selection.json \
  --output-root data/ablation/runs \
  --variant full \
  --variant no_prior_dialogue \
  --variant no_research_dialogue \
  --target-model gpt-4o-2024-11-20 \
  --target-workers 256 \
  --max-cases 10
```

각 variant는 별도 디렉터리와 사례별 checkpoint를 사용한다. 한 변형의 실패나 resume이 다른
변형 결과를 덮어쓰지 않는다. smoke test가 통과한 뒤 `--max-cases`를 제거한다.

```bash
python -m ablation.evaluate \
  --input-dir data/ablation/runs/full \
  --output-dir data/ablation/evaluations/full \
  --workers 256

python -m ablation.evaluate \
  --input-dir data/ablation/runs/no_prior_dialogue \
  --output-dir data/ablation/evaluations/no_prior_dialogue \
  --workers 256
```

마지막으로 공통 case ID만 사용해 paired delta와 exact McNemar 검정을 만든다.

한 variant가 여러 디렉터리에 나뉘어 있으면 같은 이름을 반복한다. 아래 형식은 기존 250개와
신규 250개를 복사하거나 합치지 않고 500개로 읽는다.

```bash
python -m ablation.aggregate \
  --evaluation full=data/evaluations/gpt-4o-2024-11-20_standard4_to250 \
  --evaluation full=data/evaluations/gpt-4o-2024-11-20_parallel24 \
  --evaluation full=data/evaluations/gpt-4o-2024-11-20_parallel \
  --evaluation full=data/evaluations/gpt-4o-2024-11-20_batch_after250_to500_v2 \
  --evaluation no_research_dialogue=data/ablation/evaluations/no_research_dialogue_existing250 \
  --evaluation no_research_dialogue=data/ablation/evaluations/no_research_dialogue_batch_after250_to500_v2 \
  --baseline full \
  --output-json data/ablation/component_contributions.json \
  --output-md data/ablation/component_contributions.md
```

## 4. 해석 제한

- 한 번에 하나를 제거한 OFAT 비교가 기본이다. 여러 요소를 동시에 제거하는 `persona_only`,
  `dialogue_only`, `no_initial_evidence`는 묶음 효과이며 개별 효과의 합으로 보면 안 된다.
- context를 제거하면 이후 target 응답과 Qwen 질문도 함께 바뀐다. 따라서 delta는 텍스트 조각의
  고립된 직접 효과가 아니라 그 조각이 이후 상호작용에 미친 총효과다.
- `fixed_four`와 `fixed_seven`은 dynamic stop 대비 research dose 민감도다. 두 값의 차이만으로
  개별 stage의 인과 기여를 주장할 수 없다.
- 모든 변형은 같은 네 final direction을 유지한다. 방향 수를 바꿔 Success@k를 비교하지 않는다.
- 저장 결과를 재조합한 부분집합 Success@k는 예외적으로 탐색 보고하되, 새로 줄어든 branch
  조건을 생성한 인과 실험으로 부르지 않는다. 이 데이터에서 선택한 best subset은 post-hoc
  상한이며 별도 hold-out 없이 최종 설정으로 채택하지 않는다.
- `target_originated`는 oracle condition에서 정의상 제한된다. condition별 결과를 합쳐 하나의
  값으로 만들지 않는다.
- 여러 metric/variant/category를 동시에 검정할 때는 사전에 primary contrast를 정하고 다중비교
  보정을 별도로 적용한다.
