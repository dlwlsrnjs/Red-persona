# RED-Persona

이 저장소는 JMIR 기반 625개 평가 샘플을 대상으로, 전체 persona pool에서 샘플별 profile을
동적으로 선택하고 persona history, Qwen–target 연구 대화, 4개 최종 분기, GPT 평가까지
연결하는 단일 파이프라인을 제공한다.

현재 기준은 [`PIPELINE_OVERVIEW_KO.md`](PIPELINE_OVERVIEW_KO.md)와
[`pipeline/README.md`](pipeline/README.md)다.

논문용 연구 철학, 선행연구 공백, 단계별 sample transformation, 평가 정의와 현재 유효
250개 결과는 [`docs/PAPER_METHODS_RESULTS_KO.md`](docs/PAPER_METHODS_RESULTS_KO.md)에 정리했다.
625개 후보에서 손상 사례를 제외하고 사람 검수를 거쳐 최종 500개를 구성한 기준은
[`docs/SELECTION_500_AUDIT_KO.md`](docs/SELECTION_500_AUDIT_KO.md)에 별도로 고정했다.
논문 메서드 그림의 실제 사례와 panel별 데이터 흐름은
[`docs/FIGURE_METHOD_EXAMPLE_JMIR_FULL_0077_KO.md`](docs/FIGURE_METHOD_EXAMPLE_JMIR_FULL_0077_KO.md),
full dialogue 대 no-research-dialogue paired 설계와 추가 Qwen target arm은
[`ablation/README_KO.md`](ablation/README_KO.md)에 기록했다.
두 target의 공식 500개 paired 결과, exact McNemar 검정, 비용과 QA는
[`ablation/RESULTS_NO_RESEARCH_OFFICIAL500_KO.md`](ablation/RESULTS_NO_RESEARCH_OFFICIAL500_KO.md)에
고정했다.
Qwen target 공식 500개의 모델 revision, 7-GPU shard, 질문 provenance, 빈 출력 검사 결과는
[`docs/QWEN_TARGET_500_RUN_AUDIT_KO.md`](docs/QWEN_TARGET_500_RUN_AUDIT_KO.md)에 고정했다.

## 활성 흐름

```text
625 goals + 625 goal-pathology routes
  -> 전체 31,733 persona pool 검색
  -> Qwen profile reranking 및 turn plan
  -> Lexi가 최소 4턴의 가변 영어 history 생성
  -> Qwen이 매 턴 검증하고 충분할 때 종료
  -> 마지막 누적 persona state를 활성 persona로 사용
  -> goal-aware Qwen과 target의 4~7턴 연구 대화
  -> 동일 누적 context에서 4개 독립 final branch
  -> candidate_response만 CARES에 전달
  -> Recovery/Behavior/CARES 및 범주별 집계
```

기본 GPT-4o target arm에서는 Qwen2.5-7B-Instruct가 goal-aware planner다. 추가 모델 일반성
arm에서는 `Qwen/Qwen2.5-7B-Instruct`가 goal-blind target이고, 같은 모델 계열을 양쪽 역할에
쓰는 confound를 피하기 위해 표준 `meta-llama/Llama-3.1-8B-Instruct`가 planner를 맡는다.
Lexi-Uncensored는 과거 persona history renderer일 뿐 target이나 추가 arm의 planner가 아니다.

새 샘플도 고정 seed를 선택하지 않는다. `pipeline.route_goals`로 pathology를 생성한 뒤 전체
pool 검색과 Qwen reranking을 동일하게 적용한다.

## 디렉터리

| 경로 | 역할 |
|---|---|
| `pipeline/` | 준비, history 생성, 실행, 평가, preflight의 canonical CLI/API |
| `experiments/` | 활성 파이프라인 구현체와 단위 테스트 |
| `configs/persona_history/` | 사용자 작성 Lexi generation/coverage 템플릿 |
| `evaluation/prompts/` | 영어 연구 질문 bank, target packet, 평가 prompt |
| `extraction/` | goal pathology 추출 구현 |
| `goals/` | 625개 필터 규칙과 추출 보고서 |
| `docs/` | 데이터 lineage, 서버 설치, 전체 실행 절차 |
| `data/` | Git에서 제외되는 원본·중간·실행·평가 산출물 |

## 빠른 시작

프로젝트 디렉터리에서 실행한다.

```bash
python3 -m pip install -r pipeline/requirements-runtime.txt
python3 -m pipeline.preflight --blueprint data/prepared/blueprints/jmir_eval_full.jsonl
python3 -m pipeline.preflight --prepared-cases data/prepared/cases/jmir_eval_full_pre_generation.json
python3 -m unittest discover -s experiments -p 'test_*.py'
```

전체 준비·모델 snapshot·서버·실행·재개 명령은
[`docs/JMIR_FULL_EXPERIMENT_RUNBOOK_KO.md`](docs/JMIR_FULL_EXPERIMENT_RUNBOOK_KO.md), 새 서버
배치는 [`docs/NEW_SERVER_SETUP_AND_EXPERIMENT_GUIDE_KO.md`](docs/NEW_SERVER_SETUP_AND_EXPERIMENT_GUIDE_KO.md)를
따른다. 프롬프트 변수와 JSON 출력 계약은
[`docs/PERSONA_HISTORY_PROMPT_HOOKS_KO.md`](docs/PERSONA_HISTORY_PROMPT_HOOKS_KO.md)에 있다.

## 데이터 경계

활성 평가 입력은 저장소 루트 `data/crisis_goals_jmir_persona_min10.jsonl`과
`data/goal_pathology_routes_n625.jsonl`이다. 기본 31,733개 persona pool은 Git에 포함된
`../data/personas/personas.jsonl`을 사용하고, 필요하면 `$PERSONA_POOL_PATH`로 대체한다.
Qwen이 생성한 `../data/personas/persona_category_labels.jsonl`의 검증 완료 canonical
sidecar는 전체 pool ID와 정확히 일치해야 한다. 생성 checkpoint와 중간 후보는 Git에서
제외한다. 행 수·checksum·추출 절차는
[`docs/DATA_LINEAGE_AND_EXTRACTION_KO.md`](docs/DATA_LINEAGE_AND_EXTRACTION_KO.md)에 기록한다.

API 키는 저장소에 기록하지 않고 환경변수 또는 로컬 `.env`로만 제공한다.
