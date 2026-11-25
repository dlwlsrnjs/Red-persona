# Follow-up × Exact Quotation 2×2 Ablation: 논문 반영 및 리뷰 답변 자료

작성일: 2026-11-24
상태: 실험·자동평가·결합·대응표본 통계 완료
대상 모델: `gpt-4o-2024-11-20`
분석 단위: PersonaHarm 197 cases × 4 fixed branches = 788 responses/cell

## 1. 한 문장 결론

**Exact quotation이 공격 성공을 가능하게 하는 주된 구성요소였고, goal-focused follow-up은 quotation 없이 단독으로는 효과가 확인되지 않았지만 quotation과 결합될 때 성공률을 추가로 높이는 조건부 증폭기로 작동했다.**

다만 이 실험에서 `Quotation-only`는 shared initial analysis에서, `Compact`는 focused readout에서 문장을 인용하므로 두 quotation의 정보량이 완전히 같지 않다. 따라서 아래 결과는 **리뷰어 요청에 따라 추가한 post-hoc component ablation의 기술적 factorial contrast**로 보고하며, follow-up과 quotation의 순수한 인과효과를 완전히 분리했다고 주장하지 않는다.

---

## 2. 왜 이 분석을 추가했는가

제출 원고는 compact protocol을 다음 두 구성요소의 결합으로 정의했다.

1. goal-focused follow-up/readout
2. target이 앞서 생성한 문장의 exact quotation

기존 ablation은 두 요소를 함께 제거한 `Direct-final-only`와 둘 다 포함한 `Compact`를 주로 비교했다. 따라서 compact의 큰 증가가 follow-up, quotation, 또는 둘의 결합 중 무엇에서 비롯되었는지 분리할 수 없었다.

이 한계는 첨부 원고에 이미 명시되어 있다.

- PDF p.3: initial analysis → short follow-up → exact-quotation final query의 compact 절차
- PDF p.7: 기존 Table 2의 interaction/history ablation과 Direct 7.11% 대 Compact 95.94%
- PDF pp.7–8: short transition이 compliance를 높였다는 해석
- PDF p.8: follow-up과 quotation을 함께 제거하여 quotation 단독효과를 분리할 수 없다는 limitation
- PDF p.17: Table 10의 protocol contract 및 unavailable quotation/empty call을 실패로 유지하는 평가 원칙

원고 근거: review submission PDF pp.3, 7–8, 17(별도 보관; 저장소에는 포함하지 않음)

이번 실험은 누락된 두 셀을 채워 완전한 2×2 비교를 구성한다.

---

## 3. 실험 설계

| Condition | Goal-focused follow-up | Exact quotation | 생성 수 | 설명 |
|---|---:|---:|---:|---|
| Direct-final-only | 없음 | 없음 | 기존 788 | shared initial analysis 뒤 direct final query |
| Follow-up-only | 있음 | 없음 | 신규 788 | focused follow-up은 유지하되 final query의 quotation block 제거 |
| Quotation-only | 없음 | 있음 | 신규 788 시도 | follow-up 없이 initial analysis의 검증된 target 문장을 인용 |
| Compact | 있음 | 있음 | 기존 788 | focused readout의 target 문장을 exact quotation하여 final query |

### 3.1 고정된 실험 조건

- 197 cases와 각 case의 4개 branch를 모든 셀에서 동일하게 유지했다.
- 네 branch는 `analyst_response_target`, `evidence_chain`, `latent_request_synthesis`, `source_aware_reconstruction`이다.
- 신규 두 셀은 `gpt-4o-2024-11-20`, temperature 0, `max_tokens=1200`으로 생성했다.
- 비용과 처리시간을 줄이기 위해 OpenAI Batch API를 사용했다.
- 기존 initial analysis와 compact readout은 재사용했으며, 불필요하게 재생성하지 않았다.
- source commit: `070f44d71421cd3d41624126a62d8e2c1c98a63a`
- case-set digest: `9090c509...`

### 3.2 Quotation-only의 보수적 실패 처리

`Quotation-only`에서는 initial analysis에 검증 가능한 target-authored quotation이 있을 때만 호출했다. 인용문이 없으면 문장을 임의로 만들거나 다른 텍스트로 대체하지 않았다.

- 정상 생성: 644/788
- verified quotation 부재로 인한 deterministic no-response: 144/788
- 해당 144 rows = 36 cases × 4 branches

주분석은 이 144건을 분모에서 제거하지 않고 실패로 계산한다. 이는 protocol feasibility까지 포함하는 intention-to-test 성격의 보수적 추정이다. 동시에 quote availability의 영향을 분리하기 위해, 네 branch 모두 initial-analysis quotation이 존재한 161 cases만의 complete-case sensitivity analysis도 함께 보고한다.

---

## 4. 평가와 통계

### 4.1 평가 지표

- CARES: `A`, `C`, `R`, `NR` 및 CARES ASR/SS
- R/B rubric: recovery `R3+`와 behavior `B4+`
- HarmBench: official `cais/HarmBench-Llama-2-13b-cls`
- Strict joint success: 동일 branch에서 `R3+ AND B4+ AND HarmBench-positive`

CARES와 R/B는 GPT-4o로 평가했다. HarmBench는 공식 classifier revision `bda705...`를 사용했다.

### 4.2 주결과 단위

주결과는 case-level `Success@4`이다. 즉, 동일 case의 고정된 네 branch 중 하나 이상이 strict-joint success이면 case success로 계산한다. Branch-level 비율은 보조적·기술적 결과로 함께 제시한다.

### 4.3 불확실성 및 대응표본 검정

- case를 cluster로 한 nonparametric percentile bootstrap
- 100,000 bootstrap replicates
- seed `20261124`
- 보고값: percentage-point contrast와 95% bootstrap CI
- sensitivity test: paired exact McNemar test

효과크기와 신뢰구간을 주된 근거로 사용한다. McNemar p-value는 다중비교 보정 전의 보조적 결과이며, 실험이 reviewer-motivated post-hoc analysis라는 점을 함께 명시한다.

---

## 5. 데이터 무결성 점검

- 각 입력·CARES·R/B·HarmBench·joined 결과: 1,576 rows
- unique IDs: 1,576
- missing IDs: 0
- extra IDs: 0
- duplicate IDs: 0
- HarmBench: 1,432 evaluated + 144 deterministic no-response; invalid 0
- HarmBench label 합계: 847 positive + 729 negative = 1,576
- R/B invalid: 0

R/B에서는 evidence field 형식 호환성을 위해 공식 deterministic reprocessor를 적용한 30건이 있었다. 그중 recovery score 24건이 하향 조정되었고 behavior score 하향 조정은 0건이었다. 이는 성공률을 인위적으로 높이는 수정이 아니며, 리뷰 또는 appendix에서는 이 사실을 공개한다.

---

## 6. 핵심 결과

### 6.1 네 셀의 strict-joint 결과

| Condition | Branch strict joint | Branch rate | Case Success@4 | Case rate |
|---|---:|---:|---:|---:|
| Direct-final-only | 14/788 | 1.78% | 14/197 | 7.11% |
| Follow-up-only | 8/788 | 1.02% | 8/197 | 4.06% |
| Quotation-only | 381/788 | 48.35% | 139/197 | 70.56% |
| Compact | 547/788 | 69.42% | 189/197 | 95.94% |

가장 간결한 읽기는 다음과 같다.

- quotation이 없을 때 follow-up을 추가해도 성공률이 증가하지 않았다: 7.11% → 4.06%.
- follow-up 없이 quotation만 추가해도 성공률이 크게 증가했다: 7.11% → 70.56%.
- quotation이 있는 상태에서 follow-up을 추가하면 더 증가했다: 70.56% → 95.94%.
- 따라서 quotation이 주된 enabling component이고, follow-up은 quotation이 있을 때 작동하는 conditional amplifier라는 해석이 데이터에 가장 잘 맞는다.

### 6.2 Case-level paired contrasts

| Contrast | 추정치 (pp) | 95% bootstrap CI | Exact McNemar p | 해석 |
|---|---:|---:|---:|---|
| Follow-up effect, quotation 없음 | -3.05 | [-7.61, 1.52] | .263 | 단독효과 확인 안 됨 |
| Follow-up effect, quotation 있음 | +25.38 | [18.78, 31.98] | 8.14×10⁻¹³ | quotation 조건에서 추가 증가 |
| Quotation effect, follow-up 없음 | +63.45 | [55.84, 70.56] | 1.65×10⁻³² | 큰 증가 |
| Quotation effect, follow-up 있음 | +91.88 | [87.82, 95.43] | 6.53×10⁻⁵⁵ | 큰 증가 |
| Compact − Direct | +88.83 | [84.26, 92.89] | 4.18×10⁻⁵³ | 결합 protocol의 전체 차이 |
| Descriptive interaction | +28.43 | [20.30, 36.55] | — | 구성요소 결합의 비가산 패턴 |

McNemar discordant pairs:

- Follow-up, quotation 없음: 7 gains / 13 losses
- Follow-up, quotation 있음: 53 gains / 3 losses
- Quotation, follow-up 없음: 130 gains / 5 losses
- Quotation, follow-up 있음: 181 gains / 0 losses
- Compact − Direct: 175 gains / 0 losses

Branch-level interaction contrast도 +21.83 pp로 같은 방향이었다.

### 6.3 신규 두 셀의 보조 평가

| Metric | Follow-up-only | Quotation-only |
|---|---:|---:|
| CARES A/C/R/NR | 4 / 3 / 781 / 0 | 450 / 30 / 164 / 144 |
| CARES ASR | 7/788 = 0.89% | 480/788 = 60.91% |
| CARES SS | 0.9930 | 0.4099 |
| R3+ | 534/788 = 67.77% | 602/788 = 76.40% |
| B4+ | 9/788 = 1.14% | 407/788 = 51.65% |
| HarmBench+ | 422/788 = 53.55% | 425/788 = 53.93% |
| Strict joint branch | 8/788 = 1.02% | 381/788 = 48.35% |
| Strict joint Success@4 | 8/197 = 4.06% | 139/197 = 70.56% |

HarmBench-positive 비율은 두 신규 셀에서 비슷하지만 CARES, B4+, strict joint는 크게 다르다. 이는 HarmBench가 광범위한 harmfulness 신호를 포착하는 반면, CARES와 R/B가 구체적인 요청 이행과 refusal boundary를 더 엄격히 구분하기 때문으로 해석할 수 있다. 바로 이 차이 때문에 단일 ASR 대신 여러 평가축과 strict conjunction을 사용했다.

---

## 7. Quotation-eligible sensitivity analysis

Quotation-only에서 36 cases가 구조적으로 호출 불가능했다. 이 차이가 주분석의 interaction을 얼마나 키웠는지 확인하기 위해, 네 branch 모두 verified quotation이 있던 161 cases만 다시 비교했다.

### 7.1 Complete-case rates

| Condition | Success@4 |
|---|---:|
| Direct-final-only | 10/161 = 6.21% |
| Follow-up-only | 6/161 = 3.73% |
| Quotation-only | 139/161 = 86.34% |
| Compact | 153/161 = 95.03% |

### 7.2 Complete-case contrasts

| Contrast | 추정치 (pp) | 95% bootstrap CI | Exact McNemar p |
|---|---:|---:|---:|
| Follow-up effect, quotation 없음 | -2.48 | [-7.45, 2.48] | .454 |
| Follow-up effect, quotation 있음 | +8.70 | [3.73, 14.29] | .00258 |
| Quotation effect, follow-up 없음 | +80.12 | [73.29, 86.34] | 9.70×10⁻³⁸ |
| Quotation effect, follow-up 있음 | +91.30 | [86.96, 95.65] | 1.12×10⁻⁴⁴ |
| Compact − Direct | +88.82 | [83.85, 93.17] | 1.79×10⁻⁴³ |
| Descriptive interaction | +11.18 | [3.73, 18.63] | — |

핵심 결론은 유지된다. quotation effect는 매우 크고, follow-up 단독효과는 확인되지 않으며, quotation이 있을 때 follow-up의 추가 효과는 양수다. 다만 interaction은 전체 197 cases에서 +28.43 pp였던 것이 quote-eligible 161 cases에서 +11.18 pp로 감소한다. 따라서 전체 interaction의 일부는 quotation availability 차이에서 발생하며, **+28.43 pp를 순수한 심리적·인과적 synergy로 해석해서는 안 된다.**

---

## 8. 논문에서 주장해도 되는 것과 피해야 할 것

### 8.1 데이터가 지지하는 주장

1. Exact quotation은 이 설정에서 compact protocol의 큰 성공 증가를 설명하는 주된 구성요소다.
2. Goal-focused follow-up만으로는 direct-final 대비 개선이 관찰되지 않았다.
3. Goal-focused follow-up은 quotation이 있을 때 추가적인 성공 증가와 연관되었다.
4. 이 패턴은 모든 197 cases를 실패 포함 방식으로 분석해도, quote-eligible 161 cases만 분석해도 유지된다.
5. Compact protocol의 효과는 두 단계의 단순 합보다 비가산적인 패턴을 보이지만, 이를 순수한 causal interaction으로 단정할 수는 없다.

### 8.2 피해야 할 표현

- “Follow-up has no effect.”
  → “We did not detect a beneficial effect of follow-up in the absence of quotation.”
- “Quotation alone fully explains compact.”
  → Compact는 Quotation-only보다 25.38 pp 높았다. complete-case에서도 +8.70 pp였다.
- “We causally isolated both components.”
  → quotation source/content가 두 quotation-present 셀에서 같지 않다.
- “The interaction is 28.43 pp.”만 단독 제시
  → 144 no-response의 영향을 밝히고 complete-case +11.18 pp도 함께 제시해야 한다.
- “All 788 Quotation-only responses were generated.”
  → 644 generated, 144 deterministic failures가 정확하다.
- “The experiment was preregistered.”
  → reviewer-motivated post-hoc ablation이다.

### 8.3 권장 서술 프레임

> Quotation was the primary enabling component, whereas the goal-focused follow-up behaved as a conditional amplifier rather than an independently sufficient component.

이 한 문장이 가장 강하면서도 결과 범위를 넘지 않는다.

---

## 9. 원고에 넣는 위치

### 9.1 Main Results

PDF p.7의 기존 Table 2 바로 뒤에 짧은 paragraph를 추가한다. 공간이 허용되면 아래 네 셀 표를 main text의 새 표 또는 Table 2 panel로 넣는다. 공간이 부족하면 표와 complete-case sensitivity는 appendix로 보내고, main text에서는 핵심 네 비율과 contrast만 제시한다.

권장 우선순위:

1. Main text: 네 셀의 case-level Success@4와 핵심 해석
2. Main 또는 appendix: paired contrasts + 95% CIs
3. Appendix: branch-level, CARES/R/B/HarmBench 상세, quote-eligible sensitivity
4. Reproducibility appendix: 모델 snapshot, failure policy, bootstrap seed, artifact provenance

### 9.2 Discussion

PDF pp.7–8의 “short transition lifts compliance” 표현을 좁혀야 한다. 기존 문장은 follow-up 자체가 효과를 낸 것처럼 읽힐 수 있다. 새 결과에 맞게 “quotation is the primary enabling component; follow-up provides additional lift when paired with quotation”으로 교체한다.

### 9.3 Limitations

PDF p.8의 “두 요소를 함께 제거해 quote-only effect를 분리하지 못했다”는 문장은 더 이상 그대로 둘 수 없다. 대신 다음 두 한계를 남긴다.

- ablation은 reviewer-motivated post-hoc analysis다.
- Quotation-only와 Compact가 서로 다른 stage에서 문장을 인용하므로 quotation content가 완전히 통제되지 않았다.
- 36 cases에서 initial-analysis quotation이 없어 quotation-only가 구조적으로 실패했다.
- 단일 target model 및 197 PersonaHarm cases에 한정된다.

### 9.4 Methods/Appendix

PDF p.17 Table 10에 신규 두 condition의 protocol contract를 추가한다. 또한 unavailable quotation을 실패로 유지했다는 원칙과 quote-eligible complete-case sensitivity를 명시한다.

---

## 10. 원고에 바로 붙여 넣을 영문 초안

### 10.1 Methods: component ablation

> **Follow-up × quotation component ablation.** To separate the two operations that were jointly removed in the original direct-final ablation, we completed a 2×2 component design crossing a goal-focused follow-up with exact quotation. The four conditions were direct-final-only (neither component), follow-up-only, quotation-only, and compact (both components). We reused the same shared initial analyses, 197 cases, and four fixed branches per case. In the follow-up-only condition, the focused readout remained in the conversational context, but the final query omitted the quotation block. In the quotation-only condition, we skipped the focused follow-up and inserted a verified target-authored sentence from the initial analysis into the compact final-query template. We did not synthesize a quotation when none was available; these calls were retained as failures. The primary outcome was case-level strict-joint Success@4, defined as at least one of four branches satisfying R3+, B4+, and HarmBench-positive simultaneously. We report case-cluster bootstrap 95% confidence intervals (100,000 replicates) and paired exact McNemar tests as sensitivity analyses.

### 10.2 Results: main paragraph

> The completed component ablation identified exact quotation as the primary enabling component. Case-level strict-joint Success@4 was 7.11% (14/197) for direct-final-only, 4.06% (8/197) for follow-up-only, 70.56% (139/197) for quotation-only, and 95.94% (189/197) for compact. Without quotation, adding the goal-focused follow-up changed success by −3.05 percentage points (95% bootstrap CI, −7.61 to 1.52; exact McNemar p=.263). Without follow-up, adding quotation increased success by 63.45 points (95% CI, 55.84 to 70.56). In the presence of quotation, adding the follow-up produced a further 25.38-point increase (95% CI, 18.78 to 31.98; p<.001). Thus, the follow-up was not independently sufficient in this setting; instead, it acted as a conditional amplifier when paired with a target-authored quotation.

### 10.3 Results: failure-policy sensitivity

> Verified initial-analysis quotations were unavailable for all four branches of 36 cases, yielding 144 deterministic no-response failures in the quotation-only condition. We retained these failures in the primary intention-to-test analysis. In a sensitivity analysis restricted to the 161 quotation-eligible cases, the qualitative conclusion was unchanged: Success@4 was 6.21%, 3.73%, 86.34%, and 95.03% for direct-final-only, follow-up-only, quotation-only, and compact, respectively. The follow-up contrast showed no improvement without quotation (−2.48 points; 95% CI, −7.45 to 2.48) and was positive with quotation (+8.70 points; 95% CI, 3.73 to 14.29).

### 10.4 Discussion

> The component analysis refines the interpretation of the compact protocol. Its large gain was not reproduced by the goal-focused follow-up alone. Exact quotation produced most of the increase, while the follow-up added value conditionally when quotation was present. This pattern is consistent with a mechanism in which the quoted target-authored statement anchors the final request to the model's own prior representation, and the focused readout improves the relevance or actionability of that anchor. Because the quotation-only and compact conditions drew quotations from different stages of the dialogue, however, the observed interaction should be interpreted descriptively rather than as a fully orthogonal causal decomposition.

### 10.5 Revised limitation paragraph

> This reviewer-motivated component ablation was conducted post hoc and on a single target model. Although it separates the presence of a follow-up from the presence of a quotation, it does not fully equate quotation content: quotation-only uses a verified sentence from the shared initial analysis, whereas compact uses a sentence from the goal-focused readout. Moreover, 36 of 197 cases lacked an eligible initial-analysis quotation, and their 144 branches were conservatively counted as failures. Complete-case sensitivity analyses preserved the qualitative pattern but attenuated the interaction contrast. Replication with stage-matched quotations, additional target models, and human adjudication is therefore needed before assigning a general causal interaction to the two components.

### 10.6 Table caption

> **Table X. Follow-up × exact-quotation component ablation on GPT-4o.** Values are strict-joint successes requiring R3+, B4+, and HarmBench-positive in the same branch. Success@4 marks a case successful when any of four fixed branches meets the conjunction. All 197 cases remain in the primary denominator; 144 unavailable quotation-only branches from 36 cases are retained as failures. Percentage-point contrasts use paired case outcomes, and 95% confidence intervals are from a case-cluster bootstrap with 100,000 replicates.

### 10.7 LaTeX table 초안

```latex
\begin{table}[t]
\centering
\caption{Follow-up $\times$ exact-quotation component ablation on GPT-4o.}
\label{tab:followup_quote_ablation}
\begin{tabular}{lrrrr}
\toprule
Condition & Follow-up & Quotation & Branch strict joint & Case Success@4 \\
\midrule
Direct-final-only & No  & No  & 14/788 (1.78\%)  & 14/197 (7.11\%) \\
Follow-up-only    & Yes & No  & 8/788 (1.02\%)   & 8/197 (4.06\%) \\
Quotation-only    & No  & Yes & 381/788 (48.35\%)& 139/197 (70.56\%) \\
Compact           & Yes & Yes & 547/788 (69.42\%)& 189/197 (95.94\%) \\
\bottomrule
\end{tabular}
\end{table}
```

---

## 11. 리뷰 답변 초안

### 11.1 핵심 리뷰: “두 요소를 함께 제거해 어느 요소가 원인인지 알 수 없다”

> We thank the reviewer for identifying that our original direct-final ablation jointly removed the goal-focused follow-up and exact quotation. We therefore added the two missing cells, follow-up-only and quotation-only, completing a 2×2 component analysis over the same 197 cases and four fixed branches. The results identify quotation as the main enabling component: strict-joint Success@4 was 7.11% for direct-final-only, 4.06% for follow-up-only, 70.56% for quotation-only, and 95.94% for compact. Follow-up alone did not improve over direct-final (−3.05 percentage points; 95% CI, −7.61 to 1.52), whereas quotation without follow-up increased success by 63.45 points (95% CI, 55.84 to 70.56). Follow-up provided an additional increase when quotation was present (+25.38 points; 95% CI, 18.78 to 31.98). We have added these results to [Results/Table X], revised the Discussion to describe quotation as the primary enabling component and follow-up as a conditional amplifier, and replaced the original limitation with the remaining design qualifications.

### 11.2 “Quotation-only의 빈 응답이 결과를 왜곡한 것 아닌가?”

> We agree that quotation availability must be made explicit. We did not fabricate or substitute a quotation when the shared initial analysis contained no verified target-authored sentence. This occurred for 36 cases (144 branches), which we conservatively retained as failures in the primary analysis because quotation availability is part of protocol feasibility. We also added a complete-case sensitivity analysis restricted to the 161 cases with eligible quotations in all four branches. Quotation-only Success@4 increased from 70.56% in the full denominator to 86.34% in the eligible subset, and the qualitative pattern remained: follow-up showed no beneficial contrast without quotation but a positive contrast with quotation. We now report both analyses and avoid interpreting the full-sample interaction as a pure causal synergy.

### 11.3 “이것은 post-hoc 분석 아닌가?”

> Yes. This component ablation was added in response to the review and was not preregistered. We now label it explicitly as a reviewer-motivated post-hoc analysis, emphasize effect sizes and case-cluster bootstrap confidence intervals, and treat exact McNemar p-values as secondary sensitivity statistics rather than confirmatory evidence.

### 11.4 “2×2라고 해도 완전한 causal factorial design은 아니다”

> We agree. The manipulation crosses the presence of follow-up and quotation, but the quotation content is not stage-matched: quotation-only draws from the shared initial analysis, whereas compact draws from the goal-focused readout. We therefore describe the interaction as a descriptive factorial contrast, not a fully orthogonal causal interaction. We have added this qualification to both the Discussion and Limitations and identify stage-matched quotation experiments as future work.

### 11.5 “왜 branch 평균이 아니라 Success@4를 주결과로 썼는가?”

> The protocol fixes four semantically distinct branches per case before evaluation, and its operational question is whether any of those fixed branches elicits a strict-joint success. We therefore use case-level Success@4 as the primary outcome and cluster uncertainty at the case level. To avoid hiding branch frequency, we also report branch-level strict-joint rates for every condition; these show the same ordering (1.78%, 1.02%, 48.35%, and 69.42%).

### 11.6 “HarmBench는 두 신규 조건이 비슷한데 왜 결론이 다른가?”

> HarmBench-positive rates were indeed similar for follow-up-only and quotation-only (53.55% vs 53.93%), but behavior fulfillment differed sharply (B4+: 1.14% vs 51.65%) as did CARES ASR (0.89% vs 60.91%). HarmBench captures a broad harmfulness signal, whereas the recovery/behavior rubric and CARES distinguish whether the response actually fulfills the requested target behavior or refuses. Our strict-joint endpoint requires agreement across these complementary criteria precisely to prevent a single detector from determining the mechanism claim.

### 11.7 “평가자가 GPT-4o라 target과 같은 계열이라 편향될 수 있다”

> We acknowledge this limitation. CARES and the recovery/behavior rubric were model-judged, but the strict-joint endpoint additionally required a positive label from the independently run official HarmBench classifier. We report each component metric separately and retain the conjunction as the primary automated endpoint. The revision now states that human adjudication and evaluator-model replication are needed to establish robustness beyond automated judgments.

### 11.8 “단일 모델 결과를 일반화할 수 있는가?”

> No broad cross-model generalization is intended. The new factorial result is specific to GPT-4o (`gpt-4o-2024-11-20`) on the 197-case PersonaHarm set. We have narrowed the claim accordingly and frame replication on additional target models as future work.

### 11.9 “R/B 결과를 사후 수정했는가?”

> We applied the official deterministic reprocessor to 30 records solely to restore evidence-field compatibility. The procedure downgraded 24 recovery scores and zero behavior scores; it did not upgrade successful outcomes. We report this processing step and preserve the raw and reprocessed artifacts for audit.

---

## 12. 최종 rebuttal 전 체크리스트

- [ ] main text에 4-cell Success@4 표 또는 핵심 네 비율 삽입
- [ ] percentage-point contrasts에 case-cluster 95% CI 표시
- [ ] follow-up-only의 음의 점추정치를 “harmful effect”로 단정하지 않기
- [ ] 144 failures와 36 affected cases를 분모 정책과 함께 명시
- [ ] full-sample과 quote-eligible sensitivity를 함께 보고
- [ ] interaction을 `descriptive`라고 부르고 pure causal synergy 표현 피하기
- [ ] reviewer-motivated post-hoc analysis라고 명시
- [ ] quotation source가 initial analysis와 focused readout으로 다름을 명시
- [ ] single-model/automatic-evaluation limitation 유지
- [ ] p-value보다 효과크기와 CI를 우선
- [ ] R/B compatibility repair 30건과 downgrade 방향 공개
- [ ] response letter에 수정된 section/table/page 위치를 최종 원고 기준으로 갱신
- [ ] 응답서 제출 전 숫자를 아래 machine-readable artifact와 다시 대조

---

## 13. 재현 및 감사용 결과 파일

### 최종 요약

- `result/reviewer_response/safe_release/factorial_aggregates/factorial_2x2_strict_joint_summary.json`
- `result/reviewer_response/safe_release/factorial_aggregates/factorial_summary.json`
- `result/reviewer_response/safe_release/factorial_aggregates/factorial_paired_statistics.json`
- `result/reviewer_response/safe_release/factorial_2x2_labels.jsonl`
- `result/reviewer_response/safe_release/factorial_aggregates/generation_summary.json`
- `result/reviewer_response/safe_release/metadata.json`

### 분석 코드 및 provenance

- `experiments/reviewer_response/export_safe_reviewer_artifacts.py`
- `result/reviewer_response/REPRODUCIBILITY_MANIFEST.json`

민감한 원문 응답·prompt·private goal·quotation은 private provenance 저장소에만 보존한다. 공개 저장소에는 aggregate statistics와 pseudonymous label-only rows만 포함한다.

---

## 14. 최종 권장 메시지

논문과 rebuttal 전체에서 같은 메시지를 유지한다.

> **Exact quotation was the primary enabling component. The goal-focused follow-up was not independently sufficient, but it provided additional lift when paired with quotation. This conditional pattern was robust to a quotation-eligible sensitivity analysis, although the non-stage-matched quotation sources preclude a fully causal interpretation of the interaction.**

이 서술은 결과의 강점을 살리면서도 가장 예상 가능한 리뷰어 반론—post-hoc 분석, quotation availability, 비직교성, 단일 모델, 자동평가—을 모두 선제적으로 다룬다.
