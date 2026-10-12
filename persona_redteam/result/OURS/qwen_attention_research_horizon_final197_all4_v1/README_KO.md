# Final-197 Qwen Attention 전체 분석

이 폴더는 `direct GOAL`, `single-readout`, `long 7-stage` 조건을 동일한
Qwen2.5-7B-Instruct proxy로 재생한 설명적 attention 분석 결과다.

- 197 cases × 4 preregistered branches = 788 analyses
- 네 분기를 사례 안에서 먼저 평균한 case-clustered aggregation
- 사례 단위 bootstrap 10,000회, 95% CI
- Qwen revision: `a09a35458c702b33eeacc393d103063234e8bc28`
- private GOAL 원문은 aggregate 결과에 저장하지 않음

공개 결과는 `aggregate/`에 있다.

- `ATTENTION_COHORT_REPORT_KO.md`: 방법, 전체 수치 및 제한
- `attention_cohort_comparison.png`: 논문용 정적 그림
- `aggregate_metrics.json`: 레이어·구간 평균과 bootstrap CI
- `case_level_metrics.csv`: 197개 사례별 네 분기 평균

`shards/`의 788개 개별 attention JSON/PNG는 저장소 크기 때문에 Git에 포함하지
않는다. `aggregate_metrics.json`의 `source_manifest_sha256`은 집계에 사용된
788개 원본 JSON 해시의 정렬된 manifest를 다시 해시한 값이다.

이 결과는 GPT-4o 내부 attention 측정이 아니다. Attention 유사도만으로 유해한
자극이나 안전 정책 우회의 인과적 메커니즘을 주장하지 않는다.
