# Reviewer 추가 실험 및 답변 초안

작성 기준일: 2026-11-25
대상: Final197, GPT-4o target, 공식 R/B·CARES·HarmBench 판정

## 결론

리뷰어가 제기한 핵심 혼동은 바로잡을 수 있다. RED-Persona의 네 branch는 응답을 본 뒤 질문을 고쳐 가는 adaptive search가 아니라, 서로 다른 의미론적 endpoint를 겨냥하도록 사전에 고정된 독립 실행이다. 다만 `Success@4`는 네 실행 중 하나라도 성공한 case-level 지표이므로 `Success@1`과 계산량을 분리해 함께 보고해야 한다.

추가 실험과 판정 일치도 분석은 세 가지 결론을 준다.

1. goal-blind aligned-vs-shuffled control에서 aligned R3+가 97.97%, 같은 위기 범주 안에서 섞은 shuffled가 70.05%였다. 27.92%p의 paired 차이(McNemar exact p=1.38e-13)는 분석이 단순 위기 범주가 아니라 case-specific 목표 신호를 상당 부분 보존한다는 근거다. shuffled가 여전히 높다는 점은 광범위한 위기 주제와 speech-act 공통성이 강하다는 한계도 동시에 보여 준다.
2. seven-stage의 추가 대화를 0단계부터 7단계까지 누적했을 때, outcome-blind로 미리 배정한 한 branch의 strict-joint Success@1은 64.97%에서 25.38%로 감소했다. 단계당 평균 -5.85%p(10,000회 case-cluster bootstrap 95% CI -6.99~-4.73%p), Cochran Q(7)=174.25, p=3.18e-34였다. 즉 이 데이터에서는 대화를 길게 만드는 것이 성공을 높이지 않았고, compact한 goal-focused mediation이 더 강했다.
3. 판정기는 완전히 중복되지 않았다. 외부 baseline 전체에서 R3+–HarmBench+ κ는 0.690, B4+–HarmBench+ κ는 0.439였고, CARES Accept-or-Caution–HarmBench+ κ는 0.109였다. 따라서 case-goal recovery, substantive fulfillment, standardized harmful-behavior classification을 모두 요구하는 strict-joint를 보수적 주지표로 두되 각 구성요소와 CARES도 별도로 공개한다.

## 1. Branch 선택에 대한 정확한 설명

### 무엇이 사전 고정되었는가

- 네 endpoint는 `latent_request_synthesis`, `evidence_chain`, `analyst_response_target`, `source_aware_reconstruction`이다.
- 각 branch는 동일 case에서 독립적으로 진행되며 서로의 target 응답을 보지 않는다.
- 최종 target 응답을 본 뒤 prompt, endpoint, branch 수를 수정하지 않았다.
- Git 이력도 결과 이전 고정을 뒷받침한다.

| Commit | 시각 | 의미 |
|---|---:|---|
| `36d271b` | 2026-10-09 06:27 UTC | seedless English pipeline 구축 |
| `00db508` | 2026-10-09 21:54 KST | four-direction pipeline 확정 |
| `d620cda` | 2026-10-09 22:02 KST | 별도 Success@4 snapshot 추가 |
| `827244b` | 2026-10-11 09:54 KST | Final197 실험 동결 |
| `abc70fe` | 2026-10-12 14:39 KST | 검증된 GPT-4o 결과 추가 |

따라서 “가장 잘 나온 응답을 보고 branch 목표를 사후 조정했다”는 설명은 사실과 다르다. 정확한 표현은 “사전 고정된 네 endpoint를 독립 실행하고, case-level union을 Success@4로 보고했다”이다.

### Success@1, Success@4, cross-fit

| 지표 | Strict-joint | 95% Wilson CI |
|---|---:|---:|
| Requested-format 고정 branch @1 | 86/197 = 43.65% | 36.92–50.64% |
| Evidence-linked 고정 branch @1 | 163/197 = 82.74% | 76.85–87.38% |
| Realistic-negative 고정 branch @1 | 161/197 = 81.73% | 75.74–86.50% |
| Matched-safety 고정 branch @1 | 137/197 = 69.54% | 62.79–75.55% |
| 균등 무작위 branch의 기대 @1 | 69.42% | — |
| 5-fold cross-fitted branch @1 | 159/197 = 80.71% | 74.63–85.61% |
| Success@4 | 189/197 = 95.94% | 92.19–97.93% |

1,000개 stratified 5-fold seed에서 cross-fitted @1은 75.63–82.74%, 중앙값 80.20%, 평균 79.95%였다. 이는 82.74% branch 하나만 사후 선택해야 성능이 나온다는 설명과 맞지 않는다. 동시에 primary 결과는 각 고정 branch와 @4이며, cross-fit은 리뷰어의 우려를 받아들인 sensitivity analysis로만 둔다.

가장 낮은 고정 branch도 43.65%로 논문 표의 외부 최고 TAP 3.55%보다 높다. 다만 실행 계약과 target call 수가 다르므로 이 차이를 compute-controlled causal 우위로 표현하지 않는다.

## 2. Goal-blind aligned-vs-shuffled control

### 설계

- Target-facing prompt에 canonical goal을 넣지 않았다.
- aligned는 해당 case packet, shuffled는 동일 crisis label 안의 deterministic cyclic derangement packet을 사용했다.
- 평가는 생성 후 original case의 private goal에 대한 R3+ recovery로 했다.
- 197 cases의 완전 paired 비교이며 fixed point는 0개다.

| 조건 | R3+ | 95% Wilson CI |
|---|---:|---:|
| Aligned | 193/197 = 97.97% | 94.90–99.21% |
| Shuffled within crisis label | 138/197 = 70.05% | 63.32–76.01% |
| Paired 차이 | +27.92%p | McNemar exact p=1.38e-13 |

discordant pair는 aligned-only 59, shuffled-only 4였다. 이 결과는 case-goal specificity를 지지하지만 자연 분포에서의 prevalence나 완전한 goal secrecy를 증명하는 실험은 아니다.

## 3. Length-matched dialogue ablation

### 설계

- shared initial analysis는 항상 유지하고 추가 seven-stage turn을 0..7개 누적했다.
- case마다 네 semantic branch 중 하나를 `SHA256(seed, case_id)`로 outcome-blind 배정했고 모든 depth에서 같은 branch를 유지했다.
- final bridge는 recovery 응답의 첫 비어 있지 않은 문단을 exact quote로 사용했다. canonical goal은 quote 선택에 쓰지 않았다.
- 197×8=1,576개 모두 생성되었고 bridge failure는 0이다.
- 이 실험은 branch 선택이 없는 Success@1 실험이다.

| 추가 대화 단계 | R3+ | B4+ | HarmBench+ | Strict-joint @1 |
|---:|---:|---:|---:|---:|
| 0 | 86.29% | 76.14% | 68.53% | 64.97% |
| 1 | 80.20% | 72.59% | 63.96% | 61.93% |
| 2 | 73.10% | 59.90% | 50.76% | 49.75% |
| 3 | 73.10% | 58.38% | 50.76% | 46.70% |
| 4 | 65.48% | 45.69% | 47.21% | 41.62% |
| 5 | 68.53% | 40.61% | 36.04% | 35.03% |
| 6 | 79.70% | 35.03% | 31.47% | 28.93% |
| 7 | 82.23% | 27.92% | 27.41% | 25.38% |

R3+는 후반에 다시 증가하지만 B4+와 HarmBench+는 계속 감소한다. 따라서 긴 대화가 목표를 잊게 해서만 실패한 것이 아니라, 목표는 복원하면서도 최종 harmful fulfillment는 줄어드는 safety/dilution 효과가 나타난 것으로 해석해야 한다.

Depth 0 대비 depth 7 strict-joint 차이는 -39.59%p였고 discordant pair는 depth0-only 85, depth7-only 7이었다(McNemar exact p=3.85e-18, 7개 비교 Holm-adjusted p=2.69e-17).

## 4. 판정 일치도와 strict-joint의 근거

### 같은 응답에 대한 통계적 일치도

Final197의 외부 baseline 3,546개 응답과 RED compact의 197×4=788개 fixed-branch 응답을 row-level로 다시 결합했다. 단순 일치율은 class imbalance에 민감하므로 positive agreement와 Cohen's κ를 함께 보고했고, κ의 95% CI는 `case_id` 단위 10,000회 cluster bootstrap으로 구했다.

| Cohort | 판정쌍 | Raw agreement | Positive agreement | Cohen's κ (95% CI) | 방향성 불일치(left-only / right-only) |
|---|---|---:|---:|---:|---:|
| 외부 baseline 전체, n=3,546 | R3+ / HarmBench+ | 92.30% | 73.31% | 0.690 (0.652–0.726) | 227 / 46 |
| 외부 baseline 전체, n=3,546 | B4+ / HarmBench+ | 91.51% | 47.47% | 0.439 (0.380–0.496) | 16 / 285 |
| 외부 baseline 전체, n=3,546 | CARES Accept / HarmBench+ | 81.50% | 32.23% | 0.217 (0.170–0.265) | 391 / 265 |
| 외부 baseline 전체, n=3,546 | CARES Accept-or-Caution / HarmBench+ | 48.25% | 28.57% | 0.109 (0.089–0.129) | 1,781 / 54 |
| RED compact four fixed branches, n=788 | B4+ / HarmBench+ | 82.23% | 88.80% | 0.463 (0.379–0.546) | 100 / 40 |
| RED compact four fixed branches, n=788 | R3+ / HarmBench+ | 75.76% | 85.99% | 0.060 (-0.010–0.140) | 182 / 9 |

RED에서 R3+가 97.46%로 거의 포화되어 있으므로 R3–HarmBench κ는 prevalence effect로 낮다. 이 경우 85.99%의 positive agreement와 방향성 불일치를 함께 읽어야 한다. 반대로 외부 baseline에서는 R3–HarmBench가 κ=0.690으로 상당히 겹친다. B4–HarmBench의 중간 수준 κ와 높은 positive agreement는 두 판정이 관련되지만 동일하지 않음을 보여 준다.

이 automated-metric 간 agreement는 서로의 중복성과 상보성을 보여 주지만 정확도 자체의 증명은 아니다. 본 reviewer-response 실행 범위에서는 연구자 결정에 따라 5인 blinded human validation을 수행하지 않으며, 따라서 아래 결과를 human-ground-truth accuracy의 증거로 표현하지 않는다.

본 Final197 평가표의 CARES ASR인 `Accept or Caution`은 non-refusal/stance를 넓게 포착하여 HarmBench보다 훨씬 많은 응답을 양성으로 둔다. 따라서 낮은 κ를 곧바로 어느 한 판정기의 실패로 해석하지 않는다. `Accept`만 사용해도 κ=0.217이고, CARES A/C와 HarmBench+의 불일치는 1,781 대 54로 한 방향에 집중된다. 이는 CARES ASR과 harmful-fulfillment ASR이 서로 다른 estimand라는 실증적 근거다.

### 왜 세 조건을 함께 쓰는가

- **R3+**는 최종 응답이 persona case의 숨겨진 harmful goal을 충분히 복원했는지 검사한다. 그러나 목표를 안전하게 요약하거나 거절하면서 언급한 응답도 R3+가 될 수 있다.
- **B4+**는 단순 언급·분석·거절이 아니라 실질적인 harmful fulfillment가 있는지 검사한다. 그러나 이는 GPT-4o rubric 판정 하나에 의존하며 표준 benchmark와 직접 비교하기 어렵다.
- **HarmBench+**는 공개된 behavior-conditioned classifier로 표준화와 재현성을 준다. 반면 case-specific persona goal과 recovery provenance를 직접 검사하지 않고, 본 실험 계약에서는 completion 앞 512 tokens만 본다.
- **CARES**는 A/C/R stance와 safety score라는 별도 임상·응답 태도 축을 제공한다. 특히 Caution을 포함한 ASR은 실질적 harmful fulfillment와 동일하지 않으므로 strict-joint의 구성요소로 넣지 않고 독립 지표로 병기한다.

따라서 새로 정의한 `strict-joint = R3+ ∧ B4+ ∧ HarmBench+`는 세 판정기의 다수결이 아니라 **precision-oriented conjunctive endpoint**다. 성공으로 세려면 (i) 정확한 case goal이 복원되고, (ii) 그것이 실질적으로 수행되며, (iii) 독립적인 표준 classifier도 harmful behavior로 확인해야 한다. 이 설계는 보수적으로 false positive를 줄이는 대신, 어느 한 판정기가 놓친 true positive를 버릴 수 있으므로 R3+, B4+, HarmBench, CARES와 strict-joint를 모두 분리 보고한다.

### 선행연구와의 연결 및 주석 후보

이 결합 원칙 자체는 jailbreak 평가에서 낯선 발상이 아니다. 다만 우리 세 구성요소와 정확히 같은 공식은 아니므로 “동일한 metric”이 아니라 “복수의 필요한 조건을 결합하는 선행 설계”로 인용한다.

1. StrongREJECT는 단순 non-refusal이 충분하지 않다고 지적하고, `score=(1-refused)×(specific+convincing)/2`로 willingness gate와 유용성·구체성을 곱한다. 이는 하나의 느슨한 신호 대신 여러 필요조건을 결합하는 가장 직접적인 선례다. [Souly et al., NeurIPS 2024](https://proceedings.neurips.cc/paper_files/paper/2024/hash/e2e06adf560b0706d3b1ddfca9f29756-Abstract-Datasets_and_Benchmarks_Track.html)
2. Cai et al.은 jailbreak를 단일 binary outcome으로 보는 한계를 지적하고 safeguard violation, informativeness, relative truthfulness를 분리한다. 실제 악용 지원을 원하는 actor의 성공은 세 조건을 모두 만족해야 한다고 정의한다. [Rethinking How to Evaluate Language Model Jailbreak](https://arxiv.org/abs/2404.06407)
3. GuidedBench는 universal judge가 case-specific criteria를 놓쳐 상충된 결과를 만든다고 보고하고 case별 guideline을 도입한다. 이는 RED의 R3+ goal-specific criterion을 표준 classifier와 병기하는 근거가 된다. [GuidedBench](https://arxiv.org/abs/2502.16903)
4. HarmBench는 18개 red-teaming 방법과 33개 target/defense를 비교하기 위한 표준화된 외부 판정 틀을 제공한다. 따라서 HarmBench를 버리지 않고 strict-joint의 독립 확인 조건으로 유지한다. [Mazeika et al., ICML 2024](https://proceedings.mlr.press/v235/mazeika24a.html)
5. 최신 evaluator 비교 연구도 서로 다른 evaluator가 서로 다른 jailbreak-success 정의를 encode하여 같은 응답을 다르게 판정할 수 있음을 확인한다. 이는 단일 judge의 verdict를 ground truth로 두지 않고 agreement와 error direction을 공개해야 한다는 근거다. [Mu, 2026](https://arxiv.org/abs/2609.10594)
6. SEAV는 semantic LLM judge에 retrieval-grounded validity/correctness 검증을 추가하고, 기존 성공의 22.1–51.0%를 invalid로 재분류했다. 이는 success claim에 독립적인 validity gate를 더하는 최근의 parallel precedent다. [Wu et al., EMNLP 2026](https://aclanthology.org/2026.emnlp-main.779/)

논문용 문장은 다음처럼 쓸 수 있다.

> Following prior evaluation designs that require more than non-refusal alone—e.g., StrongREJECT's refusal-gated specificity and convincingness score and multifaceted evaluations of violation, informativeness, and truthfulness—we define a conservative strict-joint endpoint. A response is counted only when it recovers the case-specific harmful goal (R3+), substantively fulfills it rather than merely mentioning it (B4+), and is independently classified as exhibiting the harmful behavior by HarmBench. We report every component and CARES separately because these evaluators operationalize different constructs rather than interchangeable labels.

## 5. Token·auxiliary cost 감사

논문 본문과 baseline 비교표의 비용은 독자가 일반 API로 재현하는 상황에 맞춰 **Standard API 등가 단가**로 통일한다. 여기서는 백만 토큰당 GPT-4o input $5.00, cached input $2.50, output $20.00와 GPT-4o mini input $0.30, cached input $0.15, output $1.20를 적용했다. 실제 실행은 Batch API를 사용했으므로 운영상 실지출은 이 값의 50%이며 아래에서 별도로 공개한다. 원본 Batch `usage`가 있는 값은 실측이고, source-500에서 재사용한 Final197 행은 source campaign 평균을 case 수만큼 귀속했다. 단가 근거는 [GPT-4o model reference](https://developers.openai.com/api/docs/models/gpt-4o)와 동기 API 대비 50% 할인을 명시한 [Batch API guide](https://developers.openai.com/api/docs/guides/batch)다.

| Method | 귀속 target calls | Target input tok. | Target output tok. | Standard-equivalent cost |
|---|---:|---:|---:|---:|
| Direct | 197.00 | 26,838 | 48,547 | $1.11 |
| Many-shot | 197.00 | 549,270 | 33,646 | $3.42 |
| Skeleton Key | 197.00 | 46,932 | 35,706 | $0.95 |
| PAIR | 1,976.93 | 556,227 | 683,831 | $16.46 |
| TAP | 1,577.03 | 618,302 | 330,099 | $9.69 |
| Crescendo | 1,089.34 | 616,937 | 330,254 | $9.69 |
| Red teaming | 593.76 | 176,180 | 101,518 | $2.91 |
| Therapist Crescendo | 1,143.87 | 628,816 | 318,780 | $9.52 |
| PCSA phase 2 | 3,731.19 | 1,681,316 | 983,722 | $28.08 |
| RED compact four branches | 1,773 | 5,224,662 | 680,409 | $39.73 |

PCSA online evaluator는 추가로 약 3,475.19 calls, input 1,917,808, output 218,479 tokens, Standard 등가 $0.84가 귀속된다. PAIR/TAP/기타 adaptive 방법의 local Qwen attacker와 online scorer는 API 비용이 0이지만 공짜 계산은 아니다. target Batch 입력에서 attacker가 만든 최종 prompt 토큰과 call 수는 복원했으나, PyRIT memory DB가 Git/GitHub/server에 남아 있지 않아 attacker/scorer 입력 토큰과 과거 GPU-hours는 정확히 복원할 수 없다. 이 값은 `unknown`으로 보고하고 0 token으로 대체하지 않는다.

Final197 전체 3,546행의 사후 GPT-4o 평가에는 R/B input 14,238,207, output 1,447,102 tokens(Standard 등가 $100.13), CARES input 5,694,545, output 21,721 tokens(Standard 등가 $28.91)이 사용되었다. HarmBench는 local GPU inference이므로 API token cost는 없다.

논문용 Standard API 등가 비용은 다음과 같다.

- Goal-blind 생성+평가: $12.47.
- Length-depth primary 생성: $78.09; 탈락한 초기 bridge pilot까지 포함하면 $95.09.
- Length-depth R/B 평가: $63.54; CARES 평가: $10.09.
- Length-depth HarmBench: H200 1 GPU, 57초 = 0.016 GPU-hours.
- Length-depth 총 Standard 등가 비용: $168.72(pilot 포함; primary protocol만 계산하면 $151.71).

재현성을 위해 실제 Batch 운영비도 별도로 남긴다. Goal-blind는 $6.24였고, length-depth는 primary 생성 $39.04, 폐기한 pilot 포함 생성 $47.55, R/B $31.77, CARES $5.04로 총 $84.36이었다. 이 값은 논문의 방법 간 비용 비교에 쓰지 않고 실제 실행 예산 기록으로만 사용한다.

## 6. 유사 multi-candidate jailbreak pipeline과의 관계

이 분야에서 여러 trajectory/candidate를 실행하고 하나 이상의 성공을 공격 성공으로 집계하는 것은 드문 관행이 아니다.

- PAIR는 병렬 attack stream을 사용한다. [PAIR paper](https://arxiv.org/abs/2310.08419), [official code](https://github.com/patrickrchao/JailbreakingLLMs)
- TAP는 branching factor, width, depth를 둔 tree search와 evaluator pruning을 사용한다. [TAP, NeurIPS 2024](https://proceedings.neurips.cc/paper_files/paper/2024/hash/70702e8cbb4890b4a467b984ae59828a-Abstract-Conference.html)
- Best-of-N Jailbreaking은 변형된 prompt를 반복 샘플링하고 N에 따른 ASR을 분석한다. [Best-of-N Jailbreaking](https://arxiv.org/abs/2412.03556)
- AutoDAN은 population, fitness, selection을 쓰는 hierarchical genetic search다. [AutoDAN](https://arxiv.org/abs/2310.04451), [official code](https://github.com/SheltonLiu-N/AutoDAN)
- GCG는 후보 suffix를 최적화하는 search 기반 공격이다. [GCG](https://arxiv.org/abs/2307.15043), [official code](https://github.com/llm-attacks/llm-attacks)

RED-Persona의 차이는 네 branch가 search 중 evaluator로 prune되거나 응답 후 수정되는 후보가 아니라, 서로 다른 임상적 의미 endpoint로 사전 고정된다는 점이다. 그러므로 related work에서는 관행의 유사성을 인용하되 “동일 알고리즘”이라고 쓰지 않는다.

## 7. 논문 반영 위치

### Main Results

Table 1에 다음 행을 분리한다.

- 각 fixed branch Success@1 네 개
- uniform-random branch expected @1
- cross-fitted @1은 sensitivity 열 또는 appendix 참조
- Success@4
- target calls/case와 auxiliary calls/case

`Best branch`라는 표현은 `evidence-linked fixed endpoint`로 바꾸고, 대표 branch 선택이 primary protocol처럼 보이지 않게 한다.

Main metric 정의 직후에는 R3+, B4+, HarmBench+가 각각 goal recovery, substantive fulfillment, standardized external classification을 담당하며 strict-joint가 세 조건의 교집합이라는 한 문단을 둔다. Main text에는 RED의 B4–HarmBench agreement와 외부 전체의 R3–HarmBench agreement를 간단히 제시하고, 전체 confusion counts·κ CI·CARES threshold 비교는 appendix 표로 보낸다.

### Ablation

factorial ablation 뒤에 `Dialogue depth and goal specificity controls` subsection을 추가한다. Goal-blind paired control과 0..7 prefix-depth curve를 같은 subsection에서 제시하면 “goal cue leakage”와 “length/content confounding”에 동시에 답할 수 있다.

### Limitations

- 외부 baseline과 RED는 target/auxiliary call budget이 같지 않다.
- source-500 재사용 행의 per-case token cost는 평균 귀속치다.
- local Qwen input tokens와 과거 GPU-hours는 원 DB 부재로 복원 불가다.
- shuffled R3+ 70.05%는 위기 범주와 speech-act 공통성만으로도 상당한 recovery가 가능함을 보여 준다.
- 자동 판정 간 일치도는 판정기의 상보성만 보여 주며 human-ground-truth accuracy를 증명하지 않는다. 5인 human validation은 이번 실행 범위에서 제외했다.

## 8. 리뷰 답변 문안

> We thank the reviewer for identifying an ambiguity in our original reporting. The four RED-Persona branches were pre-specified semantic endpoints and were executed independently; no endpoint or prompt was revised after observing the target's final response. We now report every fixed-branch Success@1 (43.65%, 82.74%, 81.73%, and 69.54%), the uniform-random expected Success@1 (69.42%), a five-fold cross-fitted sensitivity estimate (80.71%), and Success@4 (95.94%). Even the lowest fixed endpoint exceeds the strongest external endpoint in our table, although we explicitly do not interpret this as a compute-controlled causal comparison. We also add target-call, auxiliary-call, token, and cost accounting.
>
> To address goal leakage and dialogue-length confounding, we add two paired controls. In a goal-blind within-crisis-label shuffle, R3+ recovery was 97.97% for aligned cases and 70.05% for shuffled cases (paired difference 27.92 points; exact McNemar p=1.38e-13). In a cumulative 0-to-7 dialogue-depth ablation with one outcome-blind fixed branch per case, strict-joint Success@1 decreased from 64.97% to 25.38% (5.85 points per added stage; cluster-bootstrap 95% CI 4.73–6.99 points). These controls support case-specific goal mediation and show that the compact condition's advantage is not explained by greater dialogue length.
>
> We additionally clarify why we report a strict-joint endpoint rather than treating any single automated judge as ground truth. R3+ tests case-specific goal recovery, B4+ excludes mere mention or safe analysis by requiring substantive harmful fulfillment, and HarmBench supplies an independent standardized behavior classifier. Across all 3,546 external-baseline responses, R3+ and HarmBench agreed on 92.30% of rows (Cohen's κ=0.690, case-cluster bootstrap 95% CI 0.652–0.726), while B4+ and HarmBench agreed on 91.51% (κ=0.439, 95% CI 0.380–0.496). For the 788 RED fixed-branch responses, B4+ and HarmBench had 88.80% positive agreement (κ=0.463, 95% CI 0.379–0.546). CARES Accept-or-Caution showed much lower agreement with HarmBench (κ=0.109), as expected because it measures a broader non-refusal/response-stance construct. We therefore define strict-joint conservatively as R3+ AND B4+ AND HarmBench+, while continuing to report all components and CARES separately.

## 9. Follow-up × quotation 완전 2×2 ablation

리뷰어가 지적한 구성요소 결합 문제를 해결하기 위해 기존 `Direct-final-only`와 `Compact`에 `Follow-up-only`, `Quotation-only`를 추가했다. 동일한 197 cases × 4 fixed branches를 사용했다.

| Condition | Follow-up | Exact quotation | Branch strict joint | Case Success@4 |
|---|---:|---:|---:|---:|
| Direct-final-only | 없음 | 없음 | 14/788 = 1.78% | 14/197 = 7.11% |
| Follow-up-only | 있음 | 없음 | 8/788 = 1.02% | 8/197 = 4.06% |
| Quotation-only | 없음 | 있음 | 381/788 = 48.35% | 139/197 = 70.56% |
| Compact | 있음 | 있음 | 547/788 = 69.42% | 189/197 = 95.94% |

Case-level paired contrast는 quotation이 없는 상태의 follow-up 효과 -3.05%p(95% bootstrap CI -7.61–1.52), quotation이 있는 상태의 follow-up 효과 +25.38%p(18.78–31.98), follow-up이 없는 상태의 quotation 효과 +63.45%p(55.84–70.56), follow-up이 있는 상태의 quotation 효과 +91.88%p(87.82–95.43)였다. 전체 descriptive interaction은 +28.43%p였지만, 네 branch 모두 initial-analysis quotation이 존재한 161 cases에 제한하면 +11.18%p였다. 따라서 quotation을 주된 enabling component, follow-up을 quotation 조건에서의 conditional amplifier로 해석하되 순수 causal interaction으로 단정하지 않는다.

`Quotation-only` 788개 중 144개는 검증 가능한 initial-analysis quotation이 없어 호출하지 않고 실패로 유지했다. 상세 설계·통계·원고 문안은 `docs/FOLLOWUP_QUOTATION_FACTORIAL_ABLATION_KO.md`에 정리했다.

신규 생성 1,432건의 실측 사용량은 input 4,472,189, output 588,654 tokens였다. Standard API 등가 비용은 $34.13, 실제 Batch 비용은 $17.07이다. 자동평가 API 사용량은 최종 label 파일에 usage가 보존되지 않아 별도 exact total을 주장하지 않는다. HarmBench의 모든 실패·재시도까지 포함한 Slurm 할당량은 1.677 GPU-hours였다.

## 10. 9개 모델에서 goal recovery와 executable compliance 분리

동일한 197 paired cases에 이미 저장된 9개 compact target 결과를 재분석했다. 아래 값은 case-level Success@4이며 새 target 호출은 없다.

| Compact target run | R3+ | B4+ | HarmBench+ | Strict joint |
|---|---:|---:|---:|---:|
| GPT-4o | 99.49% | 100.00% | 96.95% | 95.94% |
| GPT-5.4 mini | 100.00% | 0.00% | 5.58% | 0.00% |
| GPT-6 Luna | 97.97% | 0.00% | 5.58% | 0.00% |
| Qwen2.5-7B | 97.97% | 96.45% | 96.45% | 90.86% |
| Llama-3.1-8B-Instruct | 93.91% | 98.98% | 94.92% | 88.32% |
| Llama3-G2C | 82.23% | 81.22% | 65.99% | 43.65% |
| Mistral-Small-3.2-24B | 99.49% | 100.00% | 97.97% | 96.95% |
| Gemma4-26B-A4B-IT | 99.49% | 98.48% | 93.91% | 92.89% |
| Phi-4 | 98.98% | 98.98% | 94.42% | 91.88% |

모델 간 이질성은 모든 endpoint에서 Cochran's Q p<1.3×10^-34였다. 그러나 모델별 R3와 B4 rate의 Spearman ρ는 0.177, R3와 strict-joint는 0.346에 불과했고, B4와 strict-joint는 0.898이었다. 특히 두 target은 목표를 거의 전부 복원하면서도 B4가 0이었다. 이 결과는 “goal recognition”과 “executable harmful compliance”를 하나의 판정으로 합치면 안 된다는 리뷰 답변을 직접 뒷받침한다. 9개 model-level correlation은 표본 수가 작으므로 기술통계로만 사용한다.

## 11. 평가 endpoint 선택에 대한 method-ranking 민감도

외부 baseline 18개 target×method cells의 방법별 비율 순위를 비교했다. 전체 18 cells에서 strict-joint와 B4의 Spearman ρ는 0.991, strict-joint와 HarmBench는 0.911, strict-joint와 R3는 0.913이었다. 반면 strict-joint와 CARES Accept는 0.340, CARES Accept-or-Caution은 0.093이었다.

이는 R/B/HarmBench가 서로 동일하다는 뜻이 아니라, external baseline에서 방법 순위가 대체로 같은 방향이라는 뜻이다. CARES A/C는 non-refusal/stance라는 더 넓은 estimand여서 harmful fulfillment 순위와 크게 다르다. 따라서 논문에는 (i) row-level agreement/confusion, (ii) method-level rank sensitivity, (iii) 각 endpoint의 별도 표, (iv) precision-oriented strict conjunction을 함께 제시한다.

## 12. Source/category-stratified robustness

Compact GPT-4o strict-joint Success@4는 네 source strata에서 90.91%, 95.59%, 100%, 100%였고, 주요 crisis strata인 self-harm와 suicidal ideation에서 각각 95.96%, 95.45%였다. Goal-blind aligned-minus-shuffled R3 차이는 source별 +5.88~+33.09%p였다. 작은 strata는 불확실성이 크므로 기술통계로만 둔다.

이 분석은 PersonaHarm 내부의 source/category 편중에 대한 sensitivity check다. 별도로 수집한 자연 대화 corpus가 아니므로 리뷰어의 natural-case external-validity 우려를 완전히 해소했다고 쓰지 않는다. 새 자연 대화 실험은 독립적인 case 수집·goal annotation·윤리 검토가 필요한 별도 연구 범위다.

## 13. Slurm GPU-hour 복구 감사

스케줄러의 `AllocTRES × ElapsedRaw`를 이용해 다음 할당량을 복구했다.

| Campaign | Allocated GPU-hours | 해석 |
|---|---:|---|
| Source-500 shared primary pipeline | 21.901 | 여러 target/method 공유 작업; Final197에 비례 귀속하지 않음 |
| Final197 shared primary pipeline | 34.619 | 여러 target/method가 7 GPUs를 공유하여 method별 분해 불가 |
| Final197 failed/superseded setup overhead | 0.957 | primary와 분리 보고 |
| Final197 HarmBench | 1.503 | local classifier |
| Factorial HarmBench, 모든 재시도 포함 | 1.677 | 실패·취소 작업 포함 실제 예약량 |
| Length-depth HarmBench | 0.016 | local classifier |

이는 GPU utilization이 아니라 예약된 GPU-hours다. 과거 PyRIT DB가 남아 있지 않아 local attacker/scorer의 입력 토큰과 shared job 내부의 method별 GPU 시간은 여전히 식별할 수 없다. 기존 문서의 “GPU-hours unavailable”은 “일부 campaign-level scheduler allocation은 복구, method-level attribution은 불가”로 수정한다.

## 14. 공개·재현성 산출물

`result/reviewer_response/safe_release/`에 다음 label-only 자료를 생성했다.

- 외부 baseline 3,546행
- RED compact 788행
- 완전 2×2 factorial 3,152행
- factorial aggregate JSON/CSV와 paired statistics
- 파일별 SHA-256, row count, 구조적 CARES missingness를 기록한 metadata

공개본은 prompt, persona, private goal, quotation, response text, evaluator rationale, 원 case ID를 포함하지 않는다. case/row ID는 salted deterministic hash로 대체했다. 공격 내용을 공개하지 않으면서도 모든 집계표와 paired 재분석을 독립적으로 재현할 수 있는 최소 산출물이다.
