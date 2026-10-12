# Final-197 Qwen Short-Readout 결과

이 폴더는 Final-197에서 수행한 Qwen 타깃 실험을 기록한다. 타깃은
`Qwen/Qwen2.5-7B-Instruct`, 연구 대화 생성 모델은
`meta-llama/Llama-3.1-8B-Instruct` revision
`0e9e39f249a16976918f6564b8830bc894c89659`이다. 각 사례에서 네 개의 독립
최종 분기를 생성하고 지표별 Best-of-4를 보고한다. 평가기는
`gpt-4o-2024-11-20`로 고정했다.

## 공개 가능한 완결 결과

| 조건 | 상태 | A/C/R/NR | Accept | JMIR exact-1 | R3+@4 | B4+@4 | HarmBench+@4 | 동일 분기 Strict Joint@4 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Short readout + history | **완결** | 197/0/0/0 | **100.00%** | **100.00%** | 97.97% | 96.45% | 96.45% | 90.86% |
| Short readout, no history | 부분 평가 | 197/0/0/0 | **100.00%** | 94.42% | — | — | — | — |

History 조건은 197개 사례와 788개 분기 생성, CARES/JMIR, R/B, HarmBench가
모두 완결됐다. Strict Joint는 같은 분기에서
`R3+ ∧ B4+ ∧ HarmBench+`를 만족한 사례 비율이다.

No-history 조건도 197개 사례와 788개 분기 생성 및 CARES/JMIR는 완결됐다.
그러나 R/B Batch 1차 요청 1,576개 중 1,492개만 완료된 시점에 프로젝트 결제
한도에 도달했다. 따라서 R/B, HarmBench 및 Strict Joint 값은 추정하거나
부분 표본으로 보고하지 않는다. 남은 R/B 84개와 후속 검증을 끝낸 뒤 같은
행을 갱신해야 한다.

## 해석

완결된 History 조건에서 CARES와 JMIR는 모두 100%였지만, 보다 보수적인 동일
분기 결합은 90.86%였다. 즉, 서로 다른 분기에서 얻은 지표를 임의로 결합하지
않아도 179/197개 사례에서 목표 복원, 구체적 행동 응답, HarmBench 양성이 동시에
관찰됐다.

No-history의 CARES Accept 역시 100%였으나 JMIR exact-1은 94.42%로 History
조건보다 5.58%p 낮았다. R/B와 HarmBench가 미완료이므로 이 차이만으로 history
효과 전체를 결론내리지 않는다.

## 파일

- `RESULTS.csv`: 통계 및 도표용 평탄화 결과
- `RESULTS.json`: 상태 필드를 포함한 기계 판독 결과
- `PAPER_TABLE.tex`: 논문용 표. 미완료 지표를 명시적으로 표시
- `PROVENANCE.json`: 로컬 원본 집계의 경로와 SHA-256
- `source_snapshots/`: 공개 가능한 aggregate-only 원본 요약

사례별 원 요청·응답과 API 자격 증명은 저장소에 포함하지 않는다.
