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

## 2. Persona category sidecar 생성

Git에는 검증 완료된 31,733행 최종 sidecar가 포함되어 있으므로 기본 실행에서는 이 절을
건너뛴다. 먼저 `sha256sum ../data/personas/persona_category_labels.jsonl`이
`7fa62560f5c99dc1d05b7aacac17f63a92ad19f13ac1e3fda13aa5a033edf9f0`인지 확인한다.
아래 절차는 라벨을 처음부터 재생성할 때만 실행한다.

```bash
python3 -m pipeline.label_persona_categories \
  --input ../data/personas/personas.jsonl \
  --output ../data/personas/persona_category_labels.jsonl \
  --checkpoint-dir ../data/personas/category_checkpoints \
  --model Qwen/Qwen2.5-7B-Instruct \
  --base-url http://127.0.0.1:8000/v1 \
  --batch-size 5 --workers 16 --attempts 3 --retry-failed
```

기존 partial JSONL만 있고 checkpoint가 없다면 `--resume-from <partial.jsonl>`을 추가한다.
완료된 행은 파일 순서와 무관하게 `persona_id`로 검증·재사용하고 누락된 persona만 생성한다.

희소 범주를 고유 base family 100개 이상으로 보강하려면 다음 targeted audit을 실행한다.

```bash
python3 -m pipeline.rebalance_persona_categories \
  --profiles ../data/personas/personas.jsonl \
  --labels ../data/personas/persona_category_labels.jsonl \
  --output ../data/personas/persona_category_labels.jsonl \
  --checkpoint-dir ../data/personas/category_checkpoints/gpt4omini-rebalance-v2 \
  --model gpt-4o-mini-2024-07-18 \
  --minimum 100 --candidate-limit 1600 --workers 64 --retry-failed
```

GPT 원문 근거 판정과 명시적 category adaptation은 구분해 provenance에 남는다. 숫자를 맞추기
위해 근거 없는 profile을 원문상 direct 사례로 재라벨링하지 않는다. 보수적 최종본은 원문
인접 재지정을 원복하고, 명확한 위해 방향을 가진 구성형 후보만 사용한다. 먼저 재분류 행을
항목별로 독립 감사한다. 감사 명령은 실패 행이 있으면 의도적으로 종료 코드 2를 반환한다.

```bash
python3 -m pipeline.audit_persona_category_rebalance \
  --profiles ../data/personas/personas.jsonl \
  --labels ../data/personas/persona_category_labels.jsonl \
  --checkpoint-dir ../data/personas/category_checkpoints/gpt4omini-audit-initial \
  --summary ../data/personas/persona_category_labels.audit.json \
  --model gpt-4o-mini-2024-07-18 \
  --batch-size 1 --workers 64 --attempts 5 --retry-failed
```

실패 행과 원문 인접 재지정을 복원하고, 결손 범주마다 후보를 넉넉히 생성해 동일 감사 통과
후보만 선택한다.

```bash
python3 -m pipeline.repair_persona_category_rebalance \
  --profiles ../data/personas/personas.jsonl \
  --labels ../data/personas/persona_category_labels.jsonl \
  --audit-checkpoints ../data/personas/category_checkpoints/gpt4omini-audit-initial \
  --checkpoint-dir ../data/personas/category_checkpoints/gpt4omini-repair \
  --output ../data/personas/persona_category_labels.jsonl \
  --summary ../data/personas/category_checkpoints/gpt4omini-repair/summary.json \
  --model gpt-4o-mini-2024-07-18 \
  --minimum 100 --batch-size 1 --workers 64 --attempts 5 \
  --revert-source-grounded
```

마지막으로 새 checkpoint 디렉터리에서 위 감사 명령을 다시 실행해 `passed=268`, `failed=0`과
다섯 차원의 268/268을 확인한다. 최종 sidecar와 `.audit.json`만 버전 관리하며 생성
checkpoint와 partial 파일은 제외한다.

초기 전체 라벨 명령은 일부 batch가 실패하면 non-zero로 종료한다. `--retry-failed`로 재실행해 최종 summary의
`complete=31733`, `failed=0`을 확인한다. Partial sidecar로 history 생성을 시작할 수 없다.

## 3. 사용자 프롬프트 준비

```bash
mkdir -p prompts
cp configs/persona_history/generation_prompt.template.txt prompts/persona_history_generation.txt
cp configs/persona_history/coverage_prompt.template.txt prompts/persona_history_coverage.txt
```

변수와 JSON 계약은 `docs/PERSONA_HISTORY_PROMPT_HOOKS_KO.md`를 따른다.

## 4. 전체 pool 기반 Lexi history

`--profiles`를 생략하면 `$PERSONA_POOL_PATH` 또는
`../data/personas/personas.jsonl`의 전체 pool을 사용한다.

```bash
python3 -m pipeline.generate_histories \
  --cases data/prepared/cases/jmir_eval_full_pre_generation.json \
  --category-labels ../data/personas/persona_category_labels.jsonl \
  --generation-prompt prompts/persona_history_generation.txt \
  --coverage-prompt prompts/persona_history_coverage.txt \
  --model Orenguteng/Llama-3.1-8B-Lexi-Uncensored-V2 \
  --base-url http://127.0.0.1:8002/v1 \
  --qwen-model Qwen/Qwen2.5-7B-Instruct \
  --qwen-base-url http://127.0.0.1:8000/v1 \
  --min-turns 4 --max-turns 12 \
  --generation-attempts 6 --lexi-temperature 0.7 \
  --seed 20261009 \
  --checkpoint-dir data/prepared/generated/jmir_eval_full_checkpoints \
  --output data/prepared/generated/jmir_eval_full_with_history.json
```

`--plans`를 생략하면 Qwen이 각 사례의 profile을 rerank하고 최대 12단계 plan을 동적으로
생성한다. Lexi의 각 turn은 Qwen 검증을 통과해야 누적된다. 실패 checkpoint 재시도에는
`--retry-failed`를 추가한다.

각 turn의 중복·검증 실패는 기본 최대 6회 재생성한다. 재시도 prompt에는 직전 실패 후보,
금지할 이전 대화, 현재 micro-plan의 `new_information`이 포함되며 attempt 번호가 달라져
결정적 반복을 피한다. `--lexi-temperature`는 Lexi 생성에만 적용되고 Qwen 검증에는 적용하지
않는다.

Qwen은 goal을 3–4개의 canonical `G1..Gn` atom으로 분해한다. Coverage는 Qwen 판정과
`verify_turn`을 통과한 micro-plan atom을 단조 누적하며, 하나라도 빠진 atom이 있으면 다음 turn
plan을 해당 부족분에 맞게 다시 만든다. `persona_grounded`와 `goal_recoverable`은 audit에 함께
남고, acceptance에는 전체 atom coverage와 persona grounding을 요구한다. 최대 12턴에도 충분하지
않으면 사례는 실패로 남으며, partial history·coverage·검증·재계획 기록은 `.failed.json`의
`diagnostics`에 저장된다.

Qwen micro-plan → Lexi 턴별 렌더링과 검증은 `pipeline.generate_histories` 안에서 수행되며,
사례별 checkpoint에 계획·생성·검증 결과가 함께 저장된다.

## 5. Qwen–target 본 실행

```bash
python3 -m pipeline.run_batch \
  --cases data/prepared/generated/jmir_eval_full_with_history.json \
  --output-dir data/runs/gpt-4o \
  --target-model gpt-4o-2024-11-20 \
  --target-workers 32
```

실패 checkpoint를 재시도하려면 `--retry-failed`를 추가한다.

## 6. 평가와 집계

```bash
python3 -m pipeline.evaluate_batch \
  --input-dir data/runs/gpt-4o \
  --output-dir data/evaluations/gpt-4o \
  --eval-model gpt-4o-mini-2024-07-18 \
  --cares-model gpt-4o-mini-2024-07-18 \
  --workers 32
```

공식 CARES에는 `manifestation_candidate_response.text`만 전달한다.

## 7. 산출물 검사

```bash
python3 -m pipeline.preflight --run data/runs/gpt-4o/jmir-full-0001.json
python3 -m pipeline.preflight --evaluation data/evaluations/gpt-4o/jmir-full-0001.json
```
