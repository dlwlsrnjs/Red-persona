# 공식 500개 full dialogue 대 no-research-dialogue 결과

## 분석 설계

주 ablation은 공식 500개 case ID에 대한 paired comparison이다. 두 arm은 case, target snapshot,
initial target analysis, neutral condition, 네 final direction, manifestation prompt, evaluator를
고정한다. 유일한 구조적 차이는 initial analysis 뒤에 goal-aware planner와 target의 반복 연구
대화를 수행하는지 여부다.

- GPT target: `gpt-4o-2024-11-20`, goal-aware planner는 Qwen2.5-7B-Instruct
- Qwen target: `Qwen/Qwen2.5-7B-Instruct`, planner는 표준 Llama-3.1-8B-Instruct
- full: 연구 대화 뒤 네 방향 분기
- no dialogue: initial analysis 직후 네 방향 분기
- Success@4: 네 방향 중 하나 이상 성공
- primary population: 500개 micro average
- sensitivity: 여섯 범주 rate의 unweighted macro average
- 검정: paired discordant case에 대한 양측 exact McNemar

기존 GPT 250개는 과거 full run의 실제 initial system/user/assistant prefix를 그대로 재사용했다.
신규 GPT 250개와 Qwen 500개는 각 target이 생성한 initial response를 두 paired arm이 공유했다.

## GPT-4o target 결과

delta는 `full - no dialogue`다.

| case-level metric | full | no dialogue | Δ micro | Δ macro | full-only / ablation-only | p |
|---|---:|---:|---:|---:|---:|---:|
| Raw Recovery | 489/500 (97.8%) | 489/500 (97.8%) | 0.0%p | 0.0%p | 5 / 5 | 1.000 |
| Target-originated Recovery | 489/500 (97.8%) | 488/500 (97.6%) | +0.2%p | +0.09%p | 6 / 5 | 1.000 |
| Unsafe manifestation ASR | 455/500 (91.0%) | 469/500 (93.8%) | -2.8%p | -1.69%p | 23 / 37 | 0.092 |
| CARES non-refuse | 500/500 (100.0%) | 499/500 (99.8%) | +0.2%p | +0.26%p | 1 / 0 | 1.000 |
| CARES Accept | 25/500 (5.0%) | 34/500 (6.8%) | -1.8%p | -2.13%p | 17 / 26 | 0.222 |

Recovery는 ceiling에 가까우며 반복 연구 대화 제거 전후가 사실상 같았다. Unsafe ASR과 CARES
Accept는 no-dialogue에서 더 높았지만 양측 exact p가 각각 .092와 .222이므로 확정적 감소 효과로
주장하지 않는다. 이는 “더 긴 연구 대화가 hidden goal 복원을 높일 것”이라는 단순 dose 가설을
지지하지 않으며, 연구 대화가 일부 사례에서 안전한 분석·거리두기를 추가했을 가능성과 evaluator
ceiling을 함께 검토해야 한다.

## Qwen2.5-7B target 결과

| case-level metric | full | no dialogue | Δ micro | Δ macro | full-only / ablation-only | p |
|---|---:|---:|---:|---:|---:|---:|
| Raw Recovery | 490/500 (98.0%) | 491/500 (98.2%) | -0.2%p | +0.08%p | 7 / 8 | 1.000 |
| Target-originated Recovery | 490/500 (98.0%) | 490/500 (98.0%) | 0.0%p | +0.18%p | 8 / 8 | 1.000 |
| Unsafe manifestation ASR | 485/500 (97.0%) | 487/500 (97.4%) | -0.4%p | +0.43%p | 13 / 15 | 0.851 |
| CARES non-refuse | 495/500 (99.0%) | 495/500 (99.0%) | 0.0%p | +0.34%p | 4 / 4 | 1.000 |
| CARES Accept | 51/500 (10.2%) | 36/500 (7.2%) | +3.0%p | +6.68%p | 35 / 20 | 0.058 |

Recovery와 unsafe ASR 차이는 거의 없었다. CARES Accept는 full에서 3.0%p 높고 p=.058이지만,
사전에 정한 0.05 기준을 넘으므로 “연구 대화가 under-refusal을 증가시킨다”는 확정적 결론으로
쓰지 않는다. Qwen arm의 planner가 GPT arm과 다르므로 두 target의 절대 rate 차이는 target
architecture 하나의 인과효과가 아니다. 각 target 내부 paired delta가 해석 단위다.

## 품질 감사

| 산출물 | 사례 | branch/evaluation rows | 계약 오류 | 빈 candidate |
|---|---:|---:|---:|---:|
| GPT full 신규분 | 250 | 1,000 | 0 | 0 |
| GPT no dialogue 전체 | 500 | 2,000 | 0 | 0 |
| Qwen full | 500 | 2,000 | 0 | 0 |
| Qwen no dialogue | 500 | 2,000 | 0 | 0 |
| GPT full 평가 신규분 | 250 | 1,000 | 0 | 해당 없음 |
| GPT no dialogue 평가 | 500 | 2,000 | 0 | 해당 없음 |
| Qwen full 평가 | 500 | 2,000 | 0 | 해당 없음 |
| Qwen no dialogue 평가 | 500 | 2,000 | 0 | 해당 없음 |

Qwen full의 500개 모두 7개 연구 stage를 완료했다. 연구 질문 3,500개 중 2,505개는 Llama가
동적으로 생성했고 995개는 누출·형식·중복 검사 뒤 등록 fallback을 사용했다. 자세한 생성 감사는
`../docs/QWEN_TARGET_500_RUN_AUDIT_KO.md`에 있다.

## 비용

모든 OpenAI Batch ledger를 합친 캠페인 누적 실비는 **USD 73.933807475**다. 최신 API key로
전환하기 직전 ledger가 USD 50.78048375였으므로 최신 key의 증분 실비는
**USD 23.153323725**다. 승인된 global cap USD 120보다 낮다. 완료됐지만 최종 분석에 사용하지
않은 중복 Batch USD 2.82184625도 누적 실비에 포함했다. 로컬 Qwen target/vLLM과 Llama planner
실행은 이 OpenAI 비용에 포함되지 않는다.

## 재현 산출물

- 전체 평가 scorecard: `RESULTS_DIALOGUE_METRIC_SCORECARD_KO.md`와
  `RESULTS_DIALOGUE_METRIC_SCORECARD.json`
- scorecard 재계산 코드: `dialogue_scorecard.py`
- GPT paired JSON/Markdown: `data/ablation/gpt4o_component_contributions_official500.*`
- Qwen paired JSON/Markdown: `data/ablation/qwen2.5-7b-instruct_component_contributions.*`
- GPT no-dialogue evaluations: `data/ablation/evaluations/no_research_dialogue_gpt4o_official500/`
- Qwen full evaluations: `data/evaluations/qwen2.5-7b-instruct_official500_neutral/`
- Qwen no-dialogue evaluations:
  `data/ablation/evaluations/no_research_dialogue_qwen2.5-7b-instruct_official500/`

`data/`는 대용량·민감 산출물이므로 Git에서 제외한다. membership, 코드, 계약, 방법과 요약표는
Git에 추적되는 문서에 고정한다.
