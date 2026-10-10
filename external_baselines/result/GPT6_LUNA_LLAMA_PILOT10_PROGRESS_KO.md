# GPT-6 Luna · Llama 파일럿 진행 현황

기록 시각: 2026-10-10 16:00 UTC
성격: 외부 베이스라인 추가 실험, 최종 평가 전 진행 스냅샷

## 실험 구성

- 사례: 고정 cohort의 첫 10개
- 방법: 9개
- 대상: GPT-6 Luna, Llama-3.1-8B-Instruct
- 기대 결과: `10 × 9 × 2 = 180`
- GPT-6 Luna/PCSA/최종 평가: OpenAI Batch API 전용
- Llama target/Qwen attacker: 로컬 GPU vLLM
- 최대 대화 턴: 4턴 이하
- 최종 evaluator: `gpt-4o-mini`

## 생성 진행률

두 출력 루트의 결과를 `target/method/case_id`로 중복 제거한 수치다.

| 방법 | GPT-6 Luna | Llama-3.1-8B-Instruct |
|---|---:|---:|
| Direct | 0/10 | 10/10 |
| Skeleton Key | 0/10 | 10/10 |
| Many-shot | 0/10 | 10/10 |
| Red Teaming | 8/10 | 10/10 |
| PAIR | 1/10 | 10/10 |
| TAP | 9/10 | 10/10 |
| Crescendo | 0/10 | 10/10 |
| Therapist Crescendo | 5/10 | 10/10 |
| PCSA Phase 2 adapter | 0/10 | 1/10 |
| 합계 | **23/90** | **81/90** |

전체 고유 완료 수는 **104/180 (57.8%)**다.

## 실행 상태

| Slurm job | 노드 | 역할 | 상태 |
|---|---|---|---|
| `32428` | `h200-1` | 기본 18개 target×method matrix | 실행 중 |
| `32430` | `h200-0` | Luna 9개 방법 및 Llama-PCSA 가속 | 실행 중 |

가속 작업의 최초 제출은 Qwen endpoint 포트와 preflight 기본 포트가 달라 API Batch 제출
전에 종료됐다. 포트를 `8000–8005`로 통일한 뒤 `32430`으로 다시 제출했으며, 최초 실패
작업에서는 OpenAI 요청이 생성되지 않았다.

## 검증된 동작

- Direct, Skeleton Key, Many-shot은 단일 target 호출로 저장된다.
- Red Teaming, PAIR, TAP, 두 Crescendo는 사례별 전체 대화 history를 다음 턴에 전달한다.
- 각 사례의 transcript는 다른 사례와 독립적이다.
- Batch wave는 이전 target 응답이 완성된 후 다음 턴 요청을 만든다.
- PCSA는 고정 persona와 pathology route를 읽어 Phase 2 후보를 생성한다.
- 성공 checkpoint는 재실행 시 건너뛰고 미완료 case만 보충한다.
- 현재 생성 JSON에는 `target_conversation`과 `final_target_response`가 함께 보존된다.

## 성능 해석 상태

CARES/JMIR 최종 평가는 아직 시작되지 않았다. 현재 결과 JSON 안의 내부
task-achievement score는 공격 탐색 제어용이며 최종 공격 성공률이 아니다. 따라서 이
스냅샷에는 CARES SS, JMIR 평균, JMIR harmful rate, A/C/R 또는 non-refuse ASR을
확정값으로 제시하지 않는다.

180개 생성이 완성되면 다음을 수행한다.

1. 모든 `target × method` 셀이 정확히 10개인지 검사
2. 마지막 사용자 발화와 최종 target 응답 추출
3. CARES와 JMIR 요청을 `gpt-4o-mini` Batch로 제출
4. 누락된 `custom_id`만 재제출
5. 평가 결과와 비용을 이 폴더의 확정 결과 문서와 JSON에 기록

## 로컬 산출물 위치

- 기본 출력: `external_baselines/outputs/gpt6_luna_llama31_pilot10/`
- 가속 출력: `external_baselines/outputs/gpt6_luna_llama31_pilot10_accel2/`
- 기본 평가 예정 경로: `external_baselines/evaluations/gpt6_luna_llama31_pilot10/`
- 가속 평가 예정 경로:
  `external_baselines/evaluations/gpt6_luna_llama31_pilot10_accel2/`

이 대용량 산출물은 Git에 포함하지 않고, 재현 설정·핵심 코드·집계 문서만 커밋한다.

## 정식 500개 실행

파일럿 생성과 병행해 정식 실행을 비중복 3개 shard로 제출했다. RTX6000 shard는 즉시
실행하고, H200 shard는 각 노드의 파일럿이 끝나는 즉시 시작한다.

| Slurm job | 노드 | 공식 index 범위 | 사례 수 | 시작 조건 |
|---|---|---:|---:|---|
| `32431` | `rtx6000-0` | 0–199 | 200 | 실행 중 |
| `32432` | `h200-0` | 200–349 | 150 | `32430` 종료 후 |
| `32433` | `h200-1` | 350–499 | 150 | `32428` 종료 후 |
| `32434` | CPU allocation | 전체 병합·평가 | 500 | 세 shard 모두 성공 후 |

RTX6000 작업은 GPU 8개를 모두 사용해 Llama endpoint 1개와 Qwen endpoint 7개를 띄운다.
각 H200 작업은 GPU 7개를 모두 사용해 Llama endpoint 1개와 Qwen endpoint 6개를 띄운다.
두 OpenAI project는 Luna와 PCSA 요청을 Batch로만 처리한다.

최종 작업은 세 shard에서 `SHARD_COMPLETE` 검증을 통과한 경우에만 실행된다. 병합기는
18개 `target × method` 셀마다 공식 case ID 500개가 정확히 한 번씩 있는지 검사하며,
누락이나 중복이 하나라도 있으면 평가 Batch를 제출하지 않는다. 검증 통과 후
CARES/JMIR 평가에 최대 USD 15의 예산 guard를 적용한다.
