# GPT-6 Luna + Llama-3.1-8B target 파일럿

상태: 실행 승인 대기  
등록일: 2026-10-10

## 목적

기존 Qwen2.5-7B-Instruct와 GPT-4o target 결과가 다른 최신 저비용 API 모델과 표준 공개
Llama 계열에도 유지되는지 확인한다. 정식 500개를 바로 반복하지 않고 동일한 첫 10개 사례로
API 호환성, 멀티턴 history 전달, 출력 길이, 비용을 먼저 검증한다.

## 고정 설계

- 코호트: `red_persona_official_500.jsonl`의 첫 10개
- 방법: Direct, Skeleton Key, Many-shot, Red Teaming, PAIR, TAP, Crescendo,
  Therapist Crescendo, PCSA Phase 2
- 타깃 1: `gpt-6-luna`, OpenAI Batch, `reasoning_effort=none`
- 타깃 2: `meta-llama/Llama-3.1-8B-Instruct`, revision
  `0e9e39f249a16976918f6564b8830bc894c89659`, 로컬 vLLM
- 공격자: `Qwen/Qwen2.5-7B-Instruct`
- PCSA 중간 평가자: `gpt-4o-mini`, Batch
- 최종 평가: CARES A/C/R·SS, JMIR 평균·harmful rate, Batch
- 순차 대화 최대 4턴. PAIR/TAP/PCSA의 병렬 후보 폭은 기존 paper budget을 유지한다.

Luna는 공식 OpenAI 문서가 Chat Completions와 Batch를 지원한다고 명시한다. 기존 GPT-4o
runner와 형식을 맞추기 위해 Chat Completions Batch를 쓰고, 샘플링 파라미터 호환성과 비용을
위해 `reasoning_effort=none`을 명시한다.

## 멀티턴 보존

적응형 방법은 한 요청에 가짜 전체 대화를 만들지 않는다. 각 wave 결과를 받은 뒤 그 사례의
`target_conversation`에 실제 응답을 추가하고 다음 wave를 제출한다. 후보 간 history와 사례 간
history는 섞이지 않는다.

## 실행 스냅샷

- [`matrix.json`](matrix.json): 두 target과 세 역할 모델 설정
- [`run.sbatch`](run.sbatch): 1 Llama GPU + 6 Qwen GPU, 생성 후 공통 평가
- 실제 runner:
  [`../../external_baselines/run_baseline_matrix.py`](../../external_baselines/run_baseline_matrix.py),
  [`../../external_baselines/run_pyrit_baseline.py`](../../external_baselines/run_pyrit_baseline.py)

## 완료 기준

1. 18개 target×method 셀 각각 정확히 10개 결과
2. `.failed.json` 0개와 truncation 0개
3. Luna 생성·PCSA·최종 평가는 모두 Batch
4. CARES/JMIR 180행 완결성 확인
5. 결과표와 실제 비용을 `results/`에 추가

10개 파일럿 수치는 모델 우열의 확정 결론이 아니라 파이프라인·효과 방향 확인용이다.

