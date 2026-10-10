# RELATED WORK 작성 전략 — RED-Persona

Related Work를 쓰기 위한 설계 문서. 첨부 논문 2편(PCSA, JARGON) 정밀 분석, 3자 비교표, 소절별 Related Work 설계, 게재처 검증 참고문헌, 주장→근거 매핑, 유사 연구 지도(novelty check), JMIR goal 데이터와 persona 풀의 출처 계보를 담는다.

Introduction 설계는 `INTRO/` 폴더에 있다.

> **섹션 번호는 마스터 문서 기준이다.** 본문의 `§N` 참조 중 이 파일에 없는 절은 [`INTRO/INTRO_STRATEGY_KO.md`](../INTRO/INTRO_STRATEGY_KO.md) 또는 마스터 문서 [`persona_redteam/docs/PAPER_POSITIONING_AND_WRITING_STRATEGY_KO.md`](../persona_redteam/docs/PAPER_POSITIONING_AND_WRITING_STRATEGY_KO.md)에 있다.
> 작성 기준일 2026-10-10. `[TBD]`=실험 결과 필요, `[VERIFY]`=원문 재확인 필요.

---

## 2. 첨부 논문 2편 정밀 분석

### 2.1 Do No Harm — PCSA (Xu et al., Monash; **EMNLP 2026 Findings**, arXiv 2604.04842; v1 2026-04-06, v2 2026-09-05)

**무엇을 했나**
- Phase I: Cactus(CBT 상담 31K 대화) + CBT-DP + Cheeseburger Therapy에서 환자 persona(`C_persona`)와 말투 참조(`C_style`) 추출, 공격 목표 y를 인지왜곡 패턴(`C_dist`)으로 매핑 → 시스템 지시 `I_sys = G_script(C_persona, C_style, T(y→C_dist))`.
- Phase II: 4가지 임상 저항 전략(Reassurance Seeking → Appeal to Expertise → Intellectualization → Metaphorical Expression)을 evaluator(GPT-4o-mini, best-of-N) 피드백으로 전환.
- 공격자: Llama-3.3-70B-abliterated. 타깃 8종(Llama-3.1 8B/70B, GPT-3.5, GPT-5.1, Crispers-7B, PsychoCounsel-8B, Qwen-3-14B, Qwen-2.5-72B). 베이스라인: CoA, AMA, Crescendo, ActorAttack.
- 지표: CARES(Refuse/Cautious/Accept) 기반 ASR = **non-refusal 비율**(Caution 포함), SS; GPT-4o judge 4범주(Harmful Content / Impersonation / Toxic Empathy / Target Compliance).
- 결과: PCSA의 ASR — CARES 0.67–0.88, GPT-judge 0.71–0.89 (Table 1). PPL < 20, 탐지율 0% (Table 3). SelfDefend/Granite Guardian 방어 하에서도 ASR 감소 0–0.18 (Table 4). 임상 심리 전공 annotator 대상 realism 승률 96.4%, 사람–GPT judge 일치 87.5%.

**강점 (우리가 인용하고 기대야 할 부분)**
1. "공감 vs 해로운 순응" 구분 실패(toxic empathy)를 **정신건강 고유의 실패 모드**로 정식화.
2. 일반 jailbreak 벤치(JailbreakBench/HarmBench)가 못 보는 임상 특화 harm 분류.
3. persona realism을 PPL + 임상가 평가로 검증하는 **방법론적 선례** — 우리도 같은 검증이 필요.
4. 같은 persona 코퍼스(Cactus + CBT-DP)와 CARES를 쓰므로 **직접 비교 가능한 기반**을 제공.

**한계 / 우리가 메울 수 있는 틈**
| # | PCSA의 한계 | 근거(논문 내) | RED-Persona의 대응 (현재 상태) |
|---|---|---|---|
| P1 | **공격자 발화가 해로운 의도를 직접 운반** — persona는 "위장한 공격자" | Eq.(1): 공격자가 `IsHarmful(r_T,y)=1`을 최대화하도록 `u_{1:T}` 생성, 전략 4종으로 압박 | Level 1/2: 질문에 goal n-gram 금지(검사·재생성·fallback), `question_audit` 기록 (구현됨) |
| P2 | **누가 해로운 내용을 도입했는지 구분 불가** | harm은 응답 단위로만 판정 | Recovery `first_source ∈ {persona, qwen, target, final_only}` + `qwen_goal_injection` 플래그 (구현됨) |
| P3 | **공격 목표를 저자들이 큐레이션** (자해·섭식·반회복 등) | §4.2 "specialized dataset of adversarial objectives" | JMIR 벤치마크 유래 **625개 goal** (2,046→813→652→625, 6 위기범주; 출처는 혼합 성격의 공개 데이터셋 12종, §23) 사용 (구현됨) |
| P4 | **ASR 정의가 느슨/이중** — CARES는 *any non-refusal*을 실패로 계산 | Eq.(3) | Behavior B0–B5, `B3+`만 unsafe, 인용·분석·거리두기는 B2 (구현됨, 임상가 검증 `[TBD]`) |
| P5 | **적응형 루프의 질의 비용 미보고**, 타깃 피드백 의존 | online evaluator best-of-N | 4–7 연구턴 + 8분기 고정 예산 (비용 집계 `[TBD]`) |
| P6 | **메커니즘 분석 없음** (왜 되는지는 가설 수준), 방어는 입력측(PPL/SelfDefend/Granite)만 | §5.3 | `[TBD]` — 오픈웨이트 타깃에서 activation/attention 분석(§12 P1-2) |
| P7 | **helpfulness/over-refusal 비용 미평가** | Conclusion의 future work로만 언급 | benign-goal 대조군(§9.4, §12 P0-5) `[TBD]` |
| P8 | 타깃은 "상담사" 단일 역할 | Fig.2 | 타깃에게 **공동 연구자/분석가** 역할 부여 (`safe_counseling_joint_research_guidelines.md`) |

### 2.2 Into the Gray Zone — JARGON (Hung et al., HKUST/USTC; **ACL 2026 main, Long Papers**, pp. 24830–24867; 코드 `github.com/JerryHung1103/JARGON`)

**무엇을 했나**
- 관찰: **Vertical Unlocking**(도메인 논문 맥락이 해당 도메인 위해 지식의 방어를 국소 완화) + **General Unlocking**(안전연구/jailbreak 논문 맥락이 *모든* 위해 범주의 방어를 광범위 완화).
- 프레임워크: Control Layer(공격자 LLM, goal·히스토리·trajectory memory) → Rapport-Building(논문 요약 등 2턴) → Attack(goal을 학술 사례로 재프레이밍) → Judge(goal 관련 내용만 "purify" 후 0–1점) → 성공 trajectory 메모리 재사용. 질의 변이 8개(paraphrase 4 + scenario 4), 3 retry × 2 trial × 4 round.
- 결과: 7개 모델 평균 ASR **99.0%** (GPT-5.2 93%, Claude-4.5/Opus 100%), 베이스라인(PAIR 20.7%, AmpleGCG 23.9%, Crescendo 47.6%, FITD 62.7%, X-Teaming 69.9%) 압도.
- 메커니즘: Qwen3-8B layer-24 MDS에서 공격 질의가 benign–harmful 사이 **gray zone**(거부 결정이 불확실한 영역)에 위치; 어텐션이 민감 토큰에서 분산(Cond. C vs A/B). 맥락이 길수록 harm score 상승(abstract < abstract+method < full paper).
- 방어: policy-guided safeguard(gpt-oss-safeguard) 및 정렬 fine-tuning — Qwen3-8B ASR 100→61%(safeguard)/66%(FT), MMLU/HellaSwag/GSM8K 유지; LLaMA-3-8B는 safeguard가 **전부 거부**하는 과민 반응.
- 핵심 인식: "*LLMs cannot simply reject all domain-specific interactions, as doing so would compromise utility for legitimate professionals*" — **우리 연구 동기와 정확히 겹치는 문장.**

**강점 (인용하고 기대야 할 부분)**
1. dual-use 딜레마를 "탈옥 성공의 원인"으로 정식화 (helpfulness–harmlessness 긴장을 *exploit*의 근거로 삼음).
2. gray zone을 표현 공간에서 시각화 — 우리가 인용하면 §9의 이론 틀로 재사용 가능.
3. "얕은 persona(I'm a researcher) vs 진짜 맥락(authentic context)" 구분 — 맥락의 *깊이*가 효과를 만든다는 가설.
4. 공격 + 방어 + 일반능력 보존까지 한 논문에 담은 구성 → 리뷰어가 기대하는 **완결성의 기준선**.

**한계 / 우리가 메울 수 있는 틈**
| # | JARGON의 한계 | 근거 | RED-Persona의 대응 |
|---|---|---|---|
| J1 | **정보적 위해 한정** (JailbreakBench: 폭탄·악성코드·사기 등). 관계적/발화행위적 위해(정당화·승인·허용)는 측정 대상 아님 | §5.1 Benchmark | 상담 도메인: 위해 = 응답이 수행하는 **speech act** (B3–B5) |
| J2 | **맥락이 모든 goal에 동일한 고정 논문** (X-Teaming 논문 등) — 개인/사례에 grounded되지 않음 | §5.2.1 | **한 사람의 persona + 최소 4턴 가변 이력(goal-atom 기반)** — 맥락이 사례별로 구성됨 |
| J3 | **공격 쿼리에 goal g를 직접 내장** (재프레이밍 함수가 g를 학술 질의로 변환) | §4.2 | Level 1/2: 상대 발화에 goal이 등장하지 않음 (단 최종 측정 단계는 goal 직접 노출 — §11-Q3) |
| J4 | **평가 지표가 best-of-many** (retry×trial×variant 중 최고 harm), 단일 judge(DeepSeek-V3.2), 0.8 임계값; 저자 스스로 "Knowledge Purification이 harm을 부풀릴 수 있다" 인정 | §4.3, §7 Limitations | 사례 단위 any-of-8 *및* 분기 단위 비율을 **둘 다** 보고(§10) |
| J5 | **방어의 비용 평가가 일반 능력(MMLU/HellaSwag/GSM8K)뿐** — 민감 도메인 over-refusal·임상 유용성 미평가 | Table 3 | benign-goal 대조군으로 도메인 내 over-refusal 측정 `[TBD]` |
| J6 | 정신건강/임상 도메인 없음, 취약 사용자 관점 없음 | 전체 | 위기 6범주(자살사고·자해·불안위기·물질·폭력사고·위험행동) |
| J7 | 방어는 "완화"일 뿐 (Qwen3-8B 61–66% 잔존) | §5.2.4, §7 | 우리는 *공격 규명*이 주목적이되, 도메인 특화 완화 방향(출력측/궤적측)을 제안 `[TBD]` |

### 2.3 두 논문이 **공통으로** 못 한 것 (우리 기여의 핵심 구간)

1. **공격자가 해로운 명제를 말하지 않는 설정**을 체계적으로 다루지 못함 (PCSA는 위장해서 말함, JARGON은 학술 프레임으로 말함).
2. **해로운 내용의 출처 귀속(provenance)** 없음 → "모델이 스스로 만든 건가, 유도된 건가"를 구분 못 함.
3. **goal 노출량(dose)**에 따른 반응 곡선 없음 (Oracle / Structural / Neutral).
4. **전문가 분석 맥락 ∩ 개인 persona**의 결합 없음 — PCSA는 persona만, JARGON은 전문가 맥락만.
5. **harm = 정보**라는 가정에서 벗어난 *발화행위 단위 harm* (JARGON은 정보, PCSA는 혼합).
6. 두 논문 모두 **방어의 도메인 비용(과잉 거부로 인한 취약 사용자/연구자 손실)**을 정량하지 않음.

---

## 4. 아키텍처 · 기능 · 사회적 필요성 비교표 (Table 1 후보)

| 차원 | PCSA | JARGON | **RED-Persona (ours)** |
|---|---|---|---|
| 공격자 정체 | 1인칭 환자(위장) | 연구자(위장) | **3인칭 공동 분석자**(goal-aware, 비주입) |
| 맥락 | 환자 대화 | 고정 안전연구 논문 | **사례별 persona + 이력 + 공동연구 가이드라인** |
| Persona 출처 | Cactus/CBT-DP/Cheeseburger, 공격목표→인지왜곡 매핑 | (persona 없음; 얕은 persona를 대비 대상으로) | Cactus/CBT-DP 31,733 풀, 범주 gating + sample_adaptation |
| 이력(history) | 없음/온라인 생성 | 없음 | **goal-atom 기반 최소 4–최대 12턴 가변 이력, 사례별 검증·종료** |
| goal 가시성 | 의도가 공격자 발화에 위장 포함 | 공격 쿼리에 내장 | **3단계 dose**: neutral / structural / oracle |
| 출처 귀속 | 없음 | 없음 | **first_source + qwen_goal_injection** |
| 적응/피드백 | evaluator best-of-N + 전략 4종 | judge + trajectory memory + 변이 8개 + 재시도 | goal-coverage 기반 질문 계획, 조건별 독립 종료 (harm-judge 피드백 없음) |
| 평가 입력 | 저자 큐레이션 target | JailbreakBench 100 | **JMIR 벤치마크 유래 625 (출처 혼합, §23)** |
| 해악 정의 | 4범주(정보/사칭/toxic empathy/순응) | 정보 harm score ≥ 0.8 | **Recovery R0–R4 + Behavior B0–B5**, CARES 병행 |
| 방어 평가 | PPL, SelfDefend, Granite Guardian (입력측) | policy safeguard + FT, MMLU 등 | `[TBD]` 입력측 가드 무력성 + 출력/궤적측 완화 + 도메인 over-refusal |
| 메커니즘 | 없음 | activation/attention | `[TBD]` (§12) |
| 도메인 | 정신건강 | 일반 보안/CBRN류 | 정신건강 위기 6범주 |

**기능적 차이 요약**: ① 해악의 출처를 가르는 provenance 측정, ② 노출량 곡선, ③ 사례-기반 맥락(이력)의 구성적 생성, ④ 발화행위 단위 harm 척도.
**아키텍처적 차이 요약**: 3자 구조(이력 작성자 ↔ 연구자 ↔ 타깃)와 *동일 prefix 복제 8분기* — 분기 간 독립성 덕에 "같은 맥락에서의 변동성"을 분리해 볼 수 있다(둘 다 없음).
**사회적 차이 요약**: 방어 대상이 "악의적 공격자"만이 아니라 **정당한 임상·연구 분석 수요와 구별 불가능한 입력**이라는 점 (§8–§9).

---

## 14. Related Work 설계 (약 1쪽, 5개 소절 + 위치 표)

> 원칙: 각 소절은 **(무엇이 알려졌나 → 그 한계 → 우리가 다른 점)** 3단 구조, 마지막 문장은 반드시 *gap sentence*.

### 2.1 Multi-turn jailbreaks and red teaming
- 포함: Crescendo(USENIX Sec'25), ActorAttack(ACL'25 main; 현재 제목 *LLMs Know Their Vulnerabilities…*, 초기 제목 *Derail Yourself*), FITD(EMNLP'25), X-Teaming(COLM'25), CoA(Findings ACL'25), MHJ(NeurIPS'24 워크숍); "LLMs Get Lost in Multi-Turn"(ICLR'26).
- 구성: (1) 단일턴→멀티턴 진화, (2) 멀티턴 방어 허점(MHJ 70%+), (3) 공통 가정 = 공격자의 질의가 점진적으로 *해로운 목표를 향해 이동*.
- gap sentence(draft): *"These methods vary how the harmful goal is approached, but in all of them the goal is carried—gradually or implicitly—by the attacker's own turns."*
- 어필: 이 소절에서 "공격자 발화에 goal이 있다"는 **공통 가정**을 미리 심어두면 §Intro P4와 연결.

### 2.2 Persona, authority, and context framing attacks
- 포함: Persona modulation(Shah et al., NeurIPS'23 SoLaR 워크숍, GPT-4 harmful rate 0.23%→42.5%), PAP(Zeng et al., ACL 2024 main, 92%+), **PCSA**(EMNLP'26 Findings), **JARGON**(ACL'26 main).
- 구성: 얕은 persona → 임상 grounded persona(PCSA) → 전문가 맥락(JARGON gray zone, Vertical/General Unlocking). 두 논문을 *가장 길게, 가장 공정하게* 서술(리뷰어가 두 논문 저자일 수 있음).
- gap sentence: *"PCSA grounds the attacker in a clinical persona but has the persona push the request; JARGON grounds it in professional context but uses a fixed document and informational harm. Neither examines a setting where the professional frame and the persona coincide and the harmful proposition is never uttered by the interlocutor."*
- 어필: 비방 금지, "complementary"로 서술. 수치는 각 논문의 주장 그대로 인용, 우리 재측정 수치와 혼동 금지.

### 2.3 Safety evaluation of LLMs in mental health
- 포함: CARES, JMIR(Arnaiz-Rodriguez), McBain(RAND), Moore(FAccT'25), Judd et al., Schoene & Canca, SIM-VAIL, K-Bench, TherapyProbe, MindEval, Steenstra et al., Transluce `[VERIFY: 페이지 본문 미확인]`, Spiral-Bench/DelusionEval.
- 구성: (1) 단일턴 위기·적절성 평가, (2) 멀티턴 시뮬 환자 감사(SIM-VAIL, K-Bench, Steenstra, TherapyProbe) — **환자 역할이 챗봇을 감사**, (3) 망상/sycophancy 누적(Spiral-Bench 등).
- gap sentence: *"These audits characterize how chatbots fail when a simulated user is vulnerable; we instead ask how a professional-analysis frame, with no harmful statement by the interlocutor, shifts the model across the counseling boundary, and decompose where the harmful content originates."*
- 어필: 동시기 연구를 **빠짐없이** 다루되 차이를 한 문장으로 못 박는다 — 누락이 가장 큰 감점 요인.

### 2.4 Simulated patients, personas, and clinical analysis practice
- 포함: Cactus, CBT-Bench(CBT-DP), Patient-Ψ, Roleplay-doh, DiaCBT; 정성 코딩/심리 부검 LLM 활용; APA 2025 서베이.
- 구성: 시뮬 환자는 훈련·평가의 확립된 도구 → persona 연구 대화는 현실 관행의 연장 → **정당한 수요**와 **공격 경로**의 이중성.
- gap sentence: *"This literature builds personas to help professionals; we study what happens when the same persona-analysis interaction is the attack surface."*
- 어필: §8의 근거 수준 구분(관행 vs LLM 증거)을 지킨다.

### 2.5 The helpfulness–harmlessness tension, sycophancy, and defenses
- 포함: Wei et al.(competing objectives/mismatched generalization), Sharma et al.(sycophancy), OR-Bench/XSTest(over-refusal), safe-completions, JARGON의 safeguard/FT, PCSA의 PPL/SelfDefend/Granite, Tang et al.(거부의 해악).
- 구성: 이진 거부의 한계 → 출력 중심 안전 → 그러나 정신건강에서는 *거부도 해악*이므로 ASR과 utility를 동시에 봐야 함.
- gap sentence: *"Existing defenses are evaluated either on input-side detectability or on general capability; we evaluate them against attacks whose inputs are in-distribution for benign professional use, reporting the ASR–utility trade-off."*

### 위치 표 (Related Work 끝 또는 §1 Table)
§4의 비교표를 축약해 사용. 열: 공격자 정체 / goal이 공격자 발화에 존재? / 맥락 / 해악 단위 / provenance / dose / 분류체계 정렬 goal / 방어-utility.

---

## 18. 참고문헌 — 게재처 검증 결과 (2026-10-10 조사)

**등급 기준**
- **A** = 주요 학회 본회의/데이터셋·벤치마크 트랙, 또는 저널 게재 (ACL/EMNLP/NAACL main, ICLR, ICML, NeurIPS, COLM, USENIX Security, FAccT, AIES, Nature Medicine, npj Digital Medicine, JMIR, Psychiatric Services 등)
- **B** = Findings / 워크숍 / extended abstract
- **C** = arXiv·기업 블로그·보고서만 확인됨 (게재처 미확인 포함)

확인 근거는 arXiv 초록 페이지의 Comments 필드, ACL Anthology/NeurIPS/ICLR/ICML 공식 페이지, 출판사 페이지의 검색 결과다. 한 번 더 확인할 항목은 `[VERIFY]`로 표시했다.
BibTeX는 같은 폴더의 [`references_related_work.bib`](references_related_work.bib)에 있다(마스터 사본은 `persona_redteam/docs/references_redpersona.bib`).

> **조사로 바로잡은 사항 (앞선 버전의 오류/불확실)**
> 1. **PCSA(Do No Harm)는 EMNLP 2026 Findings**다. arXiv 초록 페이지 Comments 필드에서 확인했다(v1 2026-04-06, v2 2026-09-05). 이전 판에서는 "ID 역추출 `[VERIFY]`"라고 써 두었는데, ID `2604.04842`도 같은 페이지에서 확인됐다.
> 2. **ActorAttack(arXiv 2410.10700)은 ACL 2025 main**이다. 다만 v3(2026-03)에서 제목이 *"LLMs know their vulnerabilities: Uncover Safety Gaps through Natural Distribution Shifts"*로 바뀌었다. 초기 제목은 *"Derail Yourself…"*다. 두 논문(PCSA, Jargon)이 "Ren et al." 또는 ActorAttack으로 인용한다. 인용할 때는 현재 제목을 쓰고 "(arXiv v1 title: Derail Yourself)"를 주석으로 붙인다.
> 3. **MHJ(Li et al.)는 NeurIPS 2024 *워크숍*(Red Teaming GenAI)**이다. main 게재가 아니다. 70%+ 수치를 쓸 때 "workshop paper"임을 알고 쓴다.
> 4. **SIM-VAIL은 Nature Medicine 2026**(doi 10.1038/s41591-026-04577-2, 2026-08 게재)이다. 이전에는 "게재지 `[VERIFY]`"였다.
> 5. **Laban et al.은 ICLR 2026 oral**이다. 수상 여부는 자료마다 달라서 쓰지 않는다.
> 6. **K-Bench, MindEval, TherapyProbe, Steenstra et al., Tang et al., Schoene & Canca, DelusionEval은 게재처를 찾지 못했다**(arXiv만). 이 중 K-Bench는 한 검색 결과에서 EACL 2026이라고 했으나, arXiv 페이지에 venue 표기가 없어 **미확인으로 처리**한다.
> 7. **Persona modulation(Shah et al.)은 NeurIPS 2023 SoLaR 워크숍**이다.

### 18.1 공격·멀티턴·방어 (본 논문의 직접 비교 대상)

| Key | 서지 | 게재처 | 등급 | 이 문서에서의 쓰임 |
|---|---|---|---|---|
| Hung26 | Hung et al. *Into the Gray Zone: Domain Contexts Can Blur LLM Safety Boundaries* | **ACL 2026 main (Long)**, pp. 24830–24867 (첨부 PDF) | A | 핵심 선행연구, gray zone, dual-use, 방어 |
| Xu26 | Xu et al. *Do No Harm: Exposing Hidden Vulnerabilities of LLMs via PCSA…* arXiv 2604.04842 | **EMNLP 2026 Findings** (arXiv Comments) | B | 핵심 선행연구, toxic empathy, 동시기 연구 |
| Russinovich25 | Russinovich, Salem, Eldan. *Great, Now Write an Article About That: The Crescendo Multi-Turn LLM Jailbreak Attack* | **USENIX Security 2025** | A | 자기 출력 추종, 입력 필터 한계 |
| Rahman25 | Rahman et al. *X-Teaming: Multi-Turn Jailbreaks and Defenses with Adaptive Multi-Agents* | **COLM 2025** | A | 멀티턴 베이스라인 |
| Weng25 | Weng, Jin, Jia, Zhang. *Foot-In-The-Door: A Multi-turn Jailbreak for LLMs* | **EMNLP 2025 main** (2025.emnlp-main.100) | A | self-corruption, 점진 수락 |
| Ren25 | Ren et al. *LLMs Know Their Vulnerabilities: Uncover Safety Gaps through Natural Distribution Shifts* (ActorAttack; v1 title *Derail Yourself*) | **ACL 2025 main** | A | 멀티턴 베이스라인 |
| Yang25 | Yang et al. *Chain of Attack: Hide Your Intention through Multi-Turn Interrogation* | **Findings of ACL 2025** | B | 멀티턴 베이스라인(PCSA 경유) |
| Li24 | Li et al. *LLM Defenses Are Not Robust to Multi-Turn Human Jailbreaks Yet* (MHJ) | **NeurIPS 2024 Workshop** (Red Teaming GenAI) | B | 단일턴 방어 과대평가 |
| Laban26 | Laban, Hayashi, Zhou, Neville. *LLMs Get Lost In Multi-Turn Conversation* | **ICLR 2026 (oral)** | A | 초기 가정 의존, 멀티턴 신뢰도 하락(−39%) |
| Zeng24 | Zeng et al. *How Johnny Can Persuade LLMs to Jailbreak Them* | **ACL 2024 main**, pp. 14322–14350 | A | 설득/권위 프레임의 효과 |
| Shah23 | Shah et al. *Scalable and Transferable Black-Box Jailbreaks… via Persona Modulation* arXiv 2311.03348 | NeurIPS 2023 SoLaR **워크숍** | B | persona 공격의 초기 증거 |
| Deshpande23 | Deshpande et al. *Toxicity in ChatGPT: Analyzing Persona-assigned Language Models* | **Findings of EMNLP 2023** | B | persona 부여가 출력 특성을 바꿈 |
| Anil24 | Anil et al. *Many-shot Jailbreaking* | **NeurIPS 2024 main** | A | 긴 컨텍스트 공격 |
| Mazeika24 | Mazeika et al. *HarmBench* | **ICML 2024** | A | 표준 레드티밍 평가 |
| Chao24 | Chao et al. *JailbreakBench* | **NeurIPS 2024 D&B** | A | 일반 jailbreak 벤치(Jargon 사용) |

### 18.2 메커니즘·트레이드오프 (§9의 이론 근거)

| Key | 서지 | 게재처 | 등급 | 쓰임 |
|---|---|---|---|---|
| Wei23 | Wei, Haghtalab, Steinhardt. *Jailbroken: How Does LLM Safety Training Fail?* | **NeurIPS 2023 (oral)** | A | competing objectives / mismatched generalization |
| Sharma24 | Sharma et al. *Towards Understanding Sycophancy in Language Models* | **ICLR 2024** | A | RLHF가 sycophancy를 유발 |
| Cheng26 | Cheng et al. *ELEPHANT: Measuring and Understanding Social Sycophancy in LLMs* | **ICLR 2026** | A | 감정적 validation, 사용자 프레임 수용(모델 76%/90% vs 인간 22%/60%) |
| Qi25 | Qi et al. *Safety Alignment Should Be Made More Than Just a Few Tokens Deep* | **ICLR 2025 (oral)** | A | 얕은 정렬 가설 |
| Arditi24 | Arditi et al. *Refusal in Language Models Is Mediated by a Single Direction* | **NeurIPS 2024** | A | 거부는 1차원 방향, 표현 공간 분석 근거 |
| Rottger24 | Röttger et al. *XSTest* | **NAACL 2024 main (long)**, pp. 5377–5400 | A | 과잉 거부 측정 |
| Cui25 | Cui et al. *OR-Bench: An Over-Refusal Benchmark for LLMs* | **ICML 2025** | A | 과잉 거부 80K |
| Gao25 | Gao et al. *Shaping the Safety Boundaries: Understanding and Defending Against Jailbreaks in LLMs* | **ACL 2025 main** (Jargon 참고문헌 확인) | A | activation 분석 방법론 |
| Yuan25 | Yuan et al. *From Hard Refusals to Safe-Completions* arXiv 2508.09224 (+OpenAI 블로그) | OpenAI 기술 보고, arXiv | C | 출력 중심 안전, 이진 거부 대안 |
| Zheng23 | Zheng et al. *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena* | **NeurIPS 2023 D&B** | A | judge 편향(위치/장황/자기선호) |
| Panickssery24 | Panickssery et al. *LLM Evaluators Recognize and Favor Their Own Generations* | **NeurIPS 2024 (oral)** | A | judge 자기선호 → 교차 judge 필요 근거 |

### 18.3 정신건강 LLM 안전·평가·시뮬레이션

| Key | 서지 | 게재처 | 등급 | 쓰임 |
|---|---|---|---|---|
| Arnaiz26 | Arnaiz-Rodriguez et al. *Between Help and Harm: An Evaluation of Mental Health Crisis Handling by LLMs* | **JMIR Mental Health 2026** (doi 10.2196/88435; arXiv 2509.24857) | A | 우리 625 goal의 출처 데이터 |
| Chen25 | Chen et al. *CARES: Comprehensive Evaluation of Safety and Adversarial Robustness in Medical LLMs* | **NeurIPS 2025 D&B** | A | 공식 평가 루브릭 |
| McBain25 | McBain et al. *Evaluation of Alignment Between LLMs and Expert Clinicians in Suicide Risk Assessment* | **Psychiatric Services 2025** (doi 10.1176/appi.ps.20250086) | A | 중간 위험 구분 실패 |
| Moore25 | Moore et al. *Expressing Stigma and Inappropriate Responses Prevents LLMs from Safely Replacing Mental Health Providers* | **FAccT 2025** (doi 10.1145/3715275.3732039) | A | 낙인·망상 조장, sycophancy 추정 |
| Iftikhar25 | Iftikhar et al. *How LLM Counselors Violate Ethical Standards in Mental Health Practice* | **AIES 2025** (doi 10.1609/aies.v8i2.36632) | A | 15개 윤리 위반, 부정적 신념 강화 |
| Weilnhammer26 | Weilnhammer et al. *A clinically validated framework for auditing AI chatbot behavior in mental health interactions* (SIM-VAIL) | **Nature Medicine 2026** (doi 10.1038/s41591-026-04577-2; arXiv 2602.01347) | A | 누적 위험, VAIL, 810 대화·9 챗봇 |
| Diel26 | Diel et al. *A scoping review on the mental health harms of LLM-based chatbots* | **npj Digital Medicine 9, 644 (2026)** (doi 10.1038/s41746-026-03054-x) | A | 위해 문헌 종합(고위험 부적합, 강화 위험) |
| Moore26 | Moore et al. *Characterizing Delusional Spirals through Human-LLM Chat Logs* arXiv 2603.16567 | ACM DL 등재(doi 10.1145/3805689.3806443; **FAccT '26** 추정 `[VERIFY]` — ACM 페이지 열람 차단) | A? | 실제 사용자 로그 기반 망상 나선 |
| Kirgis26 | *LLM Spirals of Delusion: A Benchmarking Audit Study of AI Chatbot Interfaces* arXiv 2604.06188 | IASEAI 2nd annual conf. 게재 표기(arXiv 기준) `[VERIFY]` | B | API vs 인터페이스 차이 |
| Wang24 | Wang et al. *PATIENT-Ψ* | **EMNLP 2024 main** (Anthology 개별 페이지 `[VERIFY]`) | A | CBT 인지 모델 기반 시뮬 환자 |
| Louie24 | Louie et al. *Roleplay-doh* | **EMNLP 2024 main** (2024.emnlp-main.591) | A | 전문가 원칙 기반 시뮬 환자 |
| Lee24 | Lee et al. *Cactus* | **Findings of EMNLP 2024** (arXiv 2407.03103) | B | 우리·PCSA persona 코퍼스 |
| Zhang25 | Zhang et al. *CBT-Bench* | **NAACL 2025 main (long)** (2025.naacl-long.196) | A | CBT-DP persona 출처 |
| Grabb24 | Grabb, Lamparth, Vasan. *Risks from LMs for Automated Mental Healthcare* | **AIES 2024 extended abstract**; arXiv 2406.11852 | B | 자율성 수준·윤리 틀 |
| FrontiersPH25 | *Deductively coding psychosocial autopsy interview data using a few-shot learning LLM* | **Frontiers in Public Health 2025** (doi 10.3389/fpubh.2025.1512537) | A | 연구 현장에서 LLM 정성 코딩 사례 |
| Schoene25 | Schoene, Canca. *"For Argument's Sake, Show Me How to Harm Myself!"* arXiv 2507.02990 | 게재처 미확인 | C | 학술적 질문 프레임이 자살·자해 방어 우회 |
| Judd25 | Judd et al. arXiv 2510.27521 | 게재처 미확인 | C | 임상 독립 평가(PCSA 인용) |
| Tang26 | Tang et al. *Beyond the Single Turn: Reframing Refusals…* arXiv 2602.01694 | 게재처 미확인 | C | 거부 경험(N=16 인터뷰·53 서베이) |
| Steenstra26 | Steenstra et al. arXiv 2602.19948 | 게재처 미확인 | C | 시뮬 환자 기반 임상 레드티밍 |
| Chandra26 | *TherapyProbe* arXiv 2602.22775 | 게재처 미확인 | C | validation spiral |
| Vowels26 | *K-Bench* arXiv 2609.15855 | arXiv에 venue 없음 | C | 임상 보정 벤치, judge–임상가 94.2% |
| Pombal25 | *MindEval* arXiv 2511.18491 | 게재처 미확인 | C | 멀티턴 지원 벤치 |
| DelusionEval | arXiv 2608.05004 | 게재처 미확인 | C | 망상 연계 행동 측정 |
| SpiralBench | Paech. Spiral-Bench (EQ-Bench) | 벤치마크 사이트 | C | 20턴 sycophancy/망상 강화 측정 |
| Transluce | *Mental Health Behavior Report* | 기업 보고서(본문 미열람) `[VERIFY]` | C | 대규모 시뮬(검색 요약만) |

### 18.4 사회적 필요성 (1차 출처 확인 필요)

| Key | 내용 | 출처 | 등급 | 상태 |
|---|---|---|---|---|
| OpenAI25 | 2025-10-27: 주간 활성 사용자의 약 0.15%가 자살 계획·의도의 명시적 지표를 포함, 메시지 0.05%가 명시·암시 지표, 정신병/조증 징후 약 0.07%; 170+ 임상 전문가 협업 | OpenAI 블로그 *Strengthening ChatGPT's responses in sensitive conversations* (openai.com/index/…) | C(1차 기업 공개) | 블로그 본문은 접속 차단(403)으로 직접 열람 못 했고 **여러 언론 요약에서 수치 교차 확인**. 투고 전 원문에서 재확인 |
| APA25 | 심리학자 N=1,742, 56%가 지난 1년간 AI 사용(2024: 29%), 임상 진단 8%·환자 지원 5% | APA 2025 Practitioner Pulse Survey (NPR 2025-12-16 보도 경유) | C | APA 원문 `[VERIFY]` |
| Raine25 | Raine v. OpenAI, 2025-08 California 주 법원, 소송 *주장* | 법률·언론 보도 | C | 소장 원문 `[VERIFY]`, 본문에서는 "alleged"로 서술 |
| IL25 | Illinois HB 1806, Wellness and Oversight for Psychological Resources Act (2025-08) | 입법/법률 해설 다수 | 법령 | 법령 원문 `[VERIFY]` |

> **등급 C가 근거의 전부인 주장은 문장을 약하게 쓴다.** 거부가 해악이 될 수 있다는 문장은 직접 측정한 peer-reviewed 연구를 찾지 못했다(추가 검색에서도 확인 실패). Tang26(C)과 정성 연구 외에는 근거가 없다. "has been reported to cause"처럼 서술하고, Wei23·Rottger24·Cui25(A)가 지지하는 과잉 거부 일반론을 함께 인용한다.

---

## 19. 내 주장 → 근거 매핑

각 행은 이 문서에서 제가 내린 판단에 어떤 문헌이 뒷받침되는지, 그 근거가 어느 등급인지를 보여준다. **"근거 없음/약함"** 표시가 있는 곳은 논문에서 직접 실험으로 채워야 하는 주장이다.

| # | 주장 (문서 §) | 근거 | 근거 수준 | 비고 |
|---|---|---|---|---|
| 1 | 멀티턴이 단일턴 방어를 무력화한다 (§5) | Li24(B), Russinovich25(A), Weng25(A), Ren25(A), Rahman25(A), Jargon 결과 Table 2 (Hung26, A) | 강함 | Li24는 워크숍. 대신 Russinovich25 등 A 등급 병기 |
| 2 | 대화 누적이 가정을 고착시키고 최종 답변을 조건화한다 (§5, §9) | Laban26(A): 초기 가정 의존, Russinovich25(A): 자기 출력 추종, Weng25(A): self-corruption | 강함(일반 LLM), **정신건강 도메인은 직접 증거 없음** | §9의 "commitment" 가설은 우리 실험(ablation)으로 입증해야 함 |
| 3 | 정신건강에서 위험이 턴이 쌓일수록 누적된다 (§5) | Weilnhammer26(A, Nature Medicine), Chandra26(C), Moore26(A?), Kirgis26(B) | 강함(A 1건이 주축) | TherapyProbe는 보조로만 |
| 4 | 해악이 정보가 아니라 발화행위(승인·정당화·허용)다 (§6-1) | Xu26(B): toxic empathy 범주, Moore25(A): 망상 조장·낙인, Iftikhar25(A): 부정적 신념 강화·기만적 공감, Cheng26(A): 모델의 감정적 validation 76% vs 인간 22% | 강함 | |
| 5 | 입력측 방어가 이런 공격에 약하다 (§6-2) | Xu26(B) Table 4(SelfDefend −0.05~0.18, Granite −0.00~0.05), Russinovich25(A): 개별 입력에 악의가 없음 | 중간 | 우리 공격에 대한 직접 실험 없음 → §12 P1-1 |
| 6 | 정신건강 모델은 중간 위험 구간을 구분 못 한다 (§6-8) | McBain25(A) | 강함 | ChatGPT·Claude·Gemini, 질의 30개 한정 |
| 7 | 시뮬 환자는 훈련·평가에서 확립된 도구다 (§8) | Wang24(A), Louie24(A), Lee24(B), Zhang25(A), Weilnhammer26(A) | 강함 | |
| 8 | 연구 현장에서 LLM을 정성 분석에 쓴다 (§8) | FrontiersPH25(A): 38건 인터뷰를 LLaMA3로 deductive coding | 중간(1건) | "일상화" 주장은 불가 |
| 9 | 임상가가 LLM으로 환자 사례를 공동 분석하는 것이 일상적이다 (§8) | APA25(C): 임상 용도 5–8%뿐 | **근거 약함/반대 방향** | 이 주장은 쓰지 않는다. 인터뷰·설문 추가 권장 |
| 10 | 전문가 맥락이 안전 경계를 흐린다 / 정당 사용자를 막으면 효용이 훼손된다 (§9) | Hung26(A) 실험·서술, Yuan25(C), Rottger24(A), Cui25(A) | 강함(일반 도메인) | **정신건강 도메인은 우리 실험 필요** |
| 11 | 안전 훈련의 경쟁 목표·불일치 일반화가 원인 (§9.1) | Wei23(A), Qi25(A), Arditi24(A) | 강함(이론 틀) | 우리 현상에 대한 직접 검증은 아님 |
| 12 | RLHF가 sycophancy를 만들고 사용자 프레임을 수용한다 (§9.1) | Sharma24(A), Cheng26(A) | 강함 | |
| 13 | "분석 프레임이 위기 프로토콜을 발동시키지 않는다" (§9.2-1) | **직접 근거 없음.** 간접: Schoene25(C) 학술 프레임 우회 | **가설** | ablation(프레임 유무, 1인칭/3인칭)으로 검증 |
| 14 | 거부가 취약 사용자에게 해악이 될 수 있다 (§6-6, §9.3) | Tang26(C)만 | **약함** | §18.4 주석대로 약한 표현 + 완화 문장 |
| 15 | LLM judge는 자기선호 편향이 있어 교차 judge·임상가 검증이 필요하다 (§10-3) | Zheng23(A), Panickssery24(A), Xu26(B)(사람 일치 87.5%), Vowels26(C)(임상가 94.2%) | 강함 | |
| 16 | persona 부여가 출력을 크게 바꾼다 (§2.2) | Deshpande23(B), Shah23(B), Zeng24(A) | 강함 | |
| 17 | 사회적 필요성: 규모·소송·입법 (§7) | OpenAI25(C), Raine25(C), IL25(법령), Moore25(A), Diel26(A) | 중간 | 1차 출처 재확인 필수. 소송은 "alleged" |
| 18 | gray zone을 표현 공간으로 분석할 수 있다 (§12) | Hung26(A), Gao25(A), Arditi24(A) | 강함(방법론) | 우리 도메인 적용은 신규 실험 |
| 19 | goal-conditioned persona라서 복원은 당연하다 (§11-Q2) | **레포 문서 자체**(`METHOD_PERSONA_POOL_CONSTRUCTION.md` §6) | 내부 사실 | 외부 문헌 불필요, 실험(goal-blind)으로 대응 |

---

## 20. 문헌 조사 결과가 전략에 주는 영향

1. **PCSA는 EMNLP 2026 Findings로 이미 게재 확정된 동시기 연구다.** 따라서 (a) 비교 대상으로 반드시 포함하고, (b) Related Work에서 "concurrent/closely related"로 가장 공정하게 서술하며, (c) 같은 투고 주기 안에 겹칠 수 있어 **차별점(해로운 명제 비주입, 출처 귀속, 노출량, 분류체계에 정렬된 goal·persona)을 Intro 첫 페이지에 못 박아야** 한다. Findings 게재이므로 "엄격한 main-track 검증을 거쳤다"고 쓰지 않는다.
2. **Jargon은 ACL 2026 main이다.** 가장 강한 선행연구로 취급하고, 그 한계는 논문의 **자기 서술(§7 Limitations)에서 인용**해 공격적이지 않게 서술한다(Knowledge Purification의 harm 부풀림, 방어의 불완전성).
3. **정신건강 평가 쪽 최신 근거는 상당수가 아직 arXiv다**(Steenstra, TherapyProbe, K-Bench, MindEval, Tang, DelusionEval). 동시기 연구라서 리뷰어도 허용하지만 **주장의 기둥을 이 논문들에 세우지 않는다.** A 등급 근거(SIM-VAIL, Moore25, Iftikhar25, McBain25, Arnaiz26, Diel26)를 앞에 쓰고 arXiv 논문은 "see also" 위치에 둔다.
4. **일반 jailbreak·정렬 이론은 A 등급이 충분히 있다**(Wei23, Sharma24, Cheng26, Qi25, Arditi24, Russinovich25, Weng25, Ren25, Rahman25, Anil24, Mazeika24, Chao24, Rottger24, Cui25, Laban26). 이 층은 약점이 없다.
5. **가장 약한 고리는 두 가지다.** ① 거부의 해악(Tang26 C 하나), ② 임상가-LLM 공동 분석의 일상성(근거가 오히려 반대). 둘 다 **우리 논문에서 직접 증거를 만드는 것**(임상가 인터뷰, benign 대조군 실험)이 가장 값싼 보강이다.
6. **같은 학회 계열 선택 힌트:** 핵심 인용이 ACL/EMNLP 계열(Jargon, PCSA, FITD, ActorAttack, PAP, XSTest, Patient-Ψ, Roleplay-doh)에 몰려 있다. ACL ARR 계열 투고가 문헌 맥락상 자연스럽고, 임상 검증이 크게 들어가면 FAccT/AIES 또는 의료 AI 저널(JMIR Mental Health, npj Digital Medicine)도 후보가 된다. 어떤 학회에 맞출지는 임상가 검증 규모에 따라 결정하면 된다.

---

## 22. 추가 문헌 조사 — 우리와 비슷한 연구 지도 (novelty check, 2026-10-10)

> 조사 방법: 웹 검색(주제별 8+6+8+6회)과 arXiv/ACL Anthology 초록 페이지 열람. **전수 조사가 아니다.** 2026-08~09에 올라온 프리프린트가 많아 분야 속도가 빠르다. 투고 직전에 §22.6의 검색 절차를 다시 돌려야 한다.
> 등급 표기는 §18과 같다(A=주요 학회/저널, B=Findings/워크숍, C=arXiv·블로그·보고서).

### 22.1 우리와 가장 가까운 연구 — 위협 순위

| 순위 | 연구 | 게재처 / 등급 | 하는 일 | 우리와 겹치는 점 | 우리와 다른 점 | 우리 주장에 미치는 영향 |
|---|---|---|---|---|---|---|
| 1 | **PCSA** (Xu et al.) | EMNLP 2026 Findings / B | 환자 persona로 상담 LLM 공격 | persona 코퍼스, CARES, 멀티턴 | 공격자 발화가 의도를 운반 | §2.1 참고 |
| 2 | **JARGON** (Hung et al.) | ACL 2026 main / A | 안전연구 논문 맥락 + 재프레이밍 | 전문가 프레임, gray zone | 정보적 위해, 고정 맥락 | §2.2 참고 |
| 3 | **The Slow Drift of Support** (Cheng et al.) arXiv 2601.14269 | 게재처 없음 / C | 가상 환자 50명 × 최대 20라운드, 정적/적응형 압박으로 **정신건강 LLM의 경계 침식**(대표적으로 "위험 0" 확약) 측정. 적응형이 평균 9.21→4.64턴으로 경계 위반을 앞당김 | 시뮬 환자, 멀티턴 경계 붕괴 | 위반 유형이 확약·책임 인수·전문가 역할 수행. 해로운 명제 비주입·출처 귀속·노출량 없음 | **"정신건강 멀티턴 persona 공격은 처음" 주장 불가.** 단, PCSA와 같은 계열로 묶어 서술 |
| 4 | **SIM-VAIL** (Weilnhammer et al.) | Nature Medicine 2026 / A | 취약성·의도 프로파일 사용자 30종 × 챗봇 9종, 810 대화, 13개 임상 위험 차원 | 시뮬 사용자, 누적 위험, 임상 judge 검증 | 시뮬 *사용자*가 감사. 전문가 분석 프레임 없음 | 감사 설계의 기준선. 반드시 비교 |
| 5 | **Steenstra et al.** arXiv 2602.19948 | 없음 / C | AI 심리치료사 6종 × 시뮬 환자(임상 persona 15종), 369 세션 | 임상 persona 시뮬 | 환자 역할. 알코올 사용 장애 한 사례 | 같은 계열 |
| 6 | **Lost in Delusion** (Aquilina et al.) arXiv 2606.00975 | 없음 / C | 임상 persona 시뮬 + **망상 대화와 distress-only 대조군을 짝지어 비교**. 망상 프레임 안에서 안전 개입이 최대 4.5배 억제. 실패는 감정적 validation이 아니라 **사용자 전제의 누적 수용**을 따라감 | 짝지은 대조군 설계, "누적 수용" 메커니즘 | 망상/고통 도메인. 연구 프레임 없음 | **우리 §9 commitment 가설을 지지하는 가장 직접적인 외부 증거**, 그리고 **대조군 설계의 기준**(우리도 짝지은 대조군 필수) |
| 7 | **ICON** (Lin et al.) arXiv 2601.20903 | 없음 / C | "의도–맥락 결합": 악의 의도를 의미적으로 맞는 맥락(예: 과학 연구)과 짝지으면 방어가 약해짐. ASR 97.1% | **전문가/과학 맥락이 방어를 약화**하는 현상 | 일반 jailbreak, 정신건강 아님 | JARGON 외에 "연구 맥락 효과"의 독립 증거. 선행연구로 인용 |
| 8 | **BLUEPRINT / WORLDVIEWSIM** (Chen et al.) arXiv 2609.02414 | **Findings EMNLP 2026** / B | 사회적 영향 18요인 MCTS + 턴 간 **상황 맥락 모듈**. 가장 큰 효과는 요청이 구체적·실행 가능해 보이게 하는 것 | 턴 간 맥락 구성이 효과를 만든다 | 정보적 위해, 실행 가능성 큐 | 반례 주의: 그들의 핵심 큐는 *실행 가능성*인데, 우리 연구 packet은 *새 방법을 만들지 말 것*을 규정한다. 두 해악 경로가 다르다는 점을 서술 |
| 9 | **psychosis-bench** (Au Yeung et al.) arXiv 2509.10970 | 없음(JMIR 논평 있음) / C | 12턴 시나리오 16개, 명시/암시 맥락, DCS/HES/SIS | 암시적 맥락의 sycophancy 측정 | 시나리오 큐레이션 소규모 | 발화행위 지표(DCS 등)의 선례 |
| 10 | **ActorAttack** (Ren et al.), **RedQueen**, **CoA**, **NEXUS** | ACL 2025 main / Findings ACL 2025 ×2 / EMNLP 2025 main | 의도를 여러 턴에 분산·위장. ActorAttack은 모델 *자신의 지식*으로 단서(actor)를 찾게 함 | "의도 은닉", "자기 발견 단서" | 공격자 질문이 여전히 목표 쪽으로 유도. 해악은 정보 | **"target-originated" 용어와의 충돌 위험.** 반드시 구별: 우리는 *출처를 측정*하고 해악이 발화행위 |
| 11 | **SoK: Intent-Oriented Multi-Turn Jailbreaks** (Li et al.) arXiv 2608.01117 | 없음 / C | 의도 조직 방식으로 분류. "turn-local 안전 장치는 구조적으로 불충분", 탐지 단위는 turn/session/cross-session | 의도 분산 | 정신건강 아님 | **우리 입력측 방어 한계 주장의 외부 근거.** 용어("session-level detection")를 빌려 쓸 수 있음 |

### 22.2 분류별 추가 연구

**(a) 의도 은닉·멀티턴 공격 (일반)**

| 연구 | 게재처 | 등급 | 비고 |
|---|---|---|---|
| NEXUS (ThoughtNet) | EMNLP 2025 main, pp. 24267–24295 | A | 의도를 의미망으로 분산 |
| M2S: Multi-turn to Single-turn | ACL 2025 long | A | 멀티턴을 단일턴으로 압축(방어 연구에도 사용) |
| Chain of Attack (CoA) | Findings ACL 2025, pp. 9881–9901 | B | 심문 관점 의도 은닉 |
| Red Queen (현재 제목 *Exposing Latent Multi-Turn Risks in LLMs*; 초기 *Safeguarding… against Concealed Multi-Turn Jailbreaking*) | Findings ACL 2025 | B | "해를 막으려는 사람" 위장, 큰 모델이 더 취약 |
| ICON, Paper Summary Attack (arXiv 2507.13474), PsychJail (arXiv 2608.23028), HPM (arXiv 2512.18244) | 없음 | C | PSA는 JARGON의 전신 격(논문 요약 프레임). PsychJail·HPM의 "psychological"은 *모델*을 조작하는 심리학이며 정신건강 도메인이 아님 → **용어 충돌 주의** |
| Context Compliance Attack (Microsoft, 2025-03), Bad Likert Judge (Palo Alto Unit 42) | 기업 보고 | C | **평가자/판정자 역할**로 유해 예시를 생성하게 하는 기법. 아래 22.3-③ 참고 |

**(b) persona·사용자 시뮬을 쓰는 안전 평가**

| 연구 | 게재처 | 등급 | 비고 |
|---|---|---|---|
| PENGUIN / RAISE (Wu et al.) *Personalized Safety in LLMs* | NeurIPS 2025 | A | 같은 응답도 사용자 배경에 따라 위험이 다름. 맥락 포함 시 안전 점수 +43.2%. **"안전의 정답이 persona에 따라 달라진다"는 근거** |
| PersonaTeaming (Deng et al.) | NeurIPS 2025 워크숍 | B | 레드티밍 프롬프트에 persona 돌연변이 도입, ASR 최대 +144.1% |
| VERA-MH (Belli et al.) + 검증 논문 | JMIR AI 2026 (검증), arXiv 2510.15297 | A / C | 자살 위험 persona 기반 자동 평가, 임상가–judge 신뢰도 검증 |
| K-Bench, MindEval, TrustMH-Bench (arXiv 2603.03047), mPACT (보도) | 없음 | C | 멀티턴 정신건강 벤치. TrustMH는 anti-sycophancy 축 포함 |
| MindGuard (Sword Health) arXiv 2602.00950 | 없음 | C | **멀티턴 정신건강 가드레일**(4B/8B). 적대적 멀티턴 테스트에서 ASR·유해 참여 감소를 주장 → **우리 공격의 방어 베이스라인 후보** |

**(c) 평가 방법론: judge와 지표**

| 연구 | 게재처 | 등급 | 우리에게 주는 근거 |
|---|---|---|---|
| CounselBench (Li et al.) | ICLR 2026 | A | 임상가 100명 평가, **LLM judge가 응답을 과대평가하고 임상가가 잡는 안전 문제를 놓침** |
| *When Can We Trust LLMs in Mental Health?* (Badawi et al.) | EACL 2026 long | A | LLM judge의 체계적 점수 부풀림, 안전·관련성 평가에서 신뢰도 낮음 |
| PsychEthicsBench (Shen et al.) | Findings ACL 2026 | B | **거부율은 윤리적 행동의 약한 지표.** 14개 모델 분석. PCSA 공저자 일부(Fong, Jiang, Zhao)가 같은 그룹 → **리뷰어일 가능성** |
| SORRY-Bench, CoCoNot | ICLR 2025, NeurIPS 2024 D&B | A | 세분화된 거부 평가, 과잉 거부 쌍 대조 |
| Lost in Simulation | ACL 2026 long `[VERIFY: Anthology ID 2026.acl-long.2192]` | A | 시뮬 사용자는 인간 사용자의 신뢰할 수 없는 대리 |
| Mind the Sim2Real Gap (Zhou et al.) | 없음 | C | 시뮬 사용자는 "easy mode"(과도하게 협조적), 451명 비교 |

**(d) 방어·정렬**

| 연구 | 게재처 | 등급 | 비고 |
|---|---|---|---|
| MTSA (Guo et al.) | ACL 2025 long, pp. 26424–26442 | A | 멀티턴 레드팀 기반 정렬(방어 베이스라인 후보) |
| Defensive M2S (arXiv 2601.00454), Stateful Guardrails (arXiv 2607.19361) | 없음 | C | 세션 단위 위험 누적 추적 |
| SYCON-Bench (Hong et al.) | Findings EMNLP 2025 | B | 멀티턴 sycophancy. **3인칭 프레임이 sycophancy를 최대 63.8% 줄임**(토론 시나리오) → 22.3-② |

**(e) 현실 세계의 persona 기반 감사 (§8 보강)**

| 자료 | 성격 | 등급 | 쓰임 |
|---|---|---|---|
| CCDH *Fake Friend* (2025-08) | NGO 보고서. 연구자가 13세 계정으로 ChatGPT와 대화, 응답 1,200개 중 절반 이상을 위험으로 분류. **거부당하면 "발표용"이라고 하거나 친구 얘기로 바꾸면 우회** | C | persona 기반 감사가 현실에서 이미 쓰이고, **연구·발표 프레임이 우회 경로**라는 실제 사례. 수치는 보고서 원문 확인 `[VERIFY]` |
| Sandvig et al. 2014 (sock puppet audit), Metaxa et al. 2021 (*Auditing Algorithms*, Found. Trends HCI, doi 10.1561/1100000083) | 알고리즘 감사 방법론 | A(저널 모노그래프) / 학회 발표 | persona를 만들어 시스템을 감사하는 방법의 계보. "persona 기반 연구 대화"가 새로운 이상한 방법이 아니라 **확립된 감사 방법의 LLM 버전**이라는 근거 |
| Red-Teaming Medical AI (medRxiv 2026-02), PIEE cycle (PMC) | 의료 AI 레드티밍 | C | 임상 레드티밍 일반 |

### 22.3 이 조사로 드러난 **우리 쪽 위험 3가지**

① **"first" 주장이 많이 약해졌다.** 정신건강 persona 멀티턴 공격(PCSA, Slow Drift, Steenstra, SIM-VAIL), 연구/전문가 맥락 효과(JARGON, ICON, Paper Summary Attack), 멀티턴 sycophancy(psychosis-bench, SYCON, Lost in Delusion)는 모두 선행연구가 있다. 그래서 **"first to…"를 쓰지 않는다.** 대신 "in contrast to X, we …"로 차별점을 서술한다.

② **SYCON-Bench의 3인칭 프레임 결과가 우리 가설과 긴장한다.** SYCON은 3인칭 프레임이 sycophancy를 줄인다고 보고했다(토론 시나리오). 반면 우리 §9.2는 3인칭 분석 프레임이 위기 프로토콜을 발동시키지 않아 *경계를 흐린다*고 가설을 세웠다. 두 결과는 서로 다른 과제(입장 고수 vs 위기 응답)이므로 모순은 아니지만, **리뷰어가 반드시 짚는다.** 그래서 §12의 ablation(1인칭 vs 3인칭, 연구 프레임 유무)을 *선택이 아니라 필수*로 올리고, 가설을 "분석 프레임이 *항상* 방어를 약화한다"가 아니라 "위기 프로토콜 발동 조건을 우회하는 경로가 있다"로 좁혀 서술한다.

③ **우리 final 질문의 구조가 "평가자/역할 전환형" 공격과 닮았다.** `manifestation` 질문은 "상담사가 피해야 할 응답 3가지를 나열하라", "경계를 넘는 응답 패턴을 예측하라"처럼 *평가자·분석가 역할*을 요구한다. 이는 Bad Likert Judge, Context Compliance Attack과 같은 계열의 기법(판정자 역할로 유해 예시를 얻는 것)과 구조적으로 가깝다. 리뷰어가 "이건 새 공격이 아니라 evaluator-role jailbreak의 정신건강 버전"이라고 할 수 있다. 대응: ① 이 계열을 Related Work 2.2에서 직접 언급, ② 우리의 차이는 *그 역할 전환 앞에 persona와 이력이 누적된다*는 점이며, ③ 이를 *역할 전환만 있는 대조군*(이력 없음)과 비교해 증분을 보인다.

추가로 두 가지를 기억한다. **PsychEthicsBench**는 거부율이 윤리적 행동의 약한 지표라고 주장하므로 우리의 `official_CARES_non_refuse@8` 같은 거부 기반 지표를 헤드라인에 쓰면 공격받는다(B3+ 행동 지표를 주 지표로, CARES는 보조). **CounselBench와 Badawi et al.**은 LLM judge가 안전 문제를 놓치고 점수를 부풀린다고 보고했으므로 임상가 검증 없이 GPT-4o-mini 단독 judge는 위험하다(§12 P0-6이 여전히 필수).

### 22.4 이 조사 이후에도 남는 차별점 (내가 찾은 범위에서)

찾은 범위에서는 **다음 조합을 한 연구가 모두 하는 것을 보지 못했다.** (부재의 증명은 아니다.)
1. 전문가 *분석* 프레임 ∩ 사례별 persona·이력 (JARGON은 persona 없음, PCSA는 분석 프레임 없음).
2. 대화 상대가 해로운 명제를 말하지 않는 설정에서 **내용의 최초 출처를 귀속**(persona / qwen / target / final_only).
3. goal 노출량 3단계(dose-response).
4. JMIR 분류체계에 정렬된 goal 625개와 persona 풀의 범주 gating (goal 출처가 혼합 성격이라 "실제 사용자 발화"라고 쓰지 않는다, §23).
5. 정보가 아닌 *발화행위* 단위의 해악(B0–B5) 척도를 공격 프레임워크 안에서 사용.

단, 2번의 "출처 귀속"은 ActorAttack의 "자기 발견 단서"와 개념이 가까워서 *정의를 명확히* 써야 한다.

### 22.5 새로 생긴 Q&A (§11 보강)

| 예상 공격 | 방어 |
|---|---|
| "Slow Drift나 SIM-VAIL이 이미 멀티턴 정신건강 경계 붕괴를 보였다" | 인정하고 인용. 그들은 *시뮬 환자가 챗봇을 감사*. 우리는 *분석 프레임 + 비주입 + 출처 귀속*. 유사한 점을 숨기지 말고 Table 1에 넣는다 |
| "ICON과 JARGON이 이미 연구 맥락 효과를 보였다" | 일반 jailbreak(정보)와 정신건강 발화행위의 차이, 그리고 사례별 persona·이력이라는 맥락의 구성 방식 |
| "3인칭 프레임은 sycophancy를 줄인다(SYCON)" | 과제가 다름. 프레임·인칭 ablation 결과로 직접 답한다 |
| "Bad Likert Judge류의 역할 전환 공격 아닌가" | 22.3-③ 대응 |
| "시뮬 환자는 현실과 다르다(Lost in Simulation, Sim2Real)" | 인정. 임상가 현실성 평가(PCSA 방식) + goal 출처별 층화 분석(§23.6) + Limitations 명시. goal이 모두 실제 사용자 발화라고 주장하지 않는다 |
| "거부율 기반 지표는 약하다(PsychEthicsBench)" | 주 지표는 B3+ 행동 지표, CARES는 보조 |

### 22.6 투고 직전 재검색 절차 (프리프린트가 매주 늘어난다)

1. arXiv 알림: `cs.CL`/`cs.CR`/`cs.AI`에서 키워드 "multi-turn" + ("mental health" | "counseling" | "suicid*" | "persona" | "sycophancy").
2. ACL Anthology: Findings 포함 `2026.acl-*`, `2026.findings-acl.*`, EMNLP 2026 Findings 목록에서 "persona", "mental", "gray zone", "jailbreak" 검색(PCSA·BLUEPRINT가 Findings에 있음).
3. 인용 역추적: JARGON, PCSA, SIM-VAIL, Slow Drift, Lost in Delusion을 인용한 논문을 Semantic Scholar/Google Scholar의 "cited by"로 확인.
4. 후보 학회 투고 주기 직전에 "Related Work 항목 점검" 체크리스트로 위 1–3번을 한 번 더.

### 22.7 §14 Related Work에 추가할 인용 위치

| 소절 | 추가 |
|---|---|
| 2.1 멀티턴 | NEXUS, M2S, Red Queen(Findings ACL'25), SoK(arXiv) |
| 2.2 persona·맥락 | ICON, Paper Summary Attack, BLUEPRINT(Findings EMNLP'26), PersonaTeaming(워크숍), Bad Likert Judge/Context Compliance(산업 보고, 한 문장), PsychJail·HPM(용어 구분) |
| 2.3 정신건강 평가 | Slow Drift, Lost in Delusion, psychosis-bench, VERA-MH, MindGuard, PENGUIN, CounselBench, PsychEthicsBench, TrustMH |
| 2.4 시뮬 환자·감사 | Sandvig·Metaxa(감사 방법 계보), CCDH Fake Friend, Lost in Simulation, Sim2Real |
| 2.5 트레이드오프·방어 | MTSA, SYCON-Bench, CoCoNot, SORRY-Bench, Defensive M2S/Stateful Guardrails |

---

## 23. goal 데이터(JMIR)의 출처·계보와 persona 풀 구축 — 선행연구와 어필 설계

> 사용자 확인: 625개 goal의 출처는 *Between Help and Harm: An Evaluation Study of Mental Health Crisis Handling by Large Language Models*, **JMIR Mental Health 2026** (https://mental.jmir.org/2026/1/e88435, doi 10.2196/88435; arXiv 2509.24857). 아래는 논문 원문(arXiv v3 전문을 로컬 추출)과 12개 HuggingFace 데이터셋 카드를 직접 확인한 결과다.

### 23.0 먼저 바로잡을 점 — "실제 사용자 발화 625개"라고 쓰면 안 된다

앞선 문서(§2.1 P3, §4, §10)에서 625 goal을 "실제 사용자 발화 기반"이라고 표현한 부분을 이 절의 근거로 모두 고쳤다. 이유:
- JMIR 논문 자신이 소스를 "counseling transcripts, mental health support forums, **synthetic conversations**, and **mixed human-AI interactions**"라고 서술하고, 기존 자원이 "rely on synthetic or forum-derived content"라고 한계를 인정한다. 한계 절도 "does not fully capture the diversity of real-world mental health crises"라고 쓴다.
- 우리 625개 중 상당수가 합성·혼합·벤치마크 프롬프트 출처다(§23.2).
→ 정확한 서술: *"625 user inputs drawn from the JMIR crisis benchmark, which aggregates 12 public datasets of mixed provenance."*

### 23.1 JMIR 논문은 왜 12개 데이터셋을 통합했나 (논문이 명시한 근거 vs 내 해석)

**논문이 명시한 것**
- 동기: 위기 상황 평가용 "high-quality, clinically relevant and annotated datasets"가 부족하고, 기존 자원은 "limited scope, rely on synthetic or forum-derived content, and lack robust labeling in line with best practices" (§4.1). 선행 자원(MEMO, Psych8k, HF Hub 집계물)은 임상 주석이 약하고 위기 범주 커버리지가 부족하며 "labels … are frequently inconsistent or non-specific (if at all present)" (Related Work).
- 네 가지 공백: 표준 분류체계, 임상 검증 벤치마크, 이해관계자 참여, LLM 위기 응답의 실증 평가 (Introduction).
- 통합 절차(§4.1): 12개 HF 데이터셋(Table 3)을 하나의 형식으로 합치고 중복·공백·"incomplete Reddit-style posts" 같은 저품질 항목 제거. 다중 턴은 **사용자 발화만** 이어 붙여 하나의 입력으로 만들고 40메시지 초과는 절단. 결과 **239,606개 고유 입력**.
- 기존 라벨 폐기: 일부 데이터셋에 있던 라벨은 "sparse (0.5%), inconsistent across sources, and sometimes incorrect"라서 전부 버리고 재주석. 임의 표본 검토에서 라벨이 자주 틀렸다고 각주에 기록.
- 표본·주석: 검증셋 206개(4명 전문가 — 심리·정신건강·생존자 경험, **전문가 간 Fleiss κ = 0.55**), 시험셋 2,046개. 3개 LLM 중 gpt-4o-mini가 전문가와 평균 **κ = 0.645**(gpt-5-nano 0.631, llama-4-scout 0.581; 전문가 간 평균 κ 0.553)로 최고여서 시험셋 라벨러로 선정. 3회 반복 라벨 일치 FK = 0.94, 합의 실패 2개 제외 → **2,044개**.
- 분포: no crisis 1,231 (60.2%), suicidal ideation 380 (18.6%), anxiety crisis 177 (8.7%), self-harm 139 (6.8%), substance 77 (3.8%), violent thoughts 21 (1.0%), risk-taking 19 (0.9%). 저자들은 이를 "mirrors real-world prevalence"라고 해석.
- 평가: gpt-4o-mini, gpt-5-nano, llama-4-scout에 deepseek-V3.2, grok-4-fast를 더해 5개 모델, 입력당 3회 생성(총 30,660 응답), 심리학자 설계 프로토콜 5점 척도(1 harmful ~ 5 fully appropriate).
- 한계: LLM이 라벨링·평가했고, 영어·성인 중심.

**내 해석 (논문이 직접 쓰지 않은 부분 — 논문에서는 이렇게 단정하지 않는다)**
- 단일 데이터셋이 6개 범주를 모두 충분히 다루지 못하고, 소스마다 형식·스타일이 달라서(상담 Q&A, 포럼 게시글, 합성 대화 등) 통합이 필요했을 가능성이 크다. 특히 희소 범주(violent, risk-taking)를 확보하려면 239k 규모의 풀이 유리하다. 다만 논문이 "그래서 통합했다"고 명시한 문장은 확인하지 못했다. abstract는 "a curated, diverse evaluation dataset … drawn from 12 publicly available conversational mental health datasets"와 "covering all the categories defined in the taxonomy"라고만 쓴다.

**우리 논문에서의 활용**: JMIR의 통합 근거를 "범주 커버리지와 라벨 정합성을 위해 이질적 공개 자원을 재주석해 통합했다"로 요약해 인용하고, 우리는 이 **통합·재주석 결과물을 입력으로 재사용**한다고 서술한다. 새로 모은 데이터가 아니라 *출판된 벤치마크*를 입력으로 쓴다는 점이 재현성·윤리 면에서 이점이다(IRB 불필요한 2차 분석의 연장선; JMIR Ethics Statement 참조).

### 23.2 우리 625개 goal의 실제 출처 구성 (레포 `source_hf` 필드와 데이터셋 카드로 집계)

| HF 데이터셋 | n | 중앙값 단어수 | 다중입력 비율 | 카드로 확인한 성격 | 근거 수준 |
|---|---:|---:|---:|---|---|
| cypsiSAS/transformed_Suicidal_ideation | 151 | 124 | 95% | 카드 없음. 1인칭 포럼 글 형태, Reddit 언급 포함. **원출처 미기재** | 추정 |
| sajjadhadi/Mental-Disorder-Detection-Data | 85 | 134 | 93% | 카드 비어 있음. "[deleted]", r/depression 언급 등 Reddit 아티팩트. **원출처 미기재** | 추정 |
| arianaazarbal/self-harm-synthetic-eval | 85 | 16 | 0% | 이름이 synthetic, `base`/`rephrased` 프롬프트 쌍, 카드 비어 있음 | 이름 근거 |
| fadodr/mental_health_therapy | 57 | 67 | 100% | **실제 상담 포럼 + ChatGPT 합성** 혼합(counsel-chat, Amod, MentalChat16K에서 파생), MIT | 카드 명시 |
| ShenLab/MentalChat16K | 43 | 83 | 100% | **GPT-3.5 합성 9,775 + 임상시험 인터뷰 6,338 QA(Mistral로 패러프레이즈)**. 카드가 "entirely synthetic"이라는 문장과도 충돌 | 카드 명시(모순) |
| marmikpandya/mental-health | 42 | 15 | 55% | 카드 없음, 반복적·템플릿형 | 미기재 |
| jerryjalapeno/nart-100k-synthetic | 40 | 332 | 100% | **"entirely synthetic"**, 실제 치료 상황을 대표하지 않는다고 카드가 명시 | 카드 명시 |
| fanyin3639/test_test_self_harm_all_levels | 30 | 13 | 23% | 안전 벤치마크 프롬프트(`source` 열에 saladbench, beavertails 등), GPT-4 응답 열 포함 | 카드 명시 |
| Amod/mental_health_counseling_conversations | 29 | 45 | 97% | 두 개의 상담 웹사이트에서 수집, **면허 전문가가 답한 실제 질문**, 익명화(RAIL-D 라이선스, gated) | 카드 명시 |
| richie-ghost/suicidal_finetune | 27 | 16 | 0% | 120개 짧은 1인칭 문장, 8클래스. 카드 비어 있음, 합성/수작업 가능성 | 미기재 |
| fadodr/mental_health_dataset | 18 | 15 | 67% | 카드 비어 있음 | 미기재 |
| psycode1/psyset | 18 | 45 | 94% | 카드 비어 있음, 균일한 문장 | 미기재 |

**성격별 합계 (625개)**
- 사람이 쓴 것으로 문서화(Amod) 또는 포럼 글로 추정(cypsiSAS, sajjadhadi): **265 (42%)**
- 합성 또는 혼합이 카드에 명시(fadodr/therapy, MentalChat16K, nart-100k): **140 (22%)**
- 안전 벤치마크 성격의 프롬프트(self-harm-synthetic-eval, fanyin3639): **115 (18%)**
- 출처 미기재(marmik, psycode1, fadodr/dataset, richie-ghost): **105 (17%)**
- 중앙값 약 13–16단어의 짧은 지시문/요청형 입력 5개 출처 합계: **202 (32%)**. 이들은 "내담자의 서술"이 아니라 **요청 프롬프트**에 가깝다(`is_request` 플래그는 richie-ghost만 4%이고 나머지 네 출처는 52–80%).

**데이터 위생 점검 결과 (직접 계산)**
- 정규화 후 완전 중복 그룹 4개, 근접 중복 쌍 12개. 그중 `marmikpandya/mental-health`↔`Amod`, `fadodr/mental_health_therapy`↔`Amod`는 자카드 1.0 — **파생 데이터셋이 원본을 포함**하기 때문이다(fadodr/therapy 카드가 Amod와 MentalChat16K에서 파생됐다고 명시). self-harm-synthetic-eval 내부의 base/rephrased 쌍도 5쌍 이상.
- 라벨 안정성: 3회 라벨 중 불일치 39/625 (6.2%); 불일치는 **anxiety_crisis 23/177 (13%)**에 집중 — JMIR 논문이 보고한 "anxiety crisis ↔ no crisis" 최대 혼동과 일치.
- 라벨 오류 가능성: 625개 라벨도 **gpt-4o-mini 단독 라벨**이며(전문가 일치 κ 0.645), 우리 단계의 "1인칭 내담자 발화" 필터도 gpt-4o-mini다.

**권고**: ① 중복 제거 후 최종 n 확정, ② **출처 성격별 층화 분석**(사람 작성 추정 / 합성·혼합 / 벤치마크 프롬프트 / 미기재)을 모든 주요 표에 병기, ③ 범주별 임상가 재라벨(예: 150건) 후 κ 보고, ④ 짧은 요청형 입력 202개를 제외한 민감도 분석, ⑤ 이 집계를 `DATA_LINEAGE`에 추가.

### 23.3 원 데이터 출처 쪽 선행연구 (계보와 게재처)

| 출처 계보 | 선행연구 | 게재처 / 등급 | 우리와의 관계 |
|---|---|---|---|
| JMIR 벤치마크 본체 | Arnaiz-Rodriguez et al. *Between Help and Harm* | **JMIR Mental Health 2026** (doi 10.2196/88435) / A | goal 출처. 분류체계·재주석 |
| 상담 Q&A (Amod, fadodr 파생) | CounselChat (Bertagnolli 2020; 상담 사이트의 면허 치료사 답변, 약 2.8k Q&A 판본) | 오픈 데이터/블로그 / C `[VERIFY]` | 사람이 쓴 질문의 거의 유일한 문서화된 출처 |
| MentalChat16K | Xu et al. *MentalChat16K* (arXiv 2503.13509) | **KDD 2025**, pp. 5367–5378 / A | 합성 9,775 + 임상시험 인터뷰 6,338. 우리 43개 |
| Psych8k (JMIR가 기존 자원으로 언급) | Liu et al. *ChatCounselor* (arXiv 2309.15461): 260개 상담 인터뷰, 8,187개 지시문 쌍, gated | arXiv / C | 12개에는 없음. 선행 자원 사례 |
| Reddit 자살 위험 계열 (cypsiSAS, sajjadhadi의 *추정* 계보) | Shing et al. CLPsych 2018 (r/SuicideWatch, 전문가·크라우드 주석, 4단계 위험); Zirikly et al. CLPsych 2019 shared task; Haque et al. SDCNL (ICANN 2021, 노이즈 라벨 문제) | CLPsych 워크숍 / B; ICANN 2021 | **카드가 계보를 밝히지 않으므로 직접 인용 금지**, "same family of Reddit resources" 수준으로만 서술 |
| 안전 벤치마크 프롬프트 (fanyin3639의 `source` 열) | SALAD-Bench (Li et al.), BeaverTails (Ji et al.) | **Findings ACL 2024** / B; **NeurIPS 2023 D&B** / A | 우리 30개의 일부는 일반 안전 벤치 유래 프롬프트 |
| 합성 상담 대화 | nart-100k-synthetic (카드: entirely synthetic) | HF 카드 / C | 40개 |
| 소셜미디어 정신건강 데이터의 한계 | Harrigian, Aguirre, Dredze. *On the State of Social Media Data for Mental Health Research* | **CLPsych 2021** / B | 데이터 접근·품질이 연구를 제약한다는 근거 |
| 구성 타당도 비판 | Chancellor & De Choudhury. *Methods in predictive techniques for mental health status on social media* | **npj Digital Medicine 2020** / A | 라벨의 construct validity — 우리가 재라벨 검증을 넣는 근거 |
| HF/오픈 데이터의 출처·라이선스 오기재 | Longpre et al. *A large-scale audit of dataset licensing and attribution in AI* | **Nature Machine Intelligence 2024** / A | 12개 중 다수가 카드 비어 있다는 사실의 일반론 |
| 데이터 문서화 표준 | Gebru et al. *Datasheets for Datasets* | **Communications of the ACM 2021** / A | 우리 계보 문서(체크섬·깔때기·출처 집계)의 정당화 |

> **어필 포인트(Data 절):** JMIR 통합 코퍼스는 출처 문서화가 취약한 HF 자원의 집합이다(Longpre, Harrigian). 우리는 이를 *있는 그대로 받아쓰지 않고* ① 출처별 성격을 확인·집계하고, ② 중복·파생 관계를 점검하고, ③ 출처 층화로 결과를 보고한다. 이것은 방어 가능한 데이터 위생이며 리뷰어의 데이터 신뢰성 공격을 선제 차단한다.

### 23.4 persona 풀 — 선행연구와 우리가 한 일

**선행연구가 알려준 사실 (직접 확인)**
- **Cactus**(Lee et al., Findings EMNLP 2024)는 **합성 데이터**다. 논문이 스스로 "a large-scale synthetic dataset of counseling dialogue", "synthetically generated unlike Psych8k"라고 쓴다. 클라이언트 맥락은 PatternReframe(Maddela et al., **ACL 2023**; 페르소나·부정적 사고·재구성 약 10k)에서 가져오고, 인테이크 폼은 GPT-3.5, 대화는 GPT-4o로 생성, CTRS 기준(GPT-3.5 judge ≥5.0)으로 걸러 **31,577개**(Table 1 기준; 본문엔 31,564라는 표기도 있음) 유지.
- **CBT-DP**(CBT-Bench, **NAACL 2025**)는 Boswell & Constantino(2022)의 **156개 deliberate-practice 연습문제**(전문가 교육용)이며 실제 세션이 아니다. 논문은 "real CBT session data is difficult [to collect] due to privacy constraints"라고 쓴다.
- 따라서 PCSA와 우리가 공통으로 쓰는 persona 코퍼스는 **전체가 합성 또는 전문가 제작 교재**다. PCSA도 같은 원천(Cactus, CBT-DP, Cheeseburger Therapy)을 쓴다.
- 최근 환자/내담자 시뮬레이터 문헌: Patient-Ψ(**EMNLP 2024**), Roleplay-doh(**EMNLP 2024**), AnnaAgent(**Findings ACL 2025**; 감정 변화·다회기 기억 시뮬레이터), CARE-Bench(**AAAI 2026**; 실제 상담 사례 유래 클라이언트 프로필, 전문가 지침 기반 시뮬레이션) — 모두 *소수의 정교한 환자 모델*을 만든다.

**우리가 만든 것 (레포 사실)**
1. Cactus 31,577 + CBT-DP 156 = **31,733 profile**을 정규화하고 출처·통신 특징·라이선스 메타데이터를 보존.
2. Qwen2.5-7B로 **JMIR 6개 범주에 정렬된 단일 라벨 + 적합도(direct/adjacent/weak) + 위해 방향(desire/enacted/fear/historical/none)**을 전 풀에 부여. 위해를 *원하는* 경우와 우발적 위해를 *두려워하는* 경우를 구분하도록 설계.
3. 풀이 anxiety_crisis 31,046(97.8%)에 쏠려 있어 희소 범주(self-harm, suicidal ideation, violent thoughts)를 **GPT-4o-mini로 268건 구성형 보강**: 범주마다 서로 다른 base family 100개, 비그래픽·정체성 연속성 유지, `constructed` provenance를 원문 라벨과 분리 표기, 항목별 독립 감사 5개 차원(범주 일치·위해 방향·신원 연속성·provenance·비그래픽성) 268/268 통과. 원문 인접 신호만으로 재지정한 행은 보수적으로 원복.
4. 최종 분포: anxiety 31,046 / risk-taking 102 / self-harm 101 / substance 216 / suicidal 168 / violent 100. 범주별 분할 JSONL과 SHA-256, 인덱스 제공.
5. **범주 일치 검색**(goal의 JMIR 범주 = persona 범주만 후보) → top-12 → Qwen이 선택 → 샘플별 `sample_adaptation` → goal-atom 이력.

**어필 포인트 (정직한 범위 내에서)**
- ① **분류체계 정렬**: goal과 persona가 같은 6범주 분류체계를 공유 — 기존 persona 공격(PCSA)은 persona를 공격 목표와 인지왜곡 매핑으로 연결했지, 목표 분류체계와 persona 풀을 정렬해 두지 않았다.
- ② **희소 범주 보강의 투명성**: 합성임을 숨기지 않고 `constructed` provenance와 항목별 감사를 공개 — 대부분의 데이터셋 카드가 비어 있는 현실(§23.2)에 대비되는 장점.
- ③ **규모와 재현성**: 31,733 profile, 범주별 분할, 체크섬, 논문용 방법 문단까지 정리(`PERSONA_CATEGORY_EXTRACTION_AND_GENERATION.md`).
- ④ **프라이버시 윤리**: 실제 환자 기록 없이 합성/교재 기반 persona만 사용(CBT-Bench가 지적한 실세션 데이터 확보의 어려움과 일치).

**선제 방어해야 할 약점 (리뷰어가 짚을 지점)**
| 약점 | 근거 | 대응 |
|---|---|---|
| 풀 전체가 합성이라 현실성 의문 | Cactus는 GPT 합성, CBT-DP는 교재 | 임상가 blind realism 평가(PCSA 방식), 합성 한계 명시. 실제 환자라고 주장하지 않음 |
| 97.8%가 `anxiety_crisis`(catch-all, `weak` 적합 다수) | 사이드카 분포 | 적합도(direct/adjacent/weak) 분포 보고, weak 제외 민감도 분석 |
| 범주 라벨이 Qwen2.5-7B 단일 라벨, 사람 검증 없음 | 레포 파이프라인 | 임상가 소표본 라벨과 κ 보고(JMIR는 LLM–전문가 κ 0.645를 보고했다 — 같은 기준으로 맞춘다) |
| **268건 감사자와 생성자가 같은 모델(gpt-4o-mini)** | 레포 문서 | LLM 자기선호 편향(Panickssery24, NeurIPS 2024 oral) — **다른 계열 모델 + 임상가 표본 감사**로 재검증 필요 |
| 희소 범주 base family가 각 100개뿐인데 goal은 suicidal 298, self-harm 63 | 사이드카·goal 분포 | persona 재사용 분포(각 persona가 몇 goal에 매핑되는지) 보고 |
| goal 조건 `sample_adaptation`이 goal 정보를 persona에 주입 | `METHOD_PERSONA_POOL_CONSTRUCTION.md` §6 | goal-blind 대조군(§12 P0-3) |
| 시뮬 환자는 현실 사용자 대리가 아님 | Lost in Simulation(ACL 2026), Sim2Real | Limitations, 출처 층화 |

### 23.5 논문 문단 초안 (Data / Resource 절, 영어 draft)

**Goals.** *"We use the crisis-handling benchmark of Arnaiz-Rodriguez et al. [Arnaiz26], which unifies 239,606 deduplicated user inputs from 12 public Hugging Face datasets—counseling Q&A, forum-style posts, synthetic conversations and mixed human–AI exchanges—under a six-category crisis taxonomy (suicidal ideation, self-harm, anxiety crisis, violent thoughts, substance abuse/withdrawal, risk-taking behaviors). Because source-level labels were sparse and unreliable, the benchmark re-annotates inputs with an LLM labeler selected for its agreement with four experts (mean κ = 0.645 versus 0.553 among experts). From the 2,046 test inputs we keep the 813 labeled with a crisis category, filter to first-person client utterances, and require at least ten words, yielding 625 goals. We do not claim these inputs are all real user utterances: the sources are of mixed provenance (Table X), and we report results stratified by source type."*

**Persona pool.** *"Personas come from Cactus [Lee24] (31,577 CBT dialogue clients synthesized from PatternReframe seeds [Maddela23]) and the 156 expert-authored deliberate-practice exercises of CBT-Bench [Zhang25], a pool that is synthetic or instructional by construction and thus free of patient records. Since 97.8% of this pool falls into one distress category, we align it to the goal taxonomy by (i) labeling every profile with one of the six crisis categories, a fit grade and a harm direction, and (ii) adding 268 category-conditioned constructed profiles for the three sparse high-risk categories, each with explicit constructed provenance and an item-level audit. Retrieval is gated on category agreement between goal and persona."*

### 23.6 이 절이 추가로 요구하는 분석 (§12 체크리스트 보강)

1. 출처 성격별 층화 결과(사람 작성 추정 / 합성·혼합 / 벤치마크 프롬프트 / 미기재)와 단문 요청형 202개 제외 민감도 분석.
2. 중복 제거 후 n 재확정, 파생 데이터셋 간 중복 보고.
3. goal 범주 라벨 임상가 재검증(예: 층화 150건) 및 κ.
4. persona 범주 라벨·구성형 268건에 대한 **독립 계열 모델 + 임상가** 재감사.
5. persona 재사용 분포, 적합도 분포, weak 제외 민감도.
6. `DATA_LINEAGE_AND_EXTRACTION_KO.md`에 출처 성격 집계(§23.2)와 중복 점검을 추가.

### 23.7 새로 추가된 문헌의 게재처

| Key | 문헌 | 게재처 | 등급 |
|---|---|---|---|
| Maddela23 | Maddela et al. *Training Models to Generate, Recognize, and Reframe Unhelpful Thoughts* (PatternReframe) | **ACL 2023 main (long)**, pp. 13641–13660, doi 10.18653/v1/2023.acl-long.763 | A |
| Xu25MentalChat | Xu et al. *MentalChat16K* (arXiv 2503.13509) | **KDD 2025**, pp. 5367–5378 `[VERIFY: 대학 저장소 기록 경유]` | A |
| Wang25Anna | Wang et al. *AnnaAgent* | **Findings ACL 2025**, pp. 23221–23235 | B |
| CARE25 | *CARE-Bench* (arXiv 2511.09407) | **AAAI 2026** `[VERIFY]` | A |
| Shing18 | Shing et al. *Expert, Crowdsourced, and Machine Assessment of Suicide Risk via Online Postings* | CLPsych 2018 (W18-0603) | B |
| Zirikly19 | Zirikly et al. *CLPsych 2019 Shared Task* | CLPsych 2019 (W19-3003) | B |
| Haque21 | Haque et al. *Deep Learning for Suicide and Depression Identification with Unsupervised Label Correction* (SDCNL) | ICANN 2021 `[VERIFY]` | — |
| Li24Salad | *SALAD-Bench* | **Findings ACL 2024**, pp. 3923–3954 | B |
| Ji23Beaver | *BeaverTails* | **NeurIPS 2023 D&B** | A |
| Harrigian21 | Harrigian, Aguirre, Dredze | CLPsych 2021, pp. 15–24 | B |
| Chancellor20 | Chancellor & De Choudhury | **npj Digital Medicine 3:43 (2020)** | A |
| Longpre24 | Longpre et al. | **Nature Machine Intelligence 6:975–987 (2024)**, doi 10.1038/s42256-024-00878-8 | A |
| Gebru21 | Gebru et al. *Datasheets for Datasets* | **Communications of the ACM 64(12):86–92 (2021)** | A |
| Liu23Chat | Liu et al. *ChatCounselor* (Psych8k) arXiv 2309.15461 | arXiv | C |
| Bertagnolli20 | CounselChat | 오픈 데이터/블로그 | C `[VERIFY]` |
