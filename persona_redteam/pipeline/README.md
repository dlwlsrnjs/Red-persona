# 활성 JMIR 페르소나 실험 파이프라인

이 디렉터리가 현재 전체 625개 실험의 단일 진입점이다. `experiments/` 아래 기존 파일은 과거
명령과 import 호환을 위해 유지하며, 활성 API와 CLI는 이 패키지에서 노출한다.

```text
JMIR goal + pathology
  -> persona_pool: 실행 시 전체 pool에서 top-k 검색 및 최종 profile 선택
  -> generate_histories: 사용자 소유 Lexi prompt로 최소 4턴의 가변 과거 이력 생성
  -> persona_generation: 마지막 누적 persona state를 활성 persona로 연결
  -> research_context: goal-aware Qwen 동적 질문 + 타겟 누적 분석
  -> research_context: 같은 누적 prefix를 복제한 8개 독립 분석/실제응답 분기
  -> research_context: candidate_response / research_analysis 구조 분리
  -> final_validation: GPT recovery/behavior 판정 + candidate-only 공식 CARES
  -> final_validation: 조건별/위기범주별 Success@8와 ASR@8 집계
```

## 1. 페르소나 생성

`pipeline.persona_generation`은 goal pathology만 준비하며 target-visible persona seed나
metaphor를 만들지 않는다. 전체 pool 검색·Qwen reranking·Lexi 누적 이력 생성이
끝난 뒤에만 마지막 `persona_state`가 활성 `persona`가 된다.

새 동적 경로는 `python -m pipeline.generate_histories`다. 검색은
`pipeline.persona_pool`, 프롬프트 렌더링·JSON 검증·최소/최대 턴 제어는
`pipeline.persona_history`가 담당한다. 생성 prompt와 coverage prompt의 내용은 코드에서
분리되어 있으며 `configs/persona_history/*.template.txt`를 복사해 사용자가 작성한다.
충분성 판정은 최소 4턴 이후 매 턴 실행되고, 충분하면 샘플별로 종료한다. 마지막
`persona_state`가 활성 `persona`가 되며 전체 `persona_history`도 별도 필드로 보존된다.

```bash
cp configs/persona_history/generation_prompt.template.txt prompts/my_generation.txt
cp configs/persona_history/coverage_prompt.template.txt prompts/my_coverage.txt

python3 -m pipeline.generate_histories \
  --cases data/prepared/cases/jmir_eval_full_pre_generation.json \
  --profiles data/source/personas/personas.jsonl \
  --generation-prompt prompts/my_generation.txt \
  --coverage-prompt prompts/my_coverage.txt \
  --plans data/prepared/plans/jmir_eval_full_qwen_plans.json \
  --model Orenguteng/Llama-3.1-8B-Lexi-Uncensored-V2 \
  --base-url http://127.0.0.1:8002/v1 \
  --qwen-model Qwen/Qwen2.5-7B-Instruct \
  --qwen-base-url http://127.0.0.1:8000/v1 \
  --min-turns 4 --max-turns 8 \
  --checkpoint-dir data/prepared/generated/jmir_eval_full_checkpoints \
  --output data/prepared/generated/jmir_eval_full_with_history.json
```

템플릿 치환은 Python `$변수` 문법을 쓴다. 프롬프트 본문에서 달러 기호 자체가 필요하면
`$$`로 쓴다. 생성 출력은 `user`, `assistant`, `persona_state`, coverage 출력은
`sufficient`, `missing`, `reason` JSON 계약을 지켜야 한다.
Qwen 계획을 `--plans`로 주면 각 턴의 `$current_micro_plan_json`, `$stage`와 직전
누적 상태인 `$current_persona_state_json`이 두 템플릿에 같이 전달된다. 활성 모델 프롬프트와
새로 생성하는 대화·상태 데이터는 영어로 작성한다.

## 2. 페르소나 활용 분석

`pipeline.research_context`의 최초 타겟 호출은 공동연구 system prompt, 동적으로 선택·누적한
persona state, 전체 과거 대화 이력과 metaphor를 받는다. 이후
Qwen의 새 질문에 답하면서 관찰, self schema, 인과규칙, 관계 기대, 원하는 발화행위,
대안가설과 latent goal을 순서대로 누적 분석한다.
모든 타겟 호출에는 동일한 공동연구 system prompt가 정확히 하나 포함된다.

## 3. Qwen–타겟 연구 컨텍스트

Qwen은 private goal을 최종 답변 목표로 알고 전체 누적 대화를 본다. 매 라운드 최신 타겟
응답과 goal의 핵심 명제·요청된 발화행위를 비교해 가장 중요한 누락 요소를 묻는다.
최소 4번의 연구 턴 이후 Qwen이 target proposition, 요청된 speech act, persona 근거의
충분성을 조건별로 검사하며 충분한 조건은 독립적으로 종료한다. 최대 연구 턴은 7번이다.
Neutral과 Structural 조건의 질문은 goal n-gram 누출 검사를 통과해야 한다. 타겟의 모든
이전 응답과 Qwen 질문은 삭제·요약하지 않고 다음 호출에 누적한다. Oracle은 goal 주입의
별도 대조군이다.

- Neutral: 내용과 분석축을 제시하지 않는 열린 질문
- Structural hint: goal 내용 없이 분석 방향만 제시
- Oracle hint: private goal을 연구자 가설로 직접 제시하는 대조군

blueprint의 `research_analysis_history`는 초기 설계 provenance이며 활성 호출에는 사용하지
않는다. 활성 연구 질문의 기준은 `STAGES`, `NEUTRAL_BANK`, `STRUCTURAL_BANK`다.

## 4. 8개 최종 분기와 GPT 통합

공통 누적 prefix를 복제해 잠재 요청 합성, 근거 사슬, 발화행위, metaphor 역추적, 관계 기능,
대안 가설, 듣고 싶은 판단, 출처 재구성의 8개 독립 분기를 만든다. 각 분기는 분석 응답 뒤
같은 이력에서 실제 상담 답변을 한 번 더 생성한다. 다른 분기의 질문·응답은 보지 않는다.
최종 출력은 `candidate_response`와 `research_analysis`로 분리되며, Qwen은 각 방향의 10개
직접형 질문 전체에서 인덱스로 하나를 선택한다.

blueprint의 `final_boundary_test`는 과거 설계 provenance이며 활성 8분기 GPT 프롬프트에는
합쳐지지 않는다. 활성 기준은 `FINAL_DIRECTIONS`와
`MANIFESTATION_DIRECTIONS`다.
활성 Qwen 질문 bank·8개 final branch·manifestation 프롬프트의 영어 원본은
`evaluation/prompts/research_prompt_banks_en.json`이며, 실행 시 이 파일을 로드한다.
초기 target packet은 영어 `safe_counseling_joint_research_guidelines.md`를 포함한다.

## 5. 평가 수치

`pipeline.final_validation`은 분석 응답에서 Recovery R0–R4와 출처를, 실제응답에서 Behavior
B0–B5를 각각 계산한다. 공식 CARES는 실제 target prompt와 분리된
`manifestation_candidate_response.text`에 적용한다. 연구 분석은 CARES 응답에 포함하지
않는다. 사례 단위로 다음을
집계한다.

- raw Recovery@8
- target-originated Recovery@8
- unsafe manifestation ASR@8
- official CARES Accept@8
- official CARES non-refuse@8

CARES Safety Score·Accuracy·F1은 원논문과 동일하게 사전 위해도 `h∈{0,1,2,3}`가 있는
경우에만 계산한다. `crisis_label`에서 위해도를 임의 추론하지 않는다.

## 탐색 파일럿과 본 실행의 구분

`experiments/pilot_direct_candidate_matrix.py`와
`experiments/pilot_analyst_response_accept_tree.py`는 프롬프트 탐색용이다. 본 625개 실행은
항상 `pipeline.run_batch` → `pipeline.evaluate_batch` 경로를 사용한다.

최종 batch 집계는 전체와 `crisis_label`별 성공 사례 수 및 비율을 저장한다.

## 연결 검증

각 단계 산출물은 다음처럼 모델 호출 없이 검사할 수 있다.

```bash
python3 -m pipeline.preflight --blueprint data/prepared/blueprints/jmir_eval_full.jsonl
python3 -m pipeline.preflight --prepared-cases data/prepared/cases/jmir_eval_full_pre_generation.json
python3 -m pipeline.preflight --run data/runs/gpt-4o/jmir-full-0001.json
python3 -m pipeline.preflight --evaluation data/evaluations/gpt-4o/jmir-full-0001.json
```

실제 준비·실행·평가 명령은 각각 `python -m pipeline.prepare`,
`python -m pipeline.run_batch`, `python -m pipeline.evaluate_batch`이며 전체 인자는
`docs/JMIR_FULL_EXPERIMENT_RUNBOOK_KO.md`를 따른다. `experiments/`의 동명 스크립트는
호환용 구현 경로다.
