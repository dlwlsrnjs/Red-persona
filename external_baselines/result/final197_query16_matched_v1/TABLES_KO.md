# Final-197 query-16 결과표

## 동일 평가 프로토콜 결과

| Target | Method | Calls mean/max | A/C/R/NR | Accept | CARES ASR | SS | HarmBench | PCSA unsafe | R3+ | B4+ | Strict | Qwen3Guard unsafe |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GPT-4o | Red Teaming | 9.13/16 | 25/120/52/0 | 12.69% | 73.60% | 0.569 | 18/197 (9.14%) | 30/197 (15.23%) | 16.24% | 0.51% | 0.00% | 7/197 (3.55%) |
| GPT-4o | Crescendo | 12.39/14 | 27/107/63/0 | 13.71% | 68.02% | 0.591 | 9/197 (4.57%) | 25/197 (12.69%) | 14.72% | 0.00% | 0.00% | 7/197 (3.55%) |
| GPT-4o | Therapist Crescendo | 12.57/14 | 7/114/76/0 | 3.55% | 61.42% | 0.675 | 9/197 (4.57%) | 18/197 (9.14%) | 11.68% | 0.00% | 0.00% | 5/197 (2.54%) |
| Qwen-2.5-7B-Instruct | Red Teaming | 6.27/16 | 44/133/20/0 | 22.34% | 89.85% | 0.439 | 58/197 (29.44%) | 102/197 (51.78%) | 39.09% | 7.11% | 7.11% | 29/197 (14.72%) |
| Qwen-2.5-7B-Instruct | Crescendo | 12.20/14 | 39/120/38/0 | 19.80% | 80.71% | 0.497 | 48/197 (24.37%) | 80/197 (40.61%) | 42.64% | 6.09% | 5.08% | 26/197 (13.20%) |
| Qwen-2.5-7B-Instruct | Therapist Crescendo | 11.96/14 | 19/131/47/0 | 9.64% | 76.14% | 0.571 | 34/197 (17.26%) | 57/197 (28.93%) | 27.41% | 8.12% | 7.11% | 22/197 (11.17%) |

## HarmBench 호출 예산 민감도

| Target | Method | Prior cap | Query-16 cap | Prior HB | Query-16 HB | Delta |
|---|---|---:|---:|---:|---:|---:|
| GPT-4o | Red Teaming | 4 | 16 | 17/197 (8.63%) | 18/197 (9.14%) | +0.51 pp |
| GPT-4o | Crescendo | 6 | 16 | 10/197 (5.08%) | 9/197 (4.57%) | -0.51 pp |
| GPT-4o | Therapist Crescendo | 6 | 16 | 4/197 (2.03%) | 9/197 (4.57%) | +2.54 pp |
| Qwen-2.5-7B-Instruct | Red Teaming | 4 | 16 | 42/197 (21.32%) | 58/197 (29.44%) | +8.12 pp |
| Qwen-2.5-7B-Instruct | Crescendo | 6 | 16 | 39/197 (19.80%) | 48/197 (24.37%) | +4.57 pp |
| Qwen-2.5-7B-Instruct | Therapist Crescendo | 6 | 16 | 23/197 (11.68%) | 34/197 (17.26%) | +5.58 pp |

## 14--16 target-call 외부 기법 순위

| Target | Rank | Method | Query cap | HarmBench | Source |
|---|---:|---|---:|---:|---|
| GPT-4o | 1 | PAIR | 15 | 29/197 (14.72%) | reused prior run; budget already <=16 |
| GPT-4o | 2 | TAP | 14 | 28/197 (14.21%) | reused prior run; budget already <=16 |
| GPT-4o | 3 | Red Teaming | 16 | 18/197 (9.14%) | query-16 rerun |
| GPT-4o | 4 | Crescendo | 16 | 9/197 (4.57%) | query-16 rerun |
| GPT-4o | 5 | Therapist Crescendo | 16 | 9/197 (4.57%) | query-16 rerun |
| GPT-4o | 6 | PCSA Phase II | 16 | 1/197 (0.51%) | reused prior run; budget already <=16 |
| Qwen-2.5-7B-Instruct | 1 | TAP | 14 | 85/197 (43.15%) | reused prior run; budget already <=16 |
| Qwen-2.5-7B-Instruct | 2 | PAIR | 15 | 71/197 (36.04%) | reused prior run; budget already <=16 |
| Qwen-2.5-7B-Instruct | 3 | Red Teaming | 16 | 58/197 (29.44%) | query-16 rerun |
| Qwen-2.5-7B-Instruct | 4 | Crescendo | 16 | 48/197 (24.37%) | query-16 rerun |
| Qwen-2.5-7B-Instruct | 5 | Therapist Crescendo | 16 | 34/197 (17.26%) | query-16 rerun |
| Qwen-2.5-7B-Instruct | 6 | PCSA Phase II | 16 | 4/197 (2.03%) | reused prior run; budget already <=16 |

주: Qwen Red Teaming의 R/B 보조 판정 1건은 반복 재판정 후에도 literal-evidence 검증을 통과하지 못해 invalid로 보존했으며 R3+/B4+/Strict에는 보수적으로 0을 기여한다. HarmBench, CARES, PCSA 및 Qwen3Guard는 6개 셀 모두 197/197 valid다.
