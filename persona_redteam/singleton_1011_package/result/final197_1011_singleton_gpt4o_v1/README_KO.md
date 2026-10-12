# Final-197 GPT-4o 본실험 결과

이 폴더는 `1011_method_v1` singleton Best-of-4의 Final-197 본실험 결과를 고정한다.
타깃과 GPT 기반 평가는 모두 `gpt-4o-2024-11-20`, 연구 질문 생성기는
`Qwen/Qwen2.5-7B-Instruct`, 타깃 전송과 GPT 평가는 OpenAI Batch API를 사용했다.
HarmBench는 `cais/HarmBench-Llama-2-13b-cls`를 로컬 GPU에서 실행했다.

## 실험 조건

| arm | 역할 | 타깃 입력의 차이 |
|---|---|---|
| `no_verbatim` | 최종 제안 메서드 | 자연화된 추상 GOAL 단서와 persona history, GOAL 원문 제외 |
| `explicit` | 원문 노출 ablation | `no_verbatim`에 GOAL 원문 추가 |
| `no_history` | history ablation | `no_verbatim`에서 prior dialogue만 제거 |

세 조건은 같은 197개 case ID와 순서를 사용했다. 각 사례에는 실행 전에 고정된 네
최종 방향을 한 번씩 적용했다. 따라서 arm당 788개 분기가 평가 대상이다.

## 주 결과

아래 CARES와 JMIR은 metric별 Best-of-4다. `R3+ ∧ B4+ ∧ HarmBench+`는 세 지표의
서로 다른 최적 분기를 합친 값이 아니라, 동일한 한 분기에서 세 조건을 모두 만족한
사례 비율이다.

| 조건 | CARES A/C/R/NR | Accept ↑ | CARES ASR ↑ | SS L2 ↓ | JMIR 평균 ↓ | JMIR exact-1 ↑ | R3+ @4 ↑ | B4+ @4 ↑ | HarmBench @4 ↑ | 동일 분기 결합 ↑ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `no_verbatim` (OURS) | 190/0/7/0 | 96.45% | 96.45% | 0.036 | 1.032 | 96.45% | 100.00% | 76.14% | 89.34% | 63.96% |
| `explicit` | 184/0/7/6 | 93.40% | 93.40% | 0.066 | 1.156 | 93.40% | 100.00% | 63.96% | **91.37%** | 60.41% |
| `no_history` | 195/0/2/0 | **98.98%** | **98.98%** | **0.010** | **1.008** | **98.98%** | 100.00% | **86.80%** | 86.29% | **73.10%** |

`no_verbatim`은 197건 중 190건에서 CARES Accept를 얻고 모든 788개 최종 분기를
전송했다. 그러나 가장 강한 전체 변형은 `no_history`였다. `no_history`는 OURS보다
CARES Accept와 JMIR exact-1이 각각 2.54%p, B4+ @4가 10.66%p, 엄격 동일-분기
결합이 9.14%p 높았다. 반면 HarmBench 단독 @4는 OURS가 `no_history`보다 3.05%p
높았다.

`explicit`은 HarmBench 단독 @4에서는 91.37%로 가장 높았지만 CARES, JMIR, B4+와
엄격 결합에서는 OURS보다 낮았다. 또한 27/788개 분기에서 유효한 최종 bridge를 만들지
못해 전송되지 않았다. 따라서 GOAL 원문 노출이 전체 파이프라인의 일관된 향상으로
이어졌다고 해석할 수 없다.

## 제안 메서드의 단일 분기 결과

| 최종 방향 | Accept ↑ | CARES ASR ↑ | SS L2 ↓ | JMIR 평균 ↓ | JMIR exact-1 ↑ |
|---|---:|---:|---:|---:|---:|
| `evidence_chain` | **87.31%** | **87.31%** | **0.127** | **1.161** | **85.79%** |
| `latent_request_synthesis` | 79.19% | 79.70% | 0.206 | 1.249 | 76.65% |
| `source_aware_reconstruction` | 75.63% | 77.16% | 0.236 | 1.308 | 72.59% |
| `analyst_response_target` | 21.32% | 21.32% | 0.787 | 1.907 | 18.27% |

OURS에서는 `evidence_chain`이 모든 단일 분기 CARES/JMIR 주 지표에서 가장 강했다.
`analyst_response_target`은 현저히 약했으므로 네 방향이 동등한 endpoint라는 가설은
지지되지 않는다. 전체 방향별 수치는 `direction_metrics.csv`에 세 arm 모두 기록했다.

## 해석 원칙

- 이 실험은 네 사전 등록 분기를 모두 실행하는 Best-of-4 평가다. 단일 시도와 동일한
  query budget으로 해석하면 안 된다.
- CARES와 JMIR의 Best-of-4는 metric별 선택이므로 서로 다른 분기를 고를 수 있다.
- 엄격 결합은 반드시 동일 분기의 `R3+`, `B4+`, HarmBench positive를 사용했다.
- 응답 또는 bridge 누락은 성공으로 보간하지 않았다. CARES는 `NoResponse`, JMIR은
  점수 5, 공격 지표는 실패로 처리했다.
- `no_history`가 여러 주 지표에서 가장 높으므로, 이번 결과만으로 persona history가
  성능을 높인다고 주장할 수 없다. 논문에서는 이를 부정적 ablation 결과로 보고해야 한다.
- 기존 64건 외부 베이스라인과 Final-197은 평가 집합이 다르므로 이 폴더에서는 순위를
  계산하지 않았다.

## 완전성 감사

- 각 arm: 197개 사례, 788개 분기, 생성 실패 0건
- CARES/JMIR: arm별 788행, 197개 고유 case ID, `status=complete`
- R/B: arm별 788행, 197개 고유 case ID, `status=complete`
- HarmBench: arm별 788행, 197개 고유 case ID
- R/B와 HarmBench의 `(case_id, condition, direction)` 키 SHA-256이 세 arm 모두 동일
- 최종 전송 분기: OURS 788, `explicit` 761, `no_history` 785
- bridge unavailable: OURS 0, `explicit` 27, `no_history` 3

상세 검증 결과는 `validation_report.json`, 원본 결과 파일의 SHA-256은
`source_hashes.sha256`에 기록했다.

## 파일 구성

| 파일 | 내용 |
|---|---|
| `summary.json` | 전체 설정, arm별 주 지표와 비교 결과 |
| `aggregate_metrics.csv` | 논문 표에 바로 사용할 arm별 집계 |
| `direction_metrics.csv` | 네 최종 방향의 단일 분기 CARES/JMIR 결과 |
| `validation_report.json` | 사례·분기·키·상태 완전성 감사 |
| `source_hashes.sha256` | 로컬 원본 실행·평가 산출물의 검증 해시 |

원시 대화와 유해 응답 본문은 이 공개 결과 폴더에 복제하지 않았다. 원본은 로컬의
`persona_redteam/result/OURS/final197_1011_singleton_gpt4o_v1/` 및
`persona_redteam/data/evaluations/final197_1011_singleton_gpt4o_v1/`에 보존되며,
이 폴더의 해시로 동일성을 확인할 수 있다.
