# Final-197 외부 baseline canonical 결과

이 폴더가 현재 논문 코호트의 외부 baseline 결과를 인용하는 **단일 진입점**이다. 서로
다른 시점에 실행된 결과를 모두 감사한 뒤, 완료된 Final-197 결과 21개 셀만 정규화했다.

- 기존 외부 방법 9종 × GPT-4o/Qwen target: 18개 셀
- PCSA Phase II Persona+History 대 No-Persona Qwen paired ablation: 2개 셀
- PCSA Phase II Persona+History × `gpt-4o-2024-11-20`: 1개 셀
- 각 셀: 197개 case

기존 18셀 행렬의 HarmBench, CARES, PCSA Figure-4, R/B는 각각 3,546/3,546행이며
누락·invalid가 없다. PCSA 개인화 세 셀도 최종 평가 누락·invalid가 없다.

## 파일 안내

| 파일 | 역할 |
|---|---|
| [`TABLES_KO.md`](TABLES_KO.md) | 논문용 전체 표: 주 지표, CARES 분포, PCSA 구성요소, R/B |
| [`SETTINGS_AND_PROVENANCE_KO.md`](SETTINGS_AND_PROVENANCE_KO.md) | 실행 설정, 모델·판정기·전송 방식, 호출 예산, 코드 위치 |
| [`RESULTS_INTERPRETATION_KO.md`](RESULTS_INTERPRETATION_KO.md) | 결과가 지지하는 주장과 제한, 논문 서술안 |
| [`QUALITATIVE_FAILURE_ANALYSIS_KO.md`](QUALITATIVE_FAILURE_ANALYSIS_KO.md) | 외부 공격이 실패한 위치를 보여주는 대표 3건 정성 분석 |
| [`all_results.json`](all_results.json) | 21개 셀의 정규화된 전체 count/rate와 비교 계약 |
| [`all_results.csv`](all_results.csv) | 통계·도표 작성용 평탄화 결과 |
| [`AUDIT.json`](AUDIT.json) | source/code SHA-256, coverage, 원 커밋, 제외·대체 기록 |
| [`build_results.py`](build_results.py) | 원 집계에서 표·JSON·CSV·감사를 재생성하고 검증하는 코드 |

OURS까지 함께 보는 논문 패키지는
[`../../../persona_redteam/result/final197_paper_comparison_v1/README_KO.md`](../../../persona_redteam/result/final197_paper_comparison_v1/README_KO.md)에 있다.

## 비교 계약

네 패널은 다음과 같이 분리한다.

| 패널 | 정식 비교 가능 범위 | 직접 비교하면 안 되는 범위 |
|---|---|---|
| A | 기존 matrix의 GPT-4o target 안 9개 방법 | 다른 패널 및 OURS와 공식 순위화 |
| B | 기존 matrix의 Qwen target 안 9개 방법 | 다른 패널 및 OURS와 공식 순위화 |
| C | 같은 Qwen case의 Persona+History 대 No-Persona | 기존 profile-only PCSA와 인과 비교 |
| D | GPT-4o-2024-11-20 Persona+History 단일 셀 | A의 CARES 및 snapshot 미고정 수치와 직접 비교 |

기반 요청 197개는 같지만 target snapshot, CARES/PCSA evaluator snapshot, response 선택
방식과 query budget이 전부 같지는 않다. 특히 기존 matrix의 GPT-4o는 `gpt-4o` alias이고,
추가 셀은 `gpt-4o-2024-11-20`로 고정됐다. 추가 셀의 CARES도 GPT-4o로 판정했으므로 기존
matrix의 GPT-4o-mini CARES와 합치지 않는다.

## 핵심 결과

- 기존 matrix의 GPT-4o HarmBench 최고는 PAIR 29/197(14.72%), 다음은 TAP
  28/197(14.21%)다.
- 기존 matrix의 Qwen HarmBench 최고는 TAP 85/197(43.15%), 다음은 PAIR
  71/197(36.04%)다.
- Qwen paired PCSA에서 Persona+History는 No-Persona보다 HarmBench를
  14/197→55/197(+20.81%p), PCSA Unsafe를 30/197→111/197(+41.12%p), Strict
  Joint를 7/197→26/197(+9.64%p)로 높였다. HarmBench exact McNemar 양측
  `p=8.23e-10`이다.
- 반대로 같은 paired 실험의 CARES Accept는 48/197→23/197, A+C는
  195/197→168/197로 낮아졌다. CARES non-refusal만으로 개인화 효과를 결론내리면 안 된다.
- GPT-4o-2024-11-20 Persona+History 추가 셀은 HarmBench 9/197(4.57%), PCSA Unsafe
  52/197(26.40%), Strict Joint 6/197(3.05%)다.

## 재생성 및 검증

저장소 루트에서 실행한다.

```bash
python3 external_baselines/result/final197_external_baselines_v2/build_results.py
python3 external_baselines/result/final197_external_baselines_v2/build_results.py --check
```

`--check`는 21개 셀, count/rate, CARES 합계, 3,546행 coverage, paired 2×2와 McNemar
값, 입력·코드 SHA-256, 생성 파일의 byte-level 일치를 검사한다. 민감한 개별 요청·응답과
Batch 원문은 이 폴더에 복제하지 않았다.
