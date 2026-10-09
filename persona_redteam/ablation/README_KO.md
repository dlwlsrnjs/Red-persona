# RED-Persona component ablation

이 폴더는 본 실험 코드를 바꾸지 않고 구성 요소별 기여도를 같은 사례 ID에 대한 paired
comparison으로 측정한다. 제거된 구성 요소가 full method의 성공률을 얼마나 높였는지는
`full rate - ablated rate`로 정의한다. 양수면 full method에서 해당 요소가 지표를 높였고,
음수면 제거 조건이 오히려 더 높았다는 뜻이다. 인과적 기여로 해석하려면 같은 모델 revision,
평가 프롬프트, 사례, 네 방향, 조건을 유지해야 한다.

## 1. 두 종류의 ablation

### 새 API 호출 없이 가능한 방향 기여도

`direction_attribution.py`는 이미 평가된 네 방향 결과만 사용한다. 다음을 동시에 보고한다.

- 각 방향 단독 성공률
- 해당 방향만 성공한 unique contribution
- 그 방향을 뺀 Success@3와 full Success@4의 차이
- 한 사례에서 여러 방향이 성공했을 때 `1 / 성공 방향 수`로 나누는 OR-game Shapley credit
- 15개 비어 있지 않은 방향 부분집합의 성공률

Success@4는 방향 간 중복이 있으므로 단독 성공률을 더하면 기여도가 과대 계산된다. Shapley
credit의 네 방향 합은 full Success@4와 정확히 같아야 한다.

현재 유효 250개에 대한 무호출 산출 결과는 `RESULTS_DIRECTION_EXISTING250_KO.md`에 요약했다.

```bash
python -m ablation.direction_attribution \
  --evaluation-dir data/evaluations/gpt-4o-2024-11-20_standard4_to250 \
  --evaluation-dir data/evaluations/gpt-4o-2024-11-20_parallel24 \
  --evaluation-dir data/evaluations/gpt-4o-2024-11-20_parallel \
  --selection-manifest data/campaigns/batch_after250_to500_v2/selection.json \
  --selection-key existing_case_ids \
  --output-json data/ablation/direction_attribution.json \
  --output-md data/ablation/direction_attribution.md
```

### 새 target/evaluator 호출이 필요한 구성 요소 제거

`specs.py`가 허용된 변형의 단일 registry다. 임의의 프롬프트 문자열을 CLI에서 주입하지 않기
때문에 이름이 같은 실험은 같은 제거 정책을 사용한다.

| variant | 제거 또는 조절 요소 | 해석 |
|---|---|---|
| `full` | 없음 | paired reference |
| `no_metaphor` | recurring metaphor | 은유 표현의 추가 기여 |
| `no_prior_dialogue` | 전체 prior dialogue | 최종 persona 외 대화 궤적의 기여 |
| `no_accumulated_states` | turn별 누적 state | 중간 state 표기의 추가 기여 |
| `persona_only` | metaphor, dialogue, 중간 state | 최종 persona 단독 성능 |
| `dialogue_only` | 최종 persona, metaphor, 중간 state | 원 대화 단독 성능 |
| `no_initial_evidence` | 모든 사례별 초기 증거 | context negative control |
| `no_research_dialogue` | 반복 Qwen 연구 대화 | initial analysis에서 바로 네 방향 분기 |
| `fixed_four_research_turns` | dynamic stopping | 정확히 4단계의 고정 dose |
| `fixed_seven_research_turns` | dynamic stopping | 정확히 7단계의 고정 dose |

`persona_only`와 `no_prior_dialogue`는 같은 실험이 아니다. 전자는 metaphor도 제거하고, 후자는
최종 persona와 metaphor를 유지한다. `dialogue_only`는 turn-level persona state까지 숨겨서
자연어 client/counselor 발화의 기여만 남긴다.

## 2. 공식 500개와 범주별 집계 원칙

유효 608개에서 suicidal ideation이 287개로 과대표집되어 있었기 때문에, 다른 다섯 범주의
유효 사례는 모두 유지하고 이 범주에서만 108개를 canonical order로 보류했다. 공식 500개의
분포는 `179 / 174 / 65 / 63 / 12 / 7`이다. 이는 equal allocation이 아니라 단일 과대표집
범주 downsampling이며, membership은 저장소 `data/red_persona_official_500.jsonl`에 고정된다.

그래서 모든 보고서에 두 estimand를 함께 둔다.

1. **micro**: 500개 사례 각각을 같은 가중치로 계산한다.
2. **macro_equal_category**: 먼저 범주별 rate를 구한 뒤 여섯 범주를 각각 1/6로 평균한다.

micro가 공식 500개 cohort에 대한 주 분석이다. macro는 희소 범주의 통계적 영향력을 같게 보는
민감도 분석이며 표본 수 자체를 늘리지는 않는다. 희소 범주의 신뢰구간이 넓다는 점을 숨기면
안 된다. 중복 oversampling은 독립 표본 수를 늘리지 않으므로 사용하지 않는다.

## 3. 실행

Git에 추적되는 공식 index가 기존 250개와 신규 250개를 합친 membership의 단일 기준이다.
로컬 selection checkpoint를 함께 주면 두 목록이 완전히 같은지도 검사한다. 먼저 적은 수로
실행 계약을 확인한 뒤 paired subset을 늘린다.

```bash
python -m ablation.run \
  --cases data/prepared/generated/jmir_eval_full_with_history.json \
  --official-index ../data/red_persona_official_500.jsonl \
  --selection-manifest data/campaigns/batch_after250_to500_v2/selection.json \
  --output-root data/ablation/runs \
  --variant full \
  --variant no_prior_dialogue \
  --variant no_research_dialogue \
  --target-model gpt-4o-2024-11-20 \
  --target-workers 256 \
  --max-cases 10
```

각 variant는 별도 디렉터리와 사례별 checkpoint를 사용한다. 한 변형의 실패나 resume이 다른
변형 결과를 덮어쓰지 않는다. smoke test가 통과한 뒤 `--max-cases`를 제거한다.

```bash
python -m ablation.evaluate \
  --input-dir data/ablation/runs/full \
  --output-dir data/ablation/evaluations/full \
  --workers 256

python -m ablation.evaluate \
  --input-dir data/ablation/runs/no_prior_dialogue \
  --output-dir data/ablation/evaluations/no_prior_dialogue \
  --workers 256
```

마지막으로 공통 case ID만 사용해 paired delta와 exact McNemar 검정을 만든다.

```bash
python -m ablation.aggregate \
  --evaluation full=data/ablation/evaluations/full \
  --evaluation no_prior_dialogue=data/ablation/evaluations/no_prior_dialogue \
  --baseline full \
  --output-json data/ablation/component_contributions.json \
  --output-md data/ablation/component_contributions.md
```

## 4. 해석 제한

- 한 번에 하나를 제거한 OFAT 비교가 기본이다. 여러 요소를 동시에 제거하는 `persona_only`,
  `dialogue_only`, `no_initial_evidence`는 묶음 효과이며 개별 효과의 합으로 보면 안 된다.
- context를 제거하면 이후 target 응답과 Qwen 질문도 함께 바뀐다. 따라서 delta는 텍스트 조각의
  고립된 직접 효과가 아니라 그 조각이 이후 상호작용에 미친 총효과다.
- `fixed_four`와 `fixed_seven`은 dynamic stop 대비 research dose 민감도다. 두 값의 차이만으로
  개별 stage의 인과 기여를 주장할 수 없다.
- 모든 변형은 같은 네 final direction을 유지한다. 방향 수를 바꿔 Success@k를 비교하지 않는다.
- `target_originated`는 oracle condition에서 정의상 제한된다. condition별 결과를 합쳐 하나의
  값으로 만들지 않는다.
- 여러 metric/variant/category를 동시에 검정할 때는 사전에 primary contrast를 정하고 다중비교
  보정을 별도로 적용한다.
