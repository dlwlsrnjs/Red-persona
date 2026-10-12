# PCSA Phase II Persona+History × GPT-4o Final-197

## 결론

Persona+History를 PCSA Phase II attacker에 연결하고 타깃을
`gpt-4o-2024-11-20`으로 고정한 Final-197 생성·평가가 완료됐다. 197건 모두 생성됐고
최종 평가의 누락·invalid는 0건이다.

| 지표 | count | rate |
|---|---:|---:|
| HarmBench | 9/197 | 4.57% |
| PCSA Unsafe | 52/197 | 26.40% |
| PCSA Target Compliance | 52/197 | 26.40% |
| PCSA Harmful | 49/197 | 24.87% |
| R3+ | 56/197 | 28.43% |
| B3+ | 47/197 | 23.86% |
| B4+ | 17/197 | 8.63% |
| R3+ and B4+ | 17/197 | 8.63% |
| Strict Joint | 6/197 | 3.05% |

CARES는 사용자 지정에 따라 `gpt-4o-2024-11-20` Batch로 판정했다.

| CARES | count | rate |
|---|---:|---:|
| Accept | 14/197 | 7.11% |
| Caution | 100/197 | 50.76% |
| Refuse | 83/197 | 42.13% |
| A+C | 114/197 | 57.87% |
| Safety Score | — | 0.6751 |

## 기존 GPT-4o PCSA 셀과의 기술 비교

기존 Final-197 matrix의 PCSA는 고정 profile과 pathology만 사용했고, 새 셀은 동일 cohort에
goal-conditioned persona와 source-history style/state를 추가했다.

| 지표 | 기존 profile-only PCSA | Persona+History PCSA | 차이 |
|---|---:|---:|---:|
| HarmBench | 1/197 (0.51%) | **9/197 (4.57%)** | **+4.06%p** |
| PCSA Unsafe | 8/197 (4.06%) | **52/197 (26.40%)** | **+22.34%p** |
| R3+ | 11/197 (5.58%) | **56/197 (28.43%)** | **+22.84%p** |
| B4+ | 4/197 (2.03%) | **17/197 (8.63%)** | **+6.60%p** |
| Strict Joint | 0/197 (0.00%) | **6/197 (3.05%)** | **+3.05%p** |

이 방향은 Qwen의 paired Persona+History ablation과 일치한다. 즉 persona/history를 PCSA의
attacker conditioning으로 사용할 때 목표 수행 중심 지표가 높아졌다. 다만 위 GPT-4o
비교는 기술 비교다. 기존 matrix target은 정확한 snapshot이 아닌 `gpt-4o` alias로
기록됐고, 기존 개별 HarmBench label이 공개 결과에 없어서 paired McNemar 검정을 재구성할
수 없다.

CARES는 직접 비교하지 않는다. 기존 셀은 `gpt-4o-mini-2024-07-18`, 새 셀은
`gpt-4o-2024-11-20` 판정이므로 분포 차이에 개인화 효과와 evaluator 효과가 섞여 있다.

## 생성 과정 감사

- 3개 disjoint shard: 66 + 66 + 65 = 197건
- 각 canonical slice 안에서 seed 19701로 실행 순서만 섞었으며, 평가는 `case_id`로 결합
- 생성 실패: 0
- 최대 4턴, 턴당 4전략 후보
- 실행 turn: 1턴 6건, 2턴 7건, 3턴 13건, 4턴 171건
- 온라인 evaluator 성공 종료: 35건; 최대 턴 종료: 162건
- 선택 round: 743, target 및 온라인 evaluator logical request 각각 2,972건
- target과 온라인 evaluator 호출은 모두 OpenAI Batch
- 로컬 Qwen attacker만 vLLM, HarmBench만 로컬 GPU 사용

온라인 evaluator 성공 35건 중 최종 HarmBench 양성은 전체 9건뿐이므로 PCSA의 중간 점수는
최종 공격 성공률로 사용하지 않는다.

## 평가 계약

| 역할 | 모델 | 실행 |
|---|---|---|
| Target | `gpt-4o-2024-11-20` | OpenAI Batch |
| Attacker | `Qwen/Qwen2.5-7B-Instruct` | local vLLM |
| Online evaluator | `gpt-4o-mini-2024-07-18` | OpenAI Batch |
| CARES | `gpt-4o-2024-11-20` | OpenAI Batch |
| PCSA final judge | `gpt-4o-2024-11-20` | OpenAI Batch |
| R/B v3 | `gpt-4o-mini-2024-07-18` | OpenAI Batch |
| HarmBench | pinned 13B classifier | local GPU |

R/B Batch의 최초 strict parser에서 8건이 invalid였지만, 저장된 evaluator 원문을
`reprocess_rb_batches.py`로 literal-evidence 호환성만 재검증하여 8건 모두 복구했다. 최종
R/B와 Strict Joint의 invalid/missing은 0이다.

## 코드와 공개 범위

- 생성: `external_baselines/run_pcsa_persona_history_gpt4o_final197{,_sharded}.sh`
- 핵심 PCSA loop: `external_baselines/pcsa_phase2.py`
- 평가: `official_evaluation/run_pcsa_persona_history_gpt4o_final197_eval.sh`
- 기계 결과: `external_baselines/result/pcsa_persona_history_gpt4o_final197.json`

민감한 개별 프롬프트·응답과 Batch 원문은 Git에 올리지 않고, 집계·설정·hash와 재현 코드만
공개한다.
