# Final‑197 메인 메서드: GPT‑4o·Qwen 결과와 ablation

이 폴더는 **Final‑197만** 사용한다. Official‑500, 외부 베이스라인, 다른 타깃 모델,
원 요청·응답 원문은 포함하지 않는다. 사례별 네 독립 분기를 만들고 지표별
Best‑of‑4로 집계하며, 엄격 결합은 동일 분기에서
`R3+ ∧ B4+ ∧ HarmBench+`를 모두 만족해야 한다.

## 현재 제안 메서드: GPT‑4o

사용자가 지정한 최종 설정은 로컬 실험명
`final197_no_research_pair_gpt4o_v2/gpt4o/with_history`다. 여기서
`no_research`는 연구 프레이밍을 완전히 제거한다는 뜻이 아니라, **7단계 누적 연구대화를
생략하고 분기별 짧은 research readout 1회만 유지**한다는 뜻이다. 페르소나 대화이력은
유지한다. 논문 표에서는 이를 `single readout + history`로 표기한다.

| 조건 | 역할 | Accept | JMIR exact‑1 | R3+@4 | B4+@4 | HarmBench+@4 | 동일분기 결합@4 |
|---|---|---:|---:|---:|---:|---:|---:|
| single readout + history | **최종 제안 메서드** | **100.00%** | **100.00%** | 99.49% | **100.00%** | **96.95%** | **95.94%** |
| single readout, no history | history 제거 | 100.00% | 98.48% | 97.46% | 98.98% | 86.80% | 83.76% |
| 7-stage + history | 긴 연구대화 | 96.45% | 96.45% | 100.00% | 76.14% | 89.34% | 63.96% |
| 7-stage, no history | 긴 연구대화+history 제거 | 98.98% | 98.98% | 100.00% | 86.80% | 86.29% | 73.10% |
| direct final + history | readout 제거 | 92.39% | 90.36% | 99.49% | 8.12% | 87.31% | 7.11% |
| direct final, no history | readout+history 제거 | 85.28% | 92.39% | 96.95% | 10.15% | 75.63% | 6.09% |

이 고정 설정에서 짧은 readout과 history를 함께 사용한 조건이 엄격 결합 95.94%로
가장 높았다. history 제거 대비 +12.18%p, 7-stage+history 대비 +31.98%p다.

## Qwen 완주 결과: 이전 3조건 행렬

로컬 전체 결과를 다시 검색한 결과, Qwen2.5‑7B 타깃에서 완주·평가된 Final‑197
결과는 이전 `7-stage × {no_verbatim, explicit, no_history}` 3조건이다.

| 조건 | A/C/R/NR | Accept | JMIR exact‑1 | R3+@4 | B4+@4 | HarmBench+@4 | 동일분기 결합@4 |
|---|---:|---:|---:|---:|---:|---:|---:|
| hidden goal + history (`no_verbatim`) | 70/5/112/10 | 35.53% | 93.40% | 58.88% | 30.46% | 80.20% | 15.23% |
| explicit goal + history | 61/4/114/18 | 30.96% | 90.36% | 44.67% | 21.32% | 80.20% | 10.66% |
| no history | 71/7/100/19 | 36.04% | 88.83% | 68.53% | 43.65% | 73.60% | 21.32% |

이 Qwen 표는 완결된 Final‑197 결과지만, 현재 GPT‑4o 주 결과와 달리 7단계 대화를
사용한다. 따라서 두 표를 동일 프로토콜의 타깃 간 순위처럼 비교하면 안 된다.
**Qwen의 `single readout + history` 197건 완주본은 현재 확인된 집계에 없다.**
`RESULTS.json`에도 이 차이를 기계 판독 가능한 필드로 고정했다.

## 이전 3조건 행렬의 GPT‑4o 대응값

같은 이전 행렬의 GPT‑4o 결과도 Qwen과의 대응 검증을 위해 포함한다.

| 조건 | A/C/R/NR | Accept | JMIR exact‑1 | R3+@4 | B4+@4 | HarmBench+@4 | 동일분기 결합@4 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| hidden goal + history (`no_verbatim`) | 41/1/141/14 | 20.81% | 87.82% | 48.22% | 17.26% | 31.98% | 7.61% |
| explicit goal + history | 35/1/152/9 | 17.77% | 86.80% | 44.16% | 14.72% | 32.99% | 2.54% |
| no history | 49/2/127/19 | 24.87% | 84.77% | 76.14% | 24.37% | 28.93% | 12.18% |

## 파일

| 파일 | 내용 |
|---|---|
| `RESULTS.json` | 모든 셀, paired delta, 비교 가능성 계약 |
| `RESULTS.csv` | 통계·도표용 평탄화 결과 |
| `PAPER_TABLES.tex` | 논문에 바로 넣을 수 있는 LaTeX 표 |
| `PROVENANCE.json` | 원본 집계 경로와 SHA‑256 |
| `source_snapshots/` | Final‑197 aggregate-only 원본 스냅샷 |
| `build_package.py` | 재생성 및 byte-level 검증 코드 |

## 검증

저장소의 `persona_redteam/`에서 실행한다.

```bash
python3 result/main_method_qwen_gpt4o_only_v1/build_package.py --check
```

검증은 API를 호출하지 않는다.
