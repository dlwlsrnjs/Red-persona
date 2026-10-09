# RED-Persona 활성 파이프라인

이 문서가 저장소 최상위의 현재 구조 인덱스다. 새 실행은 `pipeline/` 모듈만 진입점으로
사용하며, `experiments/`는 구현체·테스트·탐색 파일럿을 보관한다.

## 전체 흐름

```text
JMIR goal 100개
  → goal pathology
  → 전체 persona pool 31,733개에서 동적 검색
  → Qwen 의미 계획 / Lexi 과거 대화 렌더링
  → 누적 persona_state + persona_history
  → goal-aware Qwen ↔ target 누적 연구 대화
  → 동일 누적 prefix 기반 8개 독립 분기
  → candidate_response / research_analysis 분리
  → GPT 평가 + candidate-only CARES
  → 전체·조건·위기범주별 집계
```

## 폴더 지도

| 폴더 | 역할 | 안내 문서 |
|---|---|---|
| `pipeline/` | 활성 API·CLI·계약 검사 | `pipeline/README.md` |
| `configs/persona_history/` | 사용자가 작성할 Lexi 생성·coverage 프롬프트 | `configs/persona_history/README.md` |
| `data/` | 준비 데이터, 생성 이력, 실행·평가 산출물 | `data/README.md` |
| `experiments/` | 실제 구현체, 테스트, 명시적 파일럿 | `experiments/README.md` |
| `evaluation/` | 평가 코드와 고정 평가 프롬프트 | `evaluation/README.md` |
| `docs/` | 실행법, 방법론, 진행 기록 | `docs/README.md` |

## 활성 데이터

- 고정 100개 blueprint: `experiments/fixtures/jmir_persona_eval_set_100.jsonl`
- 전체 625개 blueprint: `data/prepared/blueprints/jmir_eval_full.jsonl`
- 전체 seedless 준비 사례: `data/prepared/cases/jmir_eval_full_pre_generation.json`
- 100개 fixture와 기존 산출물은 파일럿·회귀 검증용으로만 유지
- 전체 persona pool: `/home/jklee/Documents/Codex/2026-09-30-new-chat/derived/full_dataset/personas.jsonl`
- 전체 pool 크기: 31,733개(Cactus 31,577 + CBT-DP 156)
- 24개 축소 profile: 과거 복구 provenance이며 새 실행 기본값이 아님

## 활성 명령

```bash
python3 -m pipeline.prepare ...
python3 -m pipeline.generate_histories ...
python3 -m pipeline.preflight ...
python3 -m pipeline.run_batch ...
python3 -m pipeline.evaluate_batch ...
```

정확한 인자와 순서는 `docs/JMIR_FULL_EXPERIMENT_RUNBOOK_KO.md`를 따른다.

## 현재 완료와 제한

- 전체 pool 로딩·스키마 정규화·goal 원문 기반 검색: 구현 및 테스트 완료
- Qwen micro-plan → Lexi 1턴 렌더링 파일럿: 실행 확인
- Lexi JSON 파싱, 구조화 persona state, 중복 턴 검사: 구현
- 생성 이력을 최초 target context에 포함: 구현 및 테스트 완료
- 8개 분기와 candidate-only CARES 연결: 구현 및 preflight 완료
- Qwen–target 연구 대화의 최소 4턴 이후 coverage 기반 동적 종료: 아직 미구현
- Qwen–Lexi staged 생성의 전체 625개 본 실행: 아직 미실행

## 검증

```bash
python3 -m unittest discover -s experiments -p 'test_*.py'
python3 -m compileall -q pipeline experiments
python3 -m pipeline.preflight --prepared-cases data/prepared/cases/jmir_eval_full_pre_generation.json
```
