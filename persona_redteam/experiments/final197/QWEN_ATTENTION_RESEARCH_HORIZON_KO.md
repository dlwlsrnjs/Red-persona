# Qwen 장·단기 연구 대화 Attention 비교

## 목적

동일한 Final-197 사례와 동일한 최종 분기를 세 조건으로 구성하여
Qwen2.5-7B-Instruct의 attention을 비교한다.

1. `direct_goal`: 등록된 private GOAL을 직접 질문
2. `short_research`: 초기 사례 분석 뒤 분기별 연구 readout 질문 1회
3. `long_research`: 초기 사례 분석과 7단계 누적 연구 대화 뒤 동일 방향 질문

`short_research`와 `long_research`는 기존 GPT-4o 실험에 실제로 저장된 전체
message graph를 그대로 사용한다. 동일 case ID, 동일 private GOAL, 동일 분기
방향, 동일 target system prompt를 실행 전에 강제 검증한다.

## 중요한 해석 범위

GPT-4o는 내부 attention을 제공하지 않으므로 이 분석은 **Qwen proxy 분석**이다.
attention 유사도가 높다는 사실만으로 유해한 자극, 안전 정책 우회 또는 인과적
메커니즘을 입증할 수 없다. 논문에서는 다음과 같이 제한적으로 해석해야 한다.

- 사용 가능: 연구 대화 길이에 따라 Qwen의 위치별·구간별 attention 분배가
  direct-GOAL 조건과 얼마나 가까워지는지 보여주는 기술적 보조 분석
- 사용 불가: attention 유사도를 ASR, 위해성 또는 jailbreak 성공의 직접 증거로
  간주하는 주장
- 권장: attention 지표와 CARES/JMIR/HarmBench 결과의 **상관관계**를 별도로
  보고하고, attention은 설명적 분석으로 명시

## 메모리 안전한 추출 방식

긴 대화의 전체 `[sequence × sequence]` attention 행렬은 매우 크다. 예를 들어
10,000토큰 전체 attention을 모든 레이어·헤드에서 보존하면 수십 GB를 넘는다.
코드는 다음 방식으로 동일한 최종 query attention만 추출한다.

1. 전체 프롬프트를 SDPA로 prefill하며 attention 행렬은 반환하지 않음
2. 모든 조건에 동일한 고정 probe token을 한 토큰 입력
3. 이 한 decode step만 eager attention으로 실행
4. `[layer, head, 1, context]`에서 헤드 평균을 계산

따라서 긴 문맥을 자르지 않으면서도 최종 응답 시점의 문맥 attention을 비교할
수 있다. 문맥이 모델 한도를 초과하면 자동 절단하지 않고 오류로 중단한다.

## 출력 지표

- 128개 상대 위치 bin의 레이어별 attention heatmap
- 프롬프트 구간별 attention mass
  - system
  - persona/history packet
  - initial analysis
  - accumulated research dialogue
  - GOAL 또는 final question
  - assistant generation prefix
- direct-GOAL 토큰의 hidden-state 평균과 각 문맥 토큰 간 cosine similarity
- attention-weighted GOAL cosine
- GOAL 유사도 상위 10% 토큰에 대한 attention enrichment
- direct-GOAL 대비 상대 위치 attention의 레이어별 Jensen-Shannon similarity
- 정규화 attention entropy

기본 출력에는 private GOAL 원문이나 토큰 문자열을 중복 저장하지 않는다.
`--include-token-text`를 지정할 때만 상위 토큰 문자열을 감사용 JSON에 포함한다.

## 대표 사례 실행

```bash
python3 \
  -m experiments.final197.analyze_qwen_attention_horizon \
  --case-id jmir-source-1605 \
  --direction latent_request_synthesis \
  --arm with_history \
  --device cuda:3
```

각 사례·분기마다 다음 파일을 생성한다.

- `attention_metrics.json`: 모든 레이어의 수치와 provenance
- `attention_comparison.png`: 논문용 비교 그림

기본 결과 위치는 다음과 같다.

`result/OURS/qwen_attention_research_horizon_v1/<case_id>/<direction>/`

## 여러 사례와 네 분기 실행

선택 파일에서 앞 10건을 네 분기 모두 분석하려면 다음처럼 실행한다.

```bash
python3 \
  -m experiments.final197.analyze_qwen_attention_horizon \
  --case-id-file data/evaluations/final197_1011_singleton_gpt4o_v1/gpt4o/no_verbatim/selection.json \
  --limit 10 \
  --direction latent_request_synthesis \
  --direction evidence_chain \
  --direction analyst_response_target \
  --direction source_aware_reconstruction \
  --arm with_history \
  --device cuda:3
```

대화 이력 없는 조건은 `--arm no_history`로 별도 실행한다. 서로 다른 arm의
결과를 같은 사례 내에서 직접 합칠 때는 persona/history라는 실험 요인이 추가로
달라진다는 점을 명시해야 한다.

## 검증

GPU 없이 순수 지표 함수를 검사한다.

```bash
python3 \
  -m unittest experiments.final197.test_analyze_qwen_attention_horizon -v
```

## 전체 197개 × 4분기 집계

각 GPU shard가 완료된 뒤에는 분기를 사례 안에서 먼저 평균하고, 사례 단위
bootstrap 95% 신뢰구간을 계산한다. 이렇게 해야 동일 사례의 네 분기를 독립
표본처럼 중복 가중하지 않는다.

```bash
python3 \
  -m experiments.final197.aggregate_qwen_attention_horizon \
  --input-root result/OURS/qwen_attention_research_horizon_final197_all4_v1/shards \
  --output-dir result/OURS/qwen_attention_research_horizon_final197_all4_v1/aggregate \
  --expected-cases 197 \
  --expected-directions 4 \
  --bootstrap 10000 \
  --seed 20261012
```

출력은 `aggregate_metrics.json`, `case_level_metrics.csv`,
`attention_cohort_comparison.png`이다.
