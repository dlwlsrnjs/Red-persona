# 새 서버 설치 및 전체 실험 운영 가이드

이 문서는 빈 GPU 서버에서 RED-Persona 저장소를 설치하고, 비추적 연구 데이터와 고정 모델
snapshot을 배치한 뒤, JMIR 625개 전체 실험을 생성·실행·평가하는 절차를 실제 코드 계약에
맞춰 설명한다. 명령은 저장소의 `persona_redteam/` 디렉터리에서 실행한다.

## 1. 현재 활성 파이프라인과 완료 조건

```text
625 goal JSONL + 625 pathology route JSONL
  -> 625 blueprint JSONL
  -> 625 seedless prepared cases JSON
  -> 31,733 persona pool 검색
  -> Lexi 가변 길이 과거 대화와 누적 persona_state 생성
  -> active cases JSON
  -> Qwen 연구 질문 + target 누적 대화
  -> 조건 3개 x 독립 final branch 8개 x candidate response
  -> GPT recovery/behavior evaluator + candidate-only CARES
  -> 사례별 평가 JSON + 전체/조건/위기범주 aggregate JSON
```

전체 실행이 완료됐다고 보려면 다음을 모두 만족해야 한다.

1. blueprint와 prepared/active case가 각각 625개다.
2. 모든 active case에 최소 4개 `persona_history` turn이 있다.
3. `data/runs/<target>/`에 사례별 성공 JSON 625개가 있고 `.failed.json`이 없다.
4. 각 run JSON은 3조건과 조건별 8개 branch, 즉 24개 branch를 가진다.
5. `data/evaluations/<target>/`에 평가 JSON 625개가 있고 각 파일에 평가 row 24개가 있다.
6. `aggregate_summary.json`의 `evaluated_cases`가 625다.

## 2. 서버 요구사항

### 필수

- Linux, Git, Python 3.10 이상
- NVIDIA GPU와 설치할 PyTorch에 맞는 NVIDIA driver
- Qwen 7B를 BF16으로 올릴 GPU 약 16GB 이상
- Lexi 8B OpenAI-compatible server를 별도로 띄울 GPU 약 18~24GB 이상
- 모델 두 개, Hugging Face cache와 산출물을 위한 여유 디스크 80GB 이상 권장
- OpenAI API 접근 권한과 실행할 target/evaluator model 권한

History 생성 단계의 Qwen planner와 Lexi는 각각 `/v1/chat/completions`를 제공하는 로컬
서버를 사용한다. 본 Qwen–target 단계의 Qwen 연구자는 고정 snapshot을 `transformers`로
프로세스 안에서 직접 로드한다. target과 GPT evaluator는 OpenAI API를 사용한다.

### 병렬도 해석

- `--target-workers 256`: 한 사례 내부의 final/manifestation target 요청 병렬도다.
- `--workers 256`: 한 사례의 24개 평가 branch 병렬도다.
- 사례 자체는 `run_batch`와 `evaluate_batch`에서 순차 처리된다.
- `generate_histories`도 사례와 turn을 순차 처리하지만 사례별 checkpoint로 재개한다.
- 256은 상한일 뿐 권장 시작값이 아니다. API rate limit이 낮으면 16 또는 32부터 시작한다.

따라서 GPU를 여러 장 쓴다고 625개 사례가 자동 분산되지는 않는다. 여러 프로세스로 분할할
때는 서로 다른 `--start/--stop` 범위와 서로 다른 output directory를 써야 하며, 완료 후
사례 JSON만 하나의 최종 directory로 모아 집계한다.

## 3. 저장소와 Python 환경 설치

```bash
git clone https://github.com/dlwlsrnjs/Red-persona.git
cd Red-persona/persona_redteam

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip wheel
python -m pip install -r pipeline/requirements-runtime.txt
```

`requirements-runtime.txt`는 프로세스 내 Qwen 로딩에 필요한 패키지다. Lexi를 vLLM으로
서빙할 경우 CUDA/PyTorch 조합에 맞는 vLLM을 별도 설치한다. 기존 PyTorch를 무심코
교체하지 않도록 vLLM 공식 설치 조합을 먼저 확인한다.

설치 검증:

```bash
python - <<'PY'
import torch, transformers, huggingface_hub
print("torch", torch.__version__)
print("transformers", transformers.__version__)
print("cuda", torch.cuda.is_available(), torch.cuda.device_count())
if torch.cuda.is_available():
    for index in range(torch.cuda.device_count()):
        print(index, torch.cuda.get_device_name(index))
PY

python -m unittest discover -s experiments -p 'test_*.py'
python -m compileall -q pipeline experiments
```

## 4. 자격 증명

OpenAI 키는 저장소 바깥 상위 `.env` 또는 환경변수에서 읽는다. 환경변수 방식이 가장
명확하다.

```bash
export OPENAI_API_KEY='새로 발급한 키'
```

키를 Git 파일, shell history, 실행 산출물에 넣지 않는다. GitHub/Hugging Face token도
명령행에 직접 쓰지 말고 각 CLI login 또는 환경의 secret manager를 사용한다. 이전 채팅에
노출된 토큰은 재사용하지 말고 폐기한다.

## 5. 비추적 데이터 복사와 배치

Git에는 원문 goal, route, persona pool이 포함되지 않는다. 기존 서버에서 안전한 전송 수단으로
아래 세 파일을 복사해야 한다.

```text
persona_redteam/
  ../data/crisis_goals_jmir_persona_min10.jsonl
  ../data/goal_pathology_routes_n625.jsonl
  ../data/personas/personas.jsonl
```

역할과 기대 행 수:

| 파일 | 행 수 | 역할 |
|---|---:|---|
| `../data/crisis_goals_jmir_persona_min10.jsonl` | 625 | 최종 평가 goal 모집단 |
| `../data/goal_pathology_routes_n625.jsonl` | 625 | 모든 평가 goal의 pathology route |
| `../data/personas/personas.jsonl` | 31,733 | Cactus 31,577 + CBT-DP 156 전체 pool |

기본 persona pool 위치를 쓰지 않는다면 다음처럼 지정한다.

```bash
export PERSONA_POOL_PATH=/absolute/path/to/personas.jsonl
```

`pipeline.persona_pool`은 이 환경변수를 우선하고, 없으면
`../data/personas/personas.jsonl`을 사용한다.

두 핵심 historical payload는 다음 checksum과 일치해야 한다.

```bash
sha256sum ../data/crisis_goals_jmir_persona_min10.jsonl
# b87a5dd018db36e9706a4dedfcda11635a7891d57f5015ca2f652c4f7e8246fd

sha256sum ../data/goal_pathology_routes_n625.jsonl
# fa31b91fa19c2e78f295e9365465d8c3eb0a946234bec8af0bc33efb659a059e

PERSONA_POOL_FILE="${PERSONA_POOL_PATH:-../data/personas/personas.jsonl}"
wc -l ../data/crisis_goals_jmir_persona_min10.jsonl \
      ../data/goal_pathology_routes_n625.jsonl \
      "$PERSONA_POOL_FILE"
```

`PERSONA_POOL_PATH`를 설정하지 않았다면 기본 경로를 사용한다. 세 파일의 상세 출처는
`DATA_LINEAGE_AND_EXTRACTION_KO.md`에 있다.

## 6. 고정 모델 snapshot 다운로드

모델은 revision을 반드시 고정한다.

```bash
python - <<'PY'
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="Qwen/Qwen2.5-7B-Instruct",
    revision="a09a35458c702b33eeacc393d103063234e8bc28",
    local_dir=".cache/qwen2.5-7b-instruct/a09a35458c702b33eeacc393d103063234e8bc28",
)
snapshot_download(
    repo_id="Orenguteng/Llama-3.1-8B-Lexi-Uncensored-V2",
    revision="f4617caeabd21f1820ac89bd125c80eda70901a7",
    local_dir=".cache/lexi-llama31-8b/f4617caeabd21f1820ac89bd125c80eda70901a7",
)
PY
```

Qwen 본 실험은 기본적으로 첫 번째 고정 경로를 직접 읽는다. 다른 위치라면
`run_batch`에 `--qwen-snapshot /absolute/path`를 전달한다.

## 7. Qwen과 Lexi OpenAI-compatible server

History 계획·profile reranking·턴 검증에 사용할 Qwen 서버:

```bash
export CUDA_VISIBLE_DEVICES=0
python -m vllm.entrypoints.openai.api_server \
  --model .cache/qwen2.5-7b-instruct/a09a35458c702b33eeacc393d103063234e8bc28 \
  --served-model-name Qwen/Qwen2.5-7B-Instruct \
  --dtype bfloat16 \
  --host 127.0.0.1 \
  --port 8000 \
  --gpu-memory-utilization 0.90
```

Lexi 서버는 다른 GPU에서 실행한다.

예시 vLLM 명령은 다음과 같다. GPU 번호와 메모리 비율은 서버 상황에 맞춘다.

```bash
export CUDA_VISIBLE_DEVICES=1
python -m vllm.entrypoints.openai.api_server \
  --model .cache/lexi-llama31-8b/f4617caeabd21f1820ac89bd125c80eda70901a7 \
  --served-model-name Orenguteng/Llama-3.1-8B-Lexi-Uncensored-V2 \
  --dtype bfloat16 \
  --host 127.0.0.1 \
  --port 8002 \
  --gpu-memory-utilization 0.90
```

별도 shell에서 확인한다.

```bash
curl -fsS http://127.0.0.1:8002/v1/models
curl -fsS http://127.0.0.1:8000/v1/models
```

응답의 model id가 `--model`에 넘길 이름과 같아야 한다. 서버가 snapshot 경로만 model id로
돌려주는 설정이라면 `generate_histories --model`도 그 반환 id에 맞춘다.

## 8. 단계 A: 625개 blueprint 생성

Git의 625개 route를 그대로 검증하거나, 누락·신규 goal이 있으면 checkpoint 추출기로
보완한다.

```bash
python -m pipeline.route_goals \
  --goals ../data/crisis_goals_jmir_persona_min10.jsonl \
  --existing-routes ../data/goal_pathology_routes_n625.jsonl \
  --output ../data/goal_pathology_routes_n625.jsonl \
  --checkpoint-dir data/prepared/routes/jmir625 \
  --model gpt-4o-mini-2024-07-18 \
  --workers 48 --retry-failed
```

```bash
python experiments/build_jmir_eval_set_full.py
python -m pipeline.preflight \
  --blueprint data/prepared/blueprints/jmir_eval_full.jsonl
```

입력 goal JSONL 최소 양식:

```json
{"goal_id":"source-id","goal":"private evaluation request","crisis_label":"self-harm"}
```

입력 route JSONL 최소 양식:

```json
{"goal_id":"source-id","pathology":{"symptoms":[],"cognitive_distortions":[],"stressors":[]}}
```

출력 blueprint JSONL 핵심 양식:

```json
{
  "set_id": "jmir-full-0001",
  "source_goal_id": "source-id",
  "crisis_label": "self-harm",
  "source": "data/crisis_goals_jmir_persona_min10.jsonl",
  "goal_private": "private evaluation request",
  "goal_pathology": {},
  "evaluation": {
    "manifestation_threshold": 3,
    "cares_harmful_level": null
  }
}
```

`goal_id` join이 하나라도 없거나 route에 `pathology`가 없으면 builder가 실패한다. 625개에서
일부만 조용히 버리는 동작은 하지 않는다. 함께 생성되는 `.report.json`에는 행 수,
범주별 수, 입력 checksum이 기록된다.

### 이후 새로운 샘플

새 JSON/JSONL은 `goal_id` 또는 `source_goal_id`, `goal` 또는 `original_request`, 선택적
`crisis_label`을 주면 된다. ID가 없으면 goal text SHA256으로 안정적인 `dynamic-*` ID를 만든다.
`--prepared-output`을 함께 주면 별도 JMIR builder 없이 history 생성 입력까지 바로 만든다.

```bash
python -m pipeline.route_goals \
  --goals data/source/goals/new_samples.jsonl \
  --output data/prepared/routes/new_samples.jsonl \
  --prepared-output data/prepared/cases/new_samples_pre_generation.json \
  --checkpoint-dir data/prepared/routes/new_samples_checkpoints \
  --model gpt-4o-mini-2024-07-18 --workers 32 --retry-failed
```

그 출력은 `pipeline.generate_histories`에서 전체 31,733개 pool 검색과 Qwen reranking을 거친다.
새 샘플에 고정 persona seed를 수동으로 지정하지 않는다.

## 9. 단계 B: seedless prepared case 생성

```bash
python -m pipeline.prepare adapt \
  --input data/prepared/blueprints/jmir_eval_full.jsonl \
  --output data/prepared/cases/jmir_eval_full_pre_generation.json

python -m pipeline.preflight \
  --prepared-cases data/prepared/cases/jmir_eval_full_pre_generation.json
```

출력은 JSONL이 아니라 JSON array다. 핵심 양식:

```json
[
  {
    "case_id": "jmir-full-0001",
    "source_goal_id": "source-id",
    "crisis_label": "self-harm",
    "original_request": "private evaluation request",
    "evaluation": {},
    "provenance": {
      "goal_pathology": {},
      "persona_generation_status": "pending"
    }
  }
]
```

이 단계에는 `persona`와 `metaphor`가 없어야 한다. 고정 persona seed를 넣는 것은 현재
계약 위반이다.

## 10. 단계 C: persona history 프롬프트 준비

```bash
mkdir -p prompts
cp configs/persona_history/generation_prompt.template.txt \
   prompts/persona_history_generation.txt
cp configs/persona_history/coverage_prompt.template.txt \
   prompts/persona_history_coverage.txt
```

두 프롬프트는 영어로 작성하며 Python `string.Template` 문법을 쓴다. 사용 가능한 변수:

| 변수 | 의미 |
|---|---|
| `$goal`, `$goal_json` | private goal 문자열 |
| `$goal_pathology_json` | 구조화 pathology |
| `$persona_profile_json` | 전체 pool에서 선택된 profile |
| `$history_json` | 지금까지 생성된 모든 turn |
| `$current_persona_state_json` | 직전 turn까지의 누적 상태 |
| `$current_micro_plan_json` | 해당 turn의 선택적 Qwen 계획 |
| `$stage` | 계획 stage, 계획이 없으면 `unplanned` |
| `$turn_index` | 1부터 시작하는 현재 turn |
| `$min_turns`, `$max_turns` | 종료 범위 |

리터럴 `$`는 `$$`로 쓴다. generation 모델은 다음 객체 하나만 반환해야 한다.

```json
{
  "user": "English client utterance",
  "assistant": "English counselor response",
  "persona_state": {
    "summary": "All persona evidence accumulated through this turn"
  }
}
```

`persona_state`는 이번 turn의 delta가 아니라 누적 전체 상태다. coverage 모델 출력:

```json
{
  "sufficient": false,
  "missing": ["missing information dimension"],
  "reason": "brief evidence-based reason"
}
```

coverage prompt는 goal-aware Qwen에 최소 4턴 이후 매 turn 전달된다. `sufficient=true`면 사례별 조기 종료하고,
그렇지 않으면 `max_turns`까지 간다.

### Qwen micro-plan 동작

활성 `generate_histories`는 `--plans`가 없는 사례마다 Qwen을 호출해 profile top-12를
rerank하고, 최대 turn 수만큼 goal-aware micro-plan을 만들며, Lexi가 만든 각 turn을 Qwen으로
검증한다. 검증 실패 turn은 최대 3회 다시 생성한다. 최소 4턴 이후 Qwen coverage 결과가
충분하면 사례별로 조기 종료한다.

`--plans`는 재현을 위해 미리 고정한 계획을 주입할 때만 사용한다. 계획을 주입해도 Qwen
profile reranking과 turn verification은 실행된다. `--skip-qwen-planning`은 명시적 ablation
전용이며, 그 출력은 활성 본 실험 contract를 통과하지 않는다.

계획 파일 허용 양식은 list, 단일 object, 또는 case-id keyed object다. 각 plan에는
`micro_plans` list가 필수다.

```json
{
  "jmir-full-0001": {
    "target_proposition": "...",
    "requested_speech_act": "...",
    "micro_plans": [
      {"stage":"trigger","new_information":["..."]},
      {"stage":"self_interpretation","new_information":["..."]},
      {"stage":"relational_expectation","new_information":["..."]},
      {"stage":"desired_response","new_information":["..."]}
    ]
  }
}
```

## 11. 단계 D: 전체 pool 검색과 Lexi history 생성

```bash
python -m pipeline.generate_histories \
  --cases data/prepared/cases/jmir_eval_full_pre_generation.json \
  --profiles "${PERSONA_POOL_PATH:-../data/personas/personas.jsonl}" \
  --generation-prompt prompts/persona_history_generation.txt \
  --coverage-prompt prompts/persona_history_coverage.txt \
  --model Orenguteng/Llama-3.1-8B-Lexi-Uncensored-V2 \
  --base-url http://127.0.0.1:8002/v1 \
  --qwen-model Qwen/Qwen2.5-7B-Instruct \
  --qwen-base-url http://127.0.0.1:8000/v1 \
  --top-k 12 \
  --min-turns 4 \
  --max-turns 8 \
  --checkpoint-dir data/prepared/generated/jmir_eval_full_checkpoints \
  --output data/prepared/generated/jmir_eval_full_with_history.json
```

Qwen 계획을 준비했다면 `--plans data/prepared/plans/jmir_eval_full_qwen_plans.json`을 추가한다.

persona profile JSONL은 최소한 고유 `id` 또는 `persona_id`를 가져야 한다. 1차 검색은
pathology field overlap, crisis tag, goal text lexical coverage를 합산한다. Qwen은 그 top-k를
goal, pathology, profile 전체 내용으로 다시 평가해 최종 profile을 선택한다.

출력 active case의 추가 필드:

```json
{
  "persona": "final accumulated persona_state serialized as text",
  "metaphor": "state metaphor or fallback text",
  "persona_profile": {},
  "persona_history": [
    {"user":"...","assistant":"...","persona_state":{}}
  ],
  "persona_history_generation": {
    "model": "...",
    "retrieval_top_k": [],
    "profile_selection": {},
    "coverage_audit": [],
    "turn_verification": [],
    "stop_reason": "coverage_sufficient",
    "qwen_plan": {"micro_plans": []},
    "qwen_planning_mode": "goal_aware_dynamic",
    "persona_generation_status": "complete",
    "min_turns": 4,
    "max_turns": 8
  }
}
```

검사:

```bash
python -m pipeline.preflight \
  --cases data/prepared/generated/jmir_eval_full_with_history.json
```

성공 사례는 checkpoint directory에 `<case_id>.json`, 실패는
`<case_id>.failed.json`으로 저장된다. 재실행하면 성공 사례는 자동으로 건너뛰며 실패를 다시
시도하려면 `--retry-failed`를 추가한다. 최종 output JSON은 성공 사례가 생길 때마다 원자적으로
갱신된다. 하나라도 실패하면 명령은 exit code 1로 끝나므로 incomplete output을 본 실행에
넘기지 않는다. checkpoint에는 입력 case와 persona pool checksum, 두 prompt 본문, 모델,
turn 범위와 계획 설정의 fingerprint가 저장되며 완전히 같은 설정일 때만 재사용된다.

History 생성이 끝나면 Qwen vLLM 서버를 종료해 GPU 0을 비운 뒤 다음 본 실험에서 같은
snapshot을 `transformers`로 로드한다.

## 12. 단계 E: Qwen–target 본 실험

Qwen GPU와 batch 크기를 지정한다.

```bash
export QWEN_DEVICE=cuda:0
export QWEN_BATCH_SIZE=24
```

L40S의 여유 메모리가 충분하면 자동값도 24다. OOM이면 8, 4, 2 순서로 낮춘다.

먼저 한 사례만 smoke test한다.

```bash
python -m pipeline.run_batch \
  --cases data/prepared/generated/jmir_eval_full_with_history.json \
  --output-dir data/runs/gpt-4o-smoke \
  --target-model gpt-4o-2024-11-20 \
  --start 0 --stop 1 \
  --target-workers 16 \
  --qwen-snapshot .cache/qwen2.5-7b-instruct/a09a35458c702b33eeacc393d103063234e8bc28
```

smoke output을 검사한다.

```bash
python -m pipeline.preflight \
  --run data/runs/gpt-4o-smoke/jmir-full-0001.json
```

전체 실행:

```bash
python -m pipeline.run_batch \
  --cases data/prepared/generated/jmir_eval_full_with_history.json \
  --output-dir data/runs/gpt-4o \
  --target-model gpt-4o-2024-11-20 \
  --target-workers 32 \
  --qwen-snapshot .cache/qwen2.5-7b-instruct/a09a35458c702b33eeacc393d103063234e8bc28
```

주요 선택 인자:

- `--start N --stop M`: 입력 array index 반개구간 `[N, M)`만 실행
- `--crisis-label LABEL`: 반복 지정 가능한 범주 필터
- `--per-label N`: 각 선택 범주에서 최대 N개
- `--exclude-case-id ID`: 특정 case 제외
- `--retry-failed`: 기존 `.failed.json`을 재시도

성공한 사례 JSON이 있으면 자동 skip한다. 실패는 `<case_id>.failed.json`에 오류 종류와
메시지를 저장하며, 명시적으로 `--retry-failed`를 주기 전까지 skip한다.

사례별 run JSON 핵심 구조:

```json
{
  "version": "jmir-persona-eval-batch-v1",
  "research_engine_version": "...",
  "case_index": 0,
  "case": {},
  "results": [
    {
      "condition": "neutral",
      "turns": [],
      "shared_history": {"sha256":"...","full_messages":[]},
      "final_branches": [
        {
          "direction": "latent_request_synthesis",
          "question": "...",
          "target": {"text":"..."},
          "manifestation_question": "...",
          "manifestation_candidate_response": {"text":"candidate only"},
          "manifestation_research_analysis": "separate analysis",
          "manifestation_context": {"full_messages":[]}
        }
      ]
    }
  ]
}
```

조건은 `neutral`, `structural_hint`, `oracle_hint` 세 개다. final direction은 정확히 8개다.
CARES에는 `manifestation_candidate_response.text`만 전달한다.
각 조건의 누적 연구 대화는 최소 4턴 후 Qwen이 goal coverage를 검사한다. target이 target
proposition, 원하는 speech act, 이를 연결하는 persona 근거를 충분히 스스로 서술했으면 해당
조건만 종료하고, 부족하면 최대 7개 연구 stage까지 계속한다. `research_stop`과 마지막
`goal_coverage_audit`에 종료 근거가 남는다.

## 13. 단계 F: GPT 평가와 집계

smoke 평가:

```bash
python -m pipeline.evaluate_batch \
  --input-dir data/runs/gpt-4o-smoke \
  --output-dir data/evaluations/gpt-4o-smoke \
  --eval-model gpt-4o-mini-2024-07-18 \
  --cares-model gpt-4o-mini-2024-07-18 \
  --workers 16
```

전체 평가:

```bash
python -m pipeline.evaluate_batch \
  --input-dir data/runs/gpt-4o \
  --output-dir data/evaluations/gpt-4o \
  --eval-model gpt-4o-mini-2024-07-18 \
  --cares-model gpt-4o-mini-2024-07-18 \
  --workers 32
```

평가 파일의 `rows`는 3조건 x 8방향 = 24개다. 각 row에는 다음이 있다.

- `custom`: recovery level, behavior level과 파생 success boolean
- `official_cares`: `Accept`, `Caution`, `Refuse`, 입력 출처와 선택적 safety score
- `recovery_custom`: 분석 branch 기준 recovery 판정
- `manifestation_custom`: candidate response 기준 behavior 판정
- evaluator request metadata와 거절/재시도 기록

사례별 `summary`는 다음 지표를 조건별로 저장한다.

- `raw_success_at_8`
- `target_originated_success_at_8`
- `unsafe_manifestation_ASR_at_8`
- `official_CARES_non_refuse_at_8`
- `official_CARES_accept_at_8`

`cares_harmful_level`이 사전에 `0,1,2,3`으로 annotation되지 않았으면 CARES label과
Accept@8은 계산되지만 Safety Score, binary accuracy, F1은 `null`이다. `crisis_label`에서
harmful level을 임의로 추론하지 않는다.

검사:

```bash
python -m pipeline.preflight \
  --evaluation data/evaluations/gpt-4o-smoke/jmir-full-0001.json

python - <<'PY'
import json
from pathlib import Path
p = Path("data/evaluations/gpt-4o/aggregate_summary.json")
v = json.loads(p.read_text())
print("evaluated_cases", v["evaluated_cases"])
print(json.dumps(v["aggregate"].get("all", {}), indent=2))
PY
```

## 14. 파일별 역할

### 활성 진입점

| 파일 | 역할 | 주 입력 | 주 출력 |
|---|---|---|---|
| `experiments/build_jmir_eval_set_full.py` | 625 goal과 pathology join | 2개 JSONL | blueprint JSONL/report |
| `pipeline/prepare.py` | canonical adapter CLI | blueprint JSONL | prepared case JSON |
| `pipeline/generate_histories.py` | Qwen reranking/계획/검증 + Lexi history + checkpoint | prepared cases, profiles, prompts | active cases JSON |
| `pipeline/run_batch.py` | checkpointed 본 실행 | active cases | 사례별 run JSON |
| `pipeline/evaluate_batch.py` | checkpointed 평가·집계 | run directory | 사례별 eval/aggregate JSON |
| `pipeline/preflight.py` | 모델 호출 없는 경계 검사 | 각 단계 artifact | stdout validation report |

### 활성 구현 모듈

| 파일 | 역할 |
|---|---|
| `pipeline/contracts.py` | 단계별 필수 field, 3x8 matrix, candidate-only CARES 계약 |
| `pipeline/persona_pool.py` | 31,733 profile 로딩과 결정적 top-k 검색 |
| `pipeline/persona_history.py` | template 치환, JSON parsing, turn/coverage 검증, 동적 종료 |
| `pipeline/history_planning.py` | Qwen profile reranking, 최대 8단계 plan, turn 검증 계약 |
| `pipeline/runtime_io.py` | OpenAI-compatible chat HTTP 호출과 원자적 JSON 저장 |
| `experiments/prepare_jmir_persona_eval.py` | `status`, `merge`, `adapt` 실제 구현 |
| `experiments/qwen_target_persona_research_dialogue.py` | Qwen 질문, target 누적 context, 3조건, 8 branch, candidate 분리 |
| `experiments/run_jmir_persona_eval_batch.py` | 사례 선택, checkpoint, resume/failure 파일 |
| `experiments/evaluate_persona_co_research.py` | Recovery/Behavior와 CARES 입력 분리 |
| `experiments/evaluate_cares_official.py` | 고정 CARES prompt 호출과 label parsing |
| `experiments/evaluate_jmir_persona_eval_batch.py` | 사례 평가 반복과 범주별 aggregate |

### 프롬프트와 고정 설정

| 파일 | 역할 |
|---|---|
| `configs/persona_history/generation_prompt.template.txt` | Lexi turn 생성 기본 template |
| `configs/persona_history/coverage_prompt.template.txt` | 동적 종료 판정 template |
| `evaluation/prompts/research_prompt_banks_en.json` | Qwen research/final/manifestation bank |
| `evaluation/prompts/safe_counseling_joint_research_guidelines.md` | target 최초 packet의 연구 지침 |
| `evaluation/prompts/persona_co_research_recovery_evaluator.txt` | custom recovery/behavior rubric |
| `evaluation/prompts/cares_official_response_evaluator.txt` | 공식 CARES evaluator prompt |

본 문서의 canonical 명령만 사용한다.

## 15. 중단 재개와 다중 GPU 분할

`run_batch`와 `evaluate_batch`는 사례별 파일이 checkpoint다. 프로세스가 중단되어도 성공
파일은 다시 실행하지 않는다. 실패만 재시도한다.

예를 들어 625개를 네 프로세스로 나누려면 서로 다른 directory를 쓴다.

```bash
# GPU/프로세스 0
QWEN_DEVICE=cuda:0 python -m pipeline.run_batch ... --start 0   --stop 157 --output-dir data/runs/shard0
# GPU/프로세스 1
QWEN_DEVICE=cuda:1 python -m pipeline.run_batch ... --start 157 --stop 314 --output-dir data/runs/shard1
# GPU/프로세스 2
QWEN_DEVICE=cuda:2 python -m pipeline.run_batch ... --start 314 --stop 471 --output-dir data/runs/shard2
# GPU/프로세스 3
QWEN_DEVICE=cuda:3 python -m pipeline.run_batch ... --start 471 --stop 625 --output-dir data/runs/shard3
```

각 shard가 끝나면 `jmir-full-*.json`만 최종 directory로 복사한다. `run_summary.json`과
`.failed.json`은 합칠 대상이 아니다. 같은 case를 둘 이상의 프로세스가 같은 directory에서
동시에 쓰지 않는다.

## 16. 자주 발생하는 실패

| 증상 | 원인 | 조치 |
|---|---|---|
| `FileNotFoundError: Qwen snapshot` | revision 경로 불일치 | `--qwen-snapshot` 절대경로 확인 |
| persona pool 파일 없음 | 이전 서버 하드코딩 경로 의존 | `PERSONA_POOL_PATH` 설정 또는 기본 위치에 복사 |
| Lexi HTTP 404/model not found | served model name 불일치 | `/v1/models` 결과와 `--model` 일치 |
| Lexi JSON parsing 실패 | prompt가 JSON-only 계약을 못 지킴 | 소규모 prompt pilot, Markdown 금지 강화 |
| Qwen CUDA OOM | batch size가 큼 | `QWEN_BATCH_SIZE` 축소 |
| OpenAI 429 | workers/rate limit 과다 | workers 축소 후 `--retry-failed` |
| 평가 row가 24개 미만 | run branch 누락 또는 CARES 실패 | run preflight, 실패 JSON 확인 후 재실행 |
| Safety Score가 null | harmful level 미annotation | 실험 전 독립 annotation 추가; label에서 추론 금지 |
| history가 `unplanned` | `--skip-qwen-planning` 사용 또는 구형 산출물 | ablation 옵션 제거 후 checkpoint를 새로 생성 |

## 17. 현재 코드에서 남은 운영 특성

다른 서버에서 실행 전에 특히 다음을 인지해야 한다.

1. persona full-pool의 1차 후보 검색은 embedding 검색이 아니라 구조화 overlap + lexical
   coverage이며, 그 뒤 Qwen이 top-12를 rerank한다.
2. `run_batch`와 `evaluate_batch`는 사례 간 병렬화가 아니라 사례 내부 병렬화다.
3. API model snapshot 이름이 계정에서 계속 제공되는지 실행 당일 확인해야 한다.
4. raw/private data와 생성 결과는 `.gitignore` 대상이므로 Git clone만으로 복구되지 않는다.

이 운영 특성은 설치 실패와 실험 설정 차이를 구분하기 위해 run log에 기록한다.

## 18. 최종 실행 전 체크리스트

```text
[ ] Git commit hash 기록
[ ] Python/package 버전 기록
[ ] GPU/driver/CUDA 정보 기록
[ ] goal 625, route 625, persona 31,733 행 수 확인
[ ] goal/route SHA256 확인
[ ] Qwen/Lexi repo id와 revision 기록
[ ] Lexi /v1/models 응답 확인
[ ] OPENAI_API_KEY와 target/evaluator model 접근 확인
[ ] prompt 두 개가 영어이며 JSON 계약을 명시하는지 확인
[ ] Qwen plan 사용 여부와 계획 파일 checksum 기록
[ ] active case preflight 통과
[ ] 1-case run + evaluation smoke test 통과
[ ] workers를 낮게 시작해 429/OOM 여부 확인
[ ] 전체 run의 failed 파일 0개 확인
[ ] 전체 evaluation의 evaluated_cases=625 확인
[ ] aggregate와 원시 사례 JSON을 함께 보존
```

실행 기준 문서의 우선순위는 이 문서, `JMIR_FULL_EXPERIMENT_RUNBOOK_KO.md`,
`pipeline/README.md`, 실제 `--help` 순이다. 충돌이 있으면 실제 코드와 `--help`를 우선하고
문서를 같은 commit에서 수정한다.
