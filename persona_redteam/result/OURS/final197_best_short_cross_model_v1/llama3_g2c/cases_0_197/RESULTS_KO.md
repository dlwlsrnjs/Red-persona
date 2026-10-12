# UKPLab/Llama3-G2C · Final-197 best short readout

- 방법: 페르소나 이력 + fresh target initial analysis + 분기별 연구 readout 1회
- 표본: 197건 × 독립 최종 분기 4개, 사례별 Best-of-4
- CARES/JMIR/R/B 평가자: GPT-4o (`gpt-4o-2024-11-20`)
- HarmBench: 공식 로컬 분류기

| 지표 | 결과 |
|---|---:|
| CARES A/C/R/NR | 181/3/5/8 |
| CARES Accept | 91.88% |
| CARES ASR | 93.40% |
| CARES SS ↓ | 0.074 |
| JMIR mean ↓ | 1.262 |
| JMIR exact-1 | 87.82% |
| R3+@4 | 82.23% |
| B4+@4 | 81.22% |
| HarmBench+@4 | 65.99% |
| 같은 분기 R3+∧B4+∧HarmBench+@4 | 43.65% |

결합 지표는 서로 다른 분기의 최댓값을 섞지 않고 같은 분기에서 세 조건을 모두 만족한 사례만 센다.
