# JMIR 100개 실험 실행 절차

저장소 루트에서 실행한다. 전체 구조는 `PIPELINE_OVERVIEW_KO.md`를 기준으로 한다.

## 1. 입력 검사와 adapter

```bash
python3 -m pipeline.preflight \
  --blueprint experiments/fixtures/jmir_persona_eval_set_100.jsonl

python3 -m pipeline.prepare adapt \
  --input data/prepared/matched/jmir_eval_100_matched.jsonl \
  --output data/prepared/cases/jmir_eval_100_pre_generation.json

python3 -m pipeline.preflight \
  --prepared-cases data/prepared/cases/jmir_eval_100_pre_generation.json
```

## 2. 사용자 프롬프트 준비

```bash
mkdir -p prompts
cp configs/persona_history/generation_prompt.template.txt prompts/persona_history_generation.txt
cp configs/persona_history/coverage_prompt.template.txt prompts/persona_history_coverage.txt
```

변수와 JSON 계약은 `docs/PERSONA_HISTORY_PROMPT_HOOKS_KO.md`를 따른다.

## 3. 전체 pool 기반 Lexi history

`--profiles`를 생략하면 31,733개 전체 pool을 사용한다.

```bash
python3 -m pipeline.generate_histories \
  --cases data/prepared/cases/jmir_eval_100_pre_generation.json \
  --generation-prompt prompts/persona_history_generation.txt \
  --coverage-prompt prompts/persona_history_coverage.txt \
  --model Orenguteng/Llama-3.1-8B-Lexi-Uncensored-V2 \
  --base-url http://127.0.0.1:8002/v1 \
  --min-turns 4 --max-turns 8 \
  --output data/prepared/generated/jmir_eval_100_with_history.json
```

Qwen micro-plan → Lexi 턴별 렌더링은 현재 아래 소규모 파일럿에서 검증한다.

```bash
python3 experiments/pilot_qwen_lexi_persona_history.py \
  --cases data/prepared/cases/jmir_eval_100_pre_generation.json \
  --matched data/prepared/matched/jmir_eval_100_matched.jsonl \
  --case-id jmir-eval-003 \
  --output data/pilots/qwen-lexi-history/jmir-eval-003.json
```

## 4. Qwen–target 본 실행

```bash
python3 -m pipeline.run_batch \
  --cases data/prepared/generated/jmir_eval_100_with_history.json \
  --output-dir data/runs/gpt-4o \
  --target-model gpt-4o-2024-11-20 \
  --target-workers 256
```

실패 checkpoint를 재시도하려면 `--retry-failed`를 추가한다.

## 5. 평가와 집계

```bash
python3 -m pipeline.evaluate_batch \
  --input-dir data/runs/gpt-4o \
  --output-dir data/evaluations/gpt-4o \
  --eval-model gpt-4o-mini-2024-07-18 \
  --cares-model gpt-4o-mini-2024-07-18 \
  --workers 256
```

공식 CARES에는 `manifestation_candidate_response.text`만 전달한다.

## 6. 산출물 검사

```bash
python3 -m pipeline.preflight --run data/runs/gpt-4o/jmir-eval-001.json
python3 -m pipeline.preflight --evaluation data/evaluations/gpt-4o/jmir-eval-001.json
```
