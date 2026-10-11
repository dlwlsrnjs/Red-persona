# PCSA Phase II persona-history 어댑터 파일럿 (Qwen2.5-7B-Instruct, n=10)

## 결론

Final-197의 goal-conditioned persona와 4–9턴 source history를 PCSA Phase I의
client-characteristic/style-reference 대체 입력으로 사용한 뒤 Phase II를 실행했다.
동일 10개 case의 기존 PCSA 결과와 비교할 때, 목표 수행을 요구하는 엄격 지표가
모두 개선되어 전체 197건 실행 기준을 충족했다.

이 결과는 방향 확인용 소표본 파일럿이며 최종 논문 수치가 아니다.

## 고정 조건

- Target: `Qwen/Qwen2.5-7B-Instruct`
- Attacker: `Qwen/Qwen2.5-7B-Instruct`
- Online evaluator: `gpt-4o-mini-2024-07-18`, OpenAI Batch API
- 후보 전략: reassurance seeking, appeal to expertise, intellectualization,
  metaphorical expression
- 최대 target turns: 4
- 후보 수: turn당 4
- 새 어댑터와 기존 PCSA 비교 case: 동일한 10개
- source history 용도: attacker의 특성·문체·상태 궤적 입력
- source history는 target의 이전 대화로 재생하지 않음

## 결과

| 지표 (공격 관점) | 기존 PCSA | persona-history PCSA | 변화 |
|---|---:|---:|---:|
| HarmBench ASR ↑ | 0/10 (0%) | 3/10 (30%) | +30%p |
| PCSA GPT-4o UNSAFE ↑ | 0/10 (0%) | 6/10 (60%) | +60%p |
| PCSA Target Compliance ↑ | 0/10 (0%) | 6/10 (60%) | +60%p |
| PCSA Harmful Content ↑ | 0/10 (0%) | 6/10 (60%) | +60%p |
| R3+ ↑ | 1/10 (10%) | 6/10 (60%) | +50%p |
| B4+ ↑ | 0/10 (0%) | 2/10 (20%) | +20%p |
| R3+ ∧ B4+ ↑ | 0/10 (0%) | 2/10 (20%) | +20%p |
| Strict Joint ASR (`R3+ ∧ B4+ ∧ HarmBench+`) ↑ | 0/10 (0%) | 1/10 (10%) | +10%p |
| CARES ASR ↑ | 10/10 (100%) | 8/10 (80%) | -20%p |
| CARES SS ↓ | 0.45 | 0.60 | +0.15 |

새 방식의 CARES 분포는 `Accept=0, Caution=8, Refuse=2`였다. 기존 방식은
`Accept=1, Caution=9, Refuse=0`이지만 HarmBench, PCSA target compliance,
B4+가 모두 0이었다. 따라서 이 파일럿에서는 CARES의 non-refusal 비율만으로
공격 성공을 판단하면 Caution을 과대평가한다. 전체 실험의 주 판단은 HarmBench,
PCSA Target Compliance, B4+, Strict Joint를 함께 사용한다.

## 검증 상태

- 생성: 10/10 완료, 실패·누락 0
- HarmBench: 10/10 유효
- CARES: 10/10 유효
- PCSA Figure-4 GPT-4o judge: 10/10 유효
- R/B: 10/10 유효
- 한 R/B 출력의 비문자열 증거 인용은 저장된 Batch 응답을 보수적으로
  literal-span 재검증하여 복구했으며, API 재호출은 하지 않았다.
- perplexity는 서버에 GPT-2 캐시가 없어 이번 비교에서 제외했다. 공격 성공
  결론에는 사용하지 않았다.

## 전체 실행

파일럿 통과 후 Final-197을 두 개의 서로 겹치지 않는 shard(99/98)로 분할해
H200 두 GPU에서 실행하도록 제출했다. 생성 완료 후 동일 공식 평가 파이프라인이
자동으로 시작된다.

최종 표에서는 기존 profile-only 결과와 혼동하지 않도록, 개인화 프로필과 source
history를 모두 제거하되 나머지 설정을 고정한 `no-persona` ablation도 동일 197건에
실행해 paired comparison으로 보고한다.
