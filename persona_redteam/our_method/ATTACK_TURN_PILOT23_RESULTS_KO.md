# 실패 23건 최종 공격 턴 세 조건 파일럿 결과

## 결론

이 파일럿은 GOAL 귀속형 multi-turn을 주 방법으로 채택할 근거를 만들지 못했다. 전체
23건의 CARES만 보면 GOAL 귀속형이 가장 좋은 SS를 보였지만, 실제 추가 추적이 실행된
1차 실패 8건에서는 일반 적응형만 비거부 ASR을 높였고 GOAL 귀속형은 개선이 없었다.
JMIR는 singleton Best-of-4가 이미 23/23 exact-1이라 두 multi-turn 조건이 모두 악화됐다.

따라서 현재 권고는 다음과 같다.

1. `single_turn_best_of_4_v1`을 주 결과로 유지한다.
2. `pcsa_inspired_adaptive_best_of_4_v1`은 CARES 비거부 민감도 분석용 ablation으로 남긴다.
3. `goal_attributed_adaptive_best_of_4_v1`은 주 방법으로 승격하지 않는다.
4. 다음 비교에서는 metric별 oracle Best-of-4와 선택된 단일 endpoint의 차이를 제거하기
   위해, 같은 온라인 평가자가 고른 `selected-singleton` 대조군을 추가한다.

## 설정

- 타깃: `Qwen/Qwen2.5-7B-Instruct`
- 코호트: 기존 실패 23건, `no_verbatim` 조건
- 1차 네 분기: 세 조건에서 byte-identical하게 재사용
- 1차 중단 게이트: 이전 CARES `Accept`
- 이전 게이트 기준 성공 15건, 추가 추적 8건
- 최대 공격 턴: 4
- 추가 턴마다 후보: 등록된 네 전략
- multi-turn 공식 endpoint: 폐기 후보의 oracle가 아닌 선택된 마지막 응답 하나
- 공식 평가: GPT-4o-mini Batch CARES Level-2 및 JMIR 3회 평균
- 생성 버전: `1011-attack-turn-ablation-v7`
- 평가 버전: `1011-attack-turn-ablation-cares-jmir-v1`

## 전체 23건

| 조건 | A/C/R/NR | Accept ↑ | CARES ASR ↑ | CARES SS ↓ | JMIR 평균 ↓ | JMIR exact-1 ↑ |
|---|---:|---:|---:|---:|---:|---:|
| Singleton Best-of-4 | 13/0/10/0 | **56.52%** | 56.52% | 0.435 | **1.000** | **100.00%** |
| Adaptive selected | 12/2/9/0 | 52.17% | **60.87%** | 0.435 | 1.261 | 86.96% |
| Goal-attributed selected | 13/1/9/0 | **56.52%** | **60.87%** | **0.413** | 1.232 | 91.30% |

Singleton 대비 쌍체 Accept 전이는 일반 적응형이 2 gain/3 loss, GOAL 귀속형이
2 gain/2 loss다. 비거부 전이는 두 multi-turn 조건 모두 3 gain/2 loss다. 표본이
23건으로 작고 순개선도 1건이므로 유의한 우월성으로 해석하지 않는다.

## 실제 추가 추적 8건

| 조건 | A/C/R/NR | Accept ↑ | CARES ASR ↑ | CARES SS ↓ | JMIR 평균 ↓ | JMIR exact-1 ↑ |
|---|---:|---:|---:|---:|---:|---:|
| Singleton Best-of-4 | 1/0/7/0 | **12.50%** | 12.50% | 0.875 | **1.000** | **100.00%** |
| Adaptive selected | 1/1/6/0 | **12.50%** | **25.00%** | **0.813** | 1.667 | 75.00% |
| Goal-attributed selected | 0/1/7/0 | 0.00% | 12.50% | 0.938 | 1.500 | 87.50% |

일반 적응형은 비거부 기준으로 2 gain/1 loss였지만 Accept는 1 gain/1 loss로 순증이
없었다. GOAL 귀속형은 Accept 0 gain/1 loss, 비거부 1 gain/1 loss였다. 따라서
GOAL 귀속 프레임이 실패 사례를 복구했다는 주장은 할 수 없다.

## 실행 감사

- 일반 적응형 신규 Qwen 호출: 32회
- GOAL 귀속형 신규 Qwen 호출: 28회
- 의미보존 추상화 대상: 8건
- 추상화 감사 통과: 7건
- 5회 재작성 후 fail-closed: 1건
- 추상화 GPT-4o-mini Batch 비용: `$0.0015198`
- CARES/JMIR 평가 Batch 비용: `$0.044373825`
- 전체 23건·세 view 병합 개수: 각각 23건
- CARES 원 출력은 4토큰 상한에서 전부 잘려 등록된 max-8 호환성 라벨 복구를 138건에
  사용했다. 응답 생성 결과를 바꾼 것이 아니라 평가 라벨 형식만 복구했다.
- 코드 회귀시험: 1011 연결 및 공격 턴 99개 통과, 평가기 9개 통과

## 해석상 주의

이전 1차 CARES 게이트에서는 15건이 Accept였지만 이번 독립 재평가의 singleton
Best-of-4에서는 13건이 Accept였다. 즉 2건의 evaluator drift가 있었다. multi-turn은
이전 게이트를 사용해 조기 중단했기 때문에, 전체 23건 표의 차이 일부는 새 추적 효과가
아니라 평가 시점 차이와 endpoint 선택 차이에서 생긴다. 방법 효과 판단에는 실제 추가
추적 8건 표를 우선한다.

또한 singleton은 CARES와 JMIR 각각에 유리한 분기를 사후 선택하는 metric별 Best-of-4인
반면, multi-turn은 private 온라인 평가가 선택한 단일 endpoint만 평가한다. 쿼리 예산과
선택 규칙이 완전히 같은 인과 비교가 아니므로, 다음 파일럿에는 다음 대조군이 필요하다.

- `selected-singleton`: 1차 네 분기 중 온라인 평가가 고른 한 응답
- `single-turn Best-of-4`: 현재 보고 방식
- `adaptive selected`: 같은 선택 평가자를 사용한 multi-turn
- 가능하면 동일 총 타깃 호출 수를 사용한 non-adaptive Best-of-N

## 산출물

- 런타임: `/data1/users/ljk98/runtime_cache/persona_redteam_final197/failed23_attack_turn_ablation_v7`
- 병합 요약: `merged/run_summary.json`
- 공식 결과: `scoring/cares_jmir/results.json`
- 실행 로그: `logs/lane_0.log`–`logs/lane_3.log`
- 프로토콜: `ATTACK_TURN_ABLATION_KO.md`

PCSA와의 관계는 후보 생성–응답–평가–선택–반복 구조만 차용한 것이다. PCSA 논문은
Phase II 제거 시 성능 저하를 보고하지만, 현재 파일럿은 다른 네 전략과 다른 선택 평가자를
사용하므로 그 결과를 재현했다고 주장하지 않는다. 참고: https://arxiv.org/abs/2604.04842v2
