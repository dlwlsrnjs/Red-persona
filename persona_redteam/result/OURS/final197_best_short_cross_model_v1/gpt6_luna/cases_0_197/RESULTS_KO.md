# gpt-6-luna · Final-197 best short readout

- 방법: 페르소나 이력 + fresh target initial analysis + 분기별 연구 readout 1회
- 표본: 197건 × 독립 최종 분기 4개, 사례별 Best-of-4
- CARES/JMIR/R/B 평가자: GPT-4o (`gpt-4o-2024-11-20`)
- HarmBench: 공식 로컬 분류기

| 지표 | 결과 |
|---|---:|
| CARES A/C/R/NR | 0/4/193/0 |
| CARES Accept | 0.00% |
| CARES ASR | 2.03% |
| CARES SS ↓ | 0.990 |
| JMIR mean ↓ | 1.704 |
| JMIR exact-1 | 8.63% |
| R3+@4 | 97.97% |
| B4+@4 | 0.00% |
| HarmBench+@4 | 5.58% |
| 같은 분기 R3+∧B4+∧HarmBench+@4 | 0.00% |

결합 지표는 서로 다른 분기의 최댓값을 섞지 않고 같은 분기에서 세 조건을 모두 만족한 사례만 센다.
