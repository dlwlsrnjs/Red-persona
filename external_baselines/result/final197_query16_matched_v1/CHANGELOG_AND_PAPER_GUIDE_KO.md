# Query-16 변경 지점과 논문 반영 가이드

## 한 줄 결론

Final-197에서 target 호출 상한을 14--16회로 맞추면 Qwen target의 세 재실행
baseline은 HarmBench가 모두 상승했지만, GPT-4o target에서는 Red Teaming과 Therapist
Crescendo만 상승하고 Crescendo는 1건 감소했다. 따라서 이 실험은 “더 많은 턴이 항상
성능을 높인다”가 아니라 **동일 호출 예산에서의 모델별·전략별 민감도**를 보여준다.

## 코드에서 바뀐 위치

| 위치 | 변경 내용 | 이유 |
|---|---|---|
| `external_baselines/run_baseline_matrix.py` | `query16` budget profile과 실제·이론 호출 예산 기록 | OURS의 최대 16 target 호출과 외부 반복형 공격의 상한을 맞추기 위해 |
| `external_baselines/run_query16_gpt4o_qwen_final197.sh` | GPT-4o/Qwen × 3개 재실행 셀 launcher | 기존 상한이 4--6회였던 방법만 다시 실행하기 위해 |
| `external_baselines/run_pyrit_baseline.py` | Batch coalescing 설정, `--retry-failed-only` 복구 모드 | 완료 checkpoint를 보존하고 실패 case만 빠르게 복구하기 위해 |
| `official_evaluation/prepare_single_baseline_cell.py` | `--allow-incomplete` 선평가 모드 | 실행 중 완료 checkpoint를 먼저 평가해 총 시간을 줄이기 위해; 기본은 여전히 완결성 엄격 검사 |
| `official_evaluation/evaluate_qwen3guard.py` | Qwen3Guard-Gen-8B 보조 평가 | HarmBench·CARES와 독립된 보조 안전축을 남기기 위해 |
| `external_baselines/result/final197_query16_matched_v1/build_results.py` | 6개 셀 감사·집계, 예산 민감도·순위·LaTeX 생성 | 표와 본문을 원자료에서 결정적으로 재생성하기 위해 |

## 논문에서 바꿀 위치

### 1. Experimental Setup / Query Budget

외부 반복형 공격의 target-query 상한을 다음처럼 명시한다.

- Red Teaming: 최대 16회
- Crescendo: 최대 14 turns + 최대 2 backtracks, 총 상한 16회
- Therapist Crescendo: 최대 14 turns + 최대 2 backtracks, 총 상한 16회
- PAIR: 5 streams × 3 iterations, 최대 15회(기존 결과 재사용)
- TAP: width 2, branching 2, depth 4, 최대 14회(기존 결과 재사용)
- PCSA Phase II: 4 candidates × 4 turns, 최대 16회(기존 결과 재사용)

조기 성공은 허용했으며 실제 target 응답 턴 수의 평균/최댓값도 함께 보고한다. 이 조정은
호출 상한을 맞추지만 공격의 탐색 topology까지 동일하게 만들지는 않는다.

### 2. Research Question

다음 RQ를 추가하는 것이 적절하다.

> **RQ-Budget.** When iterative baselines are allowed a comparable maximum target-query
> budget, how sensitive are attack success rates to the additional interaction budget across
> target models and attack strategies?

### 3. Results

`paper_tables.tex`의 세 표를 사용한다.

1. `tab:query16-main`: 동일 GPT-4o 평가 프로토콜의 6개 재실행 셀
2. `tab:query16-sensitivity`: 기존 상한 대비 HarmBench 증감
3. `tab:query16-ranking`: 호출 상한 14--16인 외부 방법끼리의 HarmBench 순위

정확한 결과 서술은 `paper_results_paragraphs.tex`에 있다. 핵심 HarmBench 변화는 다음과
같다.

| Target | Red Teaming | Crescendo | Therapist Crescendo |
|---|---:|---:|---:|
| GPT-4o | 8.63→9.14% (+0.51 pp) | 5.08→4.57% (-0.51 pp) | 2.03→4.57% (+2.54 pp) |
| Qwen-2.5-7B-Instruct | 21.32→29.44% (+8.12 pp) | 19.80→24.37% (+4.57 pp) | 11.68→17.26% (+5.58 pp) |

### 4. Appendix / Auxiliary Metrics

Qwen3Guard의 `Unsafe`와 `Unsafe-or-Controversial`은 보조표로만 둔다. CARES, PCSA
Figure-4 judge, R3+/B4+/Strict Joint를 하나의 합성 점수로 섞지 않는다.

### 5. Limitations / Fair-comparison note

- 이번 query-16 CARES와 R/B 판정기는 GPT-4o이고, 이전 matrix의 해당 판정기는
  GPT-4o-mini다. 따라서 이 두 지표의 이전 대비 증감은 주장하지 않는다.
- HarmBench는 같은 고정 classifier를 사용하므로 예산 민감도 비교가 가능하다.
- OURS는 사례별 Best-of-4이고 외부 baseline은 하나의 최종 응답이다. target 호출 상한은
  유사하지만 response-selection unit은 같지 않으므로 공식적인 동일 조건 순위라고
  표현하지 않는다.
- 공격별 탐색 폭·backtracking·early stopping 구조가 다르므로 16은 동일 계산량이 아니라
  동일한 최대 target-query 상한이다.
- Qwen Red Teaming의 R/B 보조 판정 1건은 반복 재판정 뒤에도 literal-evidence 검증을
  통과하지 못했다. 이 행은 누락하거나 성공으로 간주하지 않고 R/B 및 Strict에 0으로
  기여시켰다. HarmBench·CARES 등 주 지표에는 invalid가 없다.

## 권장 주장과 피해야 할 주장

권장:

> Matching the maximum target-query budget substantially strengthened all three iterative
> baselines on Qwen, whereas gains on GPT-4o were small and non-monotonic. This indicates that
> additional interaction budget is target- and strategy-dependent rather than a universally
> sufficient explanation for performance differences.

피해야 함:

- “16턴이면 모든 baseline이 개선된다.”
- “OURS와 외부 baseline의 응답 선택 단위가 완전히 동일하다.”
- GPT-4o judge와 GPT-4o-mini judge 수치를 한 열에서 직접 증감 비교한다.
