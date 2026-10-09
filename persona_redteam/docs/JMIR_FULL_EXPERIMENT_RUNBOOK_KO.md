# JMIR 전체 625개 실험 실행 절차

저장소 루트에서 실행한다. 전체 구조는 `PIPELINE_OVERVIEW_KO.md`를 기준으로 한다.
새 서버 설치, private data 배치와 입출력 스키마는
`docs/NEW_SERVER_SETUP_AND_EXPERIMENT_GUIDE_KO.md`를 먼저 확인한다.

## 1. 입력 검사와 adapter

```bash
python3 -m pipeline.route_goals \
  --goals ../data/crisis_goals_jmir_persona_min10.jsonl \
  --existing-routes ../data/goal_pathology_routes_n625.jsonl \
  --output ../data/goal_pathology_routes_n625.jsonl \
  --checkpoint-dir data/prepared/routes/jmir625 \
  --model gpt-4o-mini-2024-07-18 --workers 48 --retry-failed

python3 experiments/build_jmir_eval_set_full.py

python3 -m pipeline.preflight \
  --blueprint data/prepared/blueprints/jmir_eval_full.jsonl

python3 -m pipeline.prepare adapt \
  --input data/prepared/blueprints/jmir_eval_full.jsonl \
  --output data/prepared/cases/jmir_eval_full_pre_generation.json

python3 -m pipeline.preflight \
  --prepared-cases data/prepared/cases/jmir_eval_full_pre_generation.json
```

## 2. 사용자 프롬프트 준비

```bash
mkdir -p prompts
cp configs/persona_history/generation_prompt.template.txt prompts/persona_history_generation.txt
cp configs/persona_history/coverage_prompt.template.txt prompts/persona_history_coverage.txt
```

변수와 JSON 계약은 `docs/PERSONA_HISTORY_PROMPT_HOOKS_KO.md`를 따른다.

## 3. 전체 pool 기반 Lexi history

`--profiles`를 생략하면 `$PERSONA_POOL_PATH` 또는
`data/source/personas/personas.jsonl`의 전체 pool을 사용한다.

```bash
python3 -m pipeline.generate_histories \
  --cases data/prepared/cases/jmir_eval_full_pre_generation.json \
  --generation-prompt prompts/persona_history_generation.txt \
  --coverage-prompt prompts/persona_history_coverage.txt \
  --model Orenguteng/Llama-3.1-8B-Lexi-Uncensored-V2 \
  --base-url http://127.0.0.1:8002/v1 \
  --qwen-model Qwen/Qwen2.5-7B-Instruct \
  --qwen-base-url http://127.0.0.1:8000/v1 \
  --min-turns 4 --max-turns 8 \
  --checkpoint-dir data/prepared/generated/jmir_eval_full_checkpoints \
  --output data/prepared/generated/jmir_eval_full_with_history.json
```

`--plans`를 생략하면 Qwen이 각 사례의 profile을 rerank하고 최대 8단계 plan을 동적으로
생성한다. Lexi의 각 turn은 Qwen 검증을 통과해야 누적된다. 실패 checkpoint 재시도에는
`--retry-failed`를 추가한다.

Qwen micro-plan → Lexi 턴별 렌더링과 검증은 `pipeline.generate_histories` 안에서 수행되며,
사례별 checkpoint에 계획·생성·검증 결과가 함께 저장된다.

## 4. Qwen–target 본 실행

```bash
python3 -m pipeline.run_batch \
  --cases data/prepared/generated/jmir_eval_full_with_history.json \
  --output-dir data/runs/gpt-4o \
  --target-model gpt-4o-2024-11-20 \
  --target-workers 32
```

실패 checkpoint를 재시도하려면 `--retry-failed`를 추가한다.

## 5. 평가와 집계

```bash
python3 -m pipeline.evaluate_batch \
  --input-dir data/runs/gpt-4o \
  --output-dir data/evaluations/gpt-4o \
  --eval-model gpt-4o-mini-2024-07-18 \
  --cares-model gpt-4o-mini-2024-07-18 \
  --workers 32
```

공식 CARES에는 `manifestation_candidate_response.text`만 전달한다.

## 6. 산출물 검사

```bash
python3 -m pipeline.preflight --run data/runs/gpt-4o/jmir-full-0001.json
python3 -m pipeline.preflight --evaluation data/evaluations/gpt-4o/jmir-full-0001.json
```
