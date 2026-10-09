# 현재 진행 상황과 남은 작업

기준일: 2026-10-09

## 활성 구조

```text
JMIR goal/pathology 100개
→ 전체 persona pool 31,733개 동적 검색
→ Qwen 의미 계획 + Lexi 턴별 과거 대화
→ 누적 persona_state/persona_history
→ goal-aware Qwen–target 연구
→ 8개 독립 분기
→ candidate/analysis 분리
→ GPT 및 candidate-only CARES 평가
```

## 데이터 상태

- 고정 blueprint, matched row, 활성 case: 각각 100개
- 전체 pool: Cactus 31,577 + CBT-DP 156 = 31,733개
- 전체 pool: `/home/jklee/Documents/Codex/2026-09-30-new-chat/derived/full_dataset/personas.jsonl`
- 24개 축소 profile은 과거 복구 provenance이며 새 실행 기본값이 아니다.

## 완료

- 전체 pool 스키마 정규화와 goal 원문 기반 검색
- Qwen top-k 의미 재선택과 4단계 micro-plan 파일럿
- Lexi JSON 파싱·재시도·중복 차단·구조화 persona state
- 생성된 전체 history를 target 최초 컨텍스트에 연결
- 3조건 Qwen–target 연구, 8분기, candidate/analysis 분리
- candidate-only CARES, workers 256, checkpoint/resume, preflight

## 남은 작업

- staged Qwen–Lexi 파일럿을 정식 `pipeline.generate_histories` backend로 통합
- `state_delta` 병합과 단계별 Qwen verifier 추가
- Qwen–target 연구 대화를 고정 8턴에서 최소 4턴 이후 coverage 기반 가변 종료로 변경
- anxiety 5개 품질 파일럿 후 100개 history 생성
- 생성 결과 preflight 후 본 target batch와 평가 실행

## 최근 확인

`jmir-eval-003`에서 24개 pool은 무관한 애완동물 self-schema를 골랐지만, 전체 pool은
실직·기술 부족·경력 전환 불안을 가진 `cactus-24521-1a932d0c4fe5`를 선택했다.
전체 pool 검색은 약 4.3초였고 테스트는 69개 통과, 환경 의존 1개 skip이다.

파일럿 결과: `data/pilots/qwen-lexi-history/`
