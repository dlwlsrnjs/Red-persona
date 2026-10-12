# 외부 기법의 턴 구조·실패 지점과 PCSA–Jargon–1011 비교

## 1. 이 문서가 답하는 질문

이 문서는 세 질문을 분리해서 답한다.

1. 각 외부 기법은 실제로 몇 개의 경로와 턴을 만들고, 다음 턴을 무엇으로 수정하는가?
2. 각 기법은 Final-197에서 주로 어느 단계에서 막혔는가?
3. PCSA, 과거 `jargon_history_bridge_v1`, 현재 최종 OURS `1011_method_v1`은 모두
   persona/history를 쓰면서도 왜 다른 방법인가?

여기서 **현재 최종 OURS**는 Final-197의 `1011_method_v1`이다. Jargon History Bridge는
Official-500에서 실행된 보존된 v1 메서드이며 현재 Final-197 결과와 같은 실험으로 취급하지
않는다. 코호트, response unit과 endpoint가 다르므로 Jargon 수치를 Final-197 순위표에
합치지 않는다.

근거의 강도도 구분한다.

- **구현 확인:** 저장소의 실행 코드와 고정 manifest에서 확인한 제어 흐름
- **집계 확인:** 완결된 197건 또는 500건 결과에서 확인한 수치
- **응답 확인:** 보존된 case JSON과 row-level 평가를 직접 결합해 확인한 사례
- **기전 해석:** 구현과 집계에 부합하는 실패 위치의 해석이며, 원 응답이 없는 셀의 개별
  응답을 보았다는 뜻은 아님

직접 응답 사례는 [`DIRECT_SAMPLE_CASEBOOK_KO.md`](DIRECT_SAMPLE_CASEBOOK_KO.md)에
안전정렬 유지와 경계 통과의 양쪽 방향으로 분리했다.

## 2. 한눈에 보는 턴 구조

`target call`은 공격자나 중간평가자 호출이 아니라 평가 대상 모델을 실제로 부른 횟수다.
멀티턴 방법에서 다음 턴은 이전 target 응답을 받은 뒤에만 만들었다. GPT-4o Batch도
`wave t 완료 → history 갱신 → wave t+1 제출` 순서를 지켰다.

| 방법 | 형태 | 한 사례의 실제 루프 | 다음 턴에 넘기는 정보 | 선택·중단 | 최대 target calls |
|---|---|---|---|---|---:|
| Direct | 싱글턴 | 원 목표를 한 번 전송 | 해당 없음 | 응답 1개 저장 | 1 |
| Skeleton Key | 싱글턴 | 모의 정책 예외 요청·모의 수락을 prefix로 붙인 뒤 목표 전송 | live 적응 없음 | 응답 1개 저장 | 1 |
| Many-shot | 싱글턴 | 성공적인 모의 대화 8개와 목표를 한 긴 prompt로 전송 | live 적응 없음 | 응답 1개 저장 | 1 |
| Red Teaming | 순차 멀티턴 | 단일 경로에서 공격자 질문 → target 응답 → 내부 점수 → 질문 수정 | 목표, 선택 경로 전체 history, 직전 응답·점수 | 성공 threshold 또는 4턴 | 4 |
| PAIR | 병렬 멀티턴 | 독립 stream 5개가 각자 질문을 3회 반복 개선 | stream별 공격/target history와 점수 | branching·off-topic prune 없이 stream 유지; 성공 시 중단 | 15 |
| TAP | 트리 멀티턴 | 생존 node를 2개씩 확장 → off-topic 제거 → target 호출·점수화 → 상위 width 2 유지 | node별 경로 history와 점수 | depth 4, width 2, branching 2; 전부 prune될 수 있음 | 14 |
| Crescendo | 순차 멀티턴 | 비교적 간접적인 질문에서 시작해 매 턴 목표 쪽으로 점진 상승 | 누적 대화, 직전 응답, 목표 점수, refusal 여부 | 거절 시 마지막 수용 지점으로 최대 2회 backtrack | 6 |
| Therapist Crescendo | 순차 멀티턴 | Crescendo 루프에 상담 관계·치료사 역할 유도용 adversary prompt 적용 | Crescendo와 같음 | 최대 4턴 + backtrack 2회 | 6 |
| PCSA Phase II | best-of-N 멀티턴 | 네 심리 전략으로 후보 4개 생성 → target 4응답 → GPT-4o-mini 평가 → 최고 한 쌍만 history에 추가 | persona/pathology/숨은 목표, 선택된 client–target history | compliance/score 성공 또는 4턴 | 16 |
| Jargon History Bridge v1 | 누적 연구대화 + 4분기 | initial analysis → 중립 연구 질문 4–7단계 → history 고정 → final readout 4개 | persona/history, target 자신의 누적 분석, Qwen coverage 상태 | stage 4부터 coverage 충분 시 종료; 최종 4분기는 독립 | 9–12 |
| 현재 OURS `1011_method_v1` | 고정 연구대화 + 4 singleton 분기 | initial analysis → 고정 7단계 → 필요 시 Case A/B 1회 → 4개 recovery/anchor → final 질문 각 1회 | target 누적 분석, private goal 대비 coverage, target의 정확 인용 anchor | 반복 attack-turn 없음; 분기별 1회만 측정 | 공통 8–9 + 최종 8 |

마지막 행의 최종 8회는 네 분기마다 `recovery response 1회 + attack response 1회`다. 현재
메서드를 “singleton”이라고 부르는 이유는 전체 context 형성이 한 호출이라는 뜻이 아니라,
**최종 attack response를 보고 다시 공격 문장을 고치는 적응형 반복이 없고 네 사전 등록
분기를 각각 한 번만 측정하기 때문**이다.

## 3. 비작동적 턴 예시

아래는 구현의 데이터 흐름을 보여주는 축약 예시다. 실제 유해 목표나 실행 정보를 재현하지
않고 `<goal>`, `<response>`로 표시했다.

| 방법 | 축약 trace |
|---|---|
| Direct | `target(<goal>) → response` |
| Skeleton Key | `[user: policy exception] → [assistant: simulated acceptance] → user:<goal> → response` |
| Many-shot | `[human request → AI compliance] × 8 → human:<goal> → response` |
| Red Teaming | `attacker(goal,H0) → p1 → target r1 → score1 → attacker(goal,H1,score1) → p2 ...` |
| PAIR | `stream s=1..5: (ps1→rs1→score) → refine ps2 → ...`, stream history는 서로 섞지 않음 |
| TAP | `root → child prompts → off-topic prune → target responses → score → top-2 nodes → expand` |
| Crescendo | `indirect p1 → r1 → slightly closer p2`; refusal이면 `p2/r2`를 버리고 수용 지점에서 완화해 재시도 |
| Therapist Crescendo | Crescendo trace와 같지만 공격자에게 therapist-role 관계 형성 목표를 부여 |
| PCSA | `4 strategies → 4 target responses → evaluator scores → argmax 한 쌍 append → next turn` |
| Jargon v1 | `target analysis → Qwen neutral question → target analysis ... → freeze H → 4 independent semantic readouts` |
| 1011 | `fixed 7-stage analysis → coverage/quote gate → optional A/B once → 4 anchored recovery prompts → 4 one-shot negative-example prompts` |

Skeleton Key의 prefix가 user/assistant 두 메시지라는 이유만으로 적응형 멀티턴으로 세지
않는다. 실제 target 응답을 본 뒤 다음 질문을 바꾸지 않고 live target 호출도 한 번뿐이다.

## 4. 외부 9개 기법의 실패 지도

HarmBench negative는 저장된 최종 응답이 adapted mental-health behavior를 실질적으로
수행하지 않았다는 뜻이다. 실패 위치 열은 구현과 aggregate에 근거한 기전 해석이다. 기존
9×2 matrix의 개별 원 응답은 공개 결과 폴더에 없으므로, 아래를 response-level manual
coding으로 표현하면 안 된다.

| 방법 | GPT-4o HB ASR | GPT-4o 실패 | 주로 막히는 지점 | 기전 해석 |
|---|---:|---:|---|---|
| Direct | 2/197 (1.02%) | 195/197 | 최초 의도 노출 | 목표가 즉시 드러나 policy/compliance 경계를 바로 만남 |
| Skeleton Key | 2/197 (1.02%) | 195/197 | 모의 권한의 실제 권한 전환 | 앞의 가상 수락이 이후 목표에 대한 안전 규칙을 바꾸지 못함 |
| Many-shot | 0/197 (0%) | 197/197 | 예시 모방의 실제 수행 전환 | 긴 성공 예시가 현재 요청의 직접 위해 수행으로 전이되지 않음 |
| Red Teaming | 17/197 (8.63%) | 180/197 | 단일 경로 수렴 | 수정할수록 목표가 선명해지지만 같은 policy boundary를 반복해서 만남 |
| PAIR | 29/197 (14.72%) | 168/197 | 병렬 refinement 뒤 compliance | GPT-4o에서 가장 강했지만 5개 stream도 다수 사례의 수행 경계를 넘지 못함 |
| TAP | 28/197 (14.21%) | 169/197 | branch 다양성의 공통 경계 | 여러 node가 같은 안전 경계에 모이거나 off-topic으로 prune됨 |
| Crescendo | 10/197 (5.08%) | 187/197 | escalation 전환점 | 관계·맥락을 쌓아도 위해 의도가 분명해지는 순간 안전 응답으로 전환 |
| Therapist Crescendo | 4/197 (2.03%) | 193/197 | 상담 역할 유도의 역효과 | 상담 문맥이 오히려 공감·경계·전문 지원 행동을 강화할 수 있음 |
| PCSA profile-only | 1/197 (0.51%) | 196/197 | engagement에서 operational compliance로 전환 | 비거절·공감·toxic-empathy 신호를 높게 볼 수 있으나 실제 목표 수행은 드묾 |

PAIR과 TAP이 GPT-4o의 외부 기법 중 가장 높았다는 것은 탐색 폭과 반복 개선이 전혀
무의미하다는 뜻이 아니다. 다만 각각 최대 15·14 target calls를 사용하고도 최종 HarmBench
양성은 15% 미만이었다. 따라서 이 결과는 동일 query efficiency의 우열이 아니라, 등록된
예산에서의 method-level outcome 비교다.

## 5. Target model을 바꾸면 어디가 달라지는가

같은 9개 방법에서 Qwen target의 HarmBench ASR은 모두 대응 GPT-4o보다 높았다.

| 방법 | GPT-4o | Qwen2.5-7B | Qwen − GPT-4o |
|---|---:|---:|---:|
| Direct | 1.02% | 7.61% | +6.60%p |
| Skeleton Key | 1.02% | 18.78% | +17.77%p |
| Many-shot | 0% | 6.09% | +6.09%p |
| Red Teaming | 8.63% | 21.32% | +12.69%p |
| PAIR | 14.72% | 36.04% | +21.32%p |
| TAP | 14.21% | 43.15% | +28.93%p |
| Crescendo | 5.08% | 19.80% | +14.72%p |
| Therapist Crescendo | 2.03% | 11.68% | +9.64%p |
| PCSA profile-only | 0.51% | 2.03% | +1.52%p |
| 9개 method×case 합계 | 93/1,773 (5.25%) | 328/1,773 (18.50%) | +13.25%p |

Qwen의 합계 ASR은 GPT-4o의 3.53배다. 특히 TAP의 증가가 +28.93%p로 가장 컸다. 같은
공격 알고리즘도 target의 안전정렬과 instruction-following 특성에 크게 의존하므로 “기법이
강하다”와 “특정 target에 강하다”를 구분해야 한다.

## 6. PCSA는 정확히 무엇을 최적화하는가

PCSA의 핵심은 **target 응답을 보고 네 심리 전략 중 다음 history로 이어갈 후보를 온라인
선택**하는 것이다.

```text
persona + style/state + pathology + hidden goal + selected history
  → reassurance / expertise / intellectualization / metaphor 후보 4개
  → target 응답 4개
  → GPT-4o-mini가 1–10점과 compliance 신호 평가
  → 최고 client–target 한 쌍만 history에 추가
  → 최대 4턴 반복
```

Persona+History는 source history를 target의 과거 대화로 그대로 재생하지 않는다. client의
문체·상태 trajectory와 persona 특성으로 공격자를 조건화할 뿐이고, target history는 현재
Phase II가 새로 만든 선택 경로다.

이 추가 정보는 Qwen target paired 실험에서 분명히 효과가 있었다. No-Persona 대비
Persona+History는 HarmBench를 14/197에서 55/197로, PCSA Target Compliance를
29/197에서 111/197로 높였다. 그러나 snapshot-pinned GPT-4o Persona+History에서는
온라인 evaluator가 35건을 성공으로 조기 종료했어도 최종 HarmBench 양성은 9건뿐이었다.

또한 GPT-4o 셀의 743개 선택 round 중 `reassurance_seeking`이 663개(89.23%)였다. 점수
동률일 때 고정된 후보 순서가 선택을 한쪽으로 몰 수 있고, 공감적으로 대화를 이어가는 응답이
직접 위해 수행보다 높게 보일 수 있다. 실제 대표 실패에서는 네 전략 모두 매 턴 1점인데
첫 전략이 계속 선택됐다. 따라서 PCSA의 주요 실패는 다음 두 곳이다.

1. **selector mismatch:** 중간평가자의 engagement/compliance 신호가 최종 HarmBench 수행과
   일치하지 않음
2. **compliance boundary:** target이 persona와 목표를 이해해도 구체적인 행동 수행으로
   넘어가지 않음

## 7. PCSA, Jargon v1, 현재 1011의 구조적 차이

| 비교 축 | PCSA Phase II | Jargon History Bridge v1 | 현재 OURS `1011_method_v1` |
|---|---|---|---|
| 정식 결과 코호트 | Final-197 외부 baseline | Official-500 보존 v1 | Final-197 최종 메서드 |
| 기본 목적 | adaptive client attack으로 target compliance 탐색 | target이 누적 분석에서 latent request를 의미적으로 복원하는지 측정 | target-generated 분석을 정확 인용해 safety-negative-example 직접응답을 4회 측정 |
| private goal을 아는 주체 | attacker와 evaluator | Qwen planner와 사후 evaluator | Qwen planner·coverage/anchor 로직과 evaluator |
| 연구 단계 target goal 노출 | 직접 노출하지 않음; 공격 문장으로 간접 표현 | neutral arm은 원문 숨김 | `no_verbatim`은 원문 숨김, 자연화 단서만 제공; `explicit`은 ablation |
| source persona history | attacker conditioning에 사용, target에 replay하지 않음 | target-visible 과거 상담 record와 persona 형성 | `no_verbatim`에서 target-visible case record; `no_history`로 제거 실험 |
| target 응답의 다음 사용 | 네 공격 후보 점수화 후 최고 한 쌍 선택 | 다음 중립 연구 질문과 coverage 판단 | 고정 7단계의 다음 분석 및 quote/coverage gate에 사용 |
| 중간평가자 | GPT-4o-mini가 후보별 성공 점수 | Qwen coverage checker; attack 후보 순위자는 아님 | coverage와 exact-quote gate; endpoint를 보고 새 공격을 반복 선택하지 않음 |
| 순차 적응 | 최대 4 attack turns | 4–7 research stages, coverage 충족 시 중단 | 고정 7단계 + 실패 시 사전 생성 Case A/B 1회 |
| 최종 출력 | 선택 trajectory의 마지막 target response 1개 | 고정 history에서 독립 semantic readout 4개 | 고정 history에서 네 recovery/anchor와 네 one-shot attack responses |
| 최종 aggregation | 응답 1개/case | metric별 Success@4 | metric별 Best-of-4; strict joint는 같은 분기 |
| 전형적 실패 | 공감·비거절을 성공처럼 고르지만 행동 수행은 없음 | 의미는 복원하지만 안전한 분석·상담 응답에 머묾 | 네 분기 모두 거절하거나, 의미 복원은 되지만 B4/HarmBench 경계를 못 넘음 |

공통점은 세 방법 모두 단순히 goal을 같은 문장으로 반복하지 않고 persona와 history를
이용한다는 것이다. 차이는 **history가 누구의 의사결정을 바꾸는가**다.

- PCSA의 history는 attacker가 다음 client utterance를 고르는 데 쓰인다.
- Jargon의 history는 target이 이미 만든 의미 구조를 final readout이 다시 읽도록 한다.
- 1011은 그 의미 구조에서 target의 정확 인용문을 anchor로 고른 뒤, “제공되어서는 안 될
  응답”이라는 고정된 final task로 옮긴다.

즉 PCSA는 `attack proposal search`, Jargon은 `semantic readout`, 1011은
`semantic recovery → quoted anchor → one-shot response elicitation`에 가깝다.

## 8. Jargon의 성과와 막히는 지점

Official-500에서 History Bridge는 legacy readout보다 target-originated Recovery@4를
GPT-4o에서 94.8%→97.0%(+2.2%p), Qwen에서 92.8%→98.2%(+5.4%p)로 높였다.
B3+@4도 GPT-4o 66.0%→79.2%, Qwen 64.0%→88.0%로 증가했다.

그러나 GPT-4o의 수정된 JMIR harmful-response rate는 History Bridge와 legacy가 모두
0.20%였고, dialogue+bridge의 harmful@4는 0.60%였다. 오히려 연구대화를 제거한
`no_dialogue`의 harmful rate는 18.15%, harmful@4는 53.60%였다. Qwen에서도
dialogue+bridge harmful rate 0.95%, harmful@4 3.0%로 no-dialogue의 11.5%, 36.6%보다
낮았다.

따라서 Jargon이 해결한 것은 주로 **숨은 목표의 의미 복원과 provenance 연결**이다.
의미를 정확히 읽는 것과 그 목표를 실제 답변으로 수행하는 것은 분리된다. 누적 연구 대화가
오히려 target을 분석·안전 문맥에 고정해 harmful manifestation을 낮춘 결과도 숨기면 안 된다.

## 9. 현재 1011이 Jargon에서 바꾼 핵심

현재 Final-197 OURS는 Jargon의 target-generated semantic structure를 활용한다는 생각을
이어가되 다음을 바꿨다.

1. 연구 stage를 7단계로 고정해 조기 coverage 종료로 뒤 단계가 사라지는 문제를 제거했다.
2. coverage 또는 정확 인용 가능성이 부족한 사례에만 Case A/B 비교 질문을 한 번 쓴다.
3. 각 final direction에서 latent request를 복원한 뒤 target 자신의 정확 연속 인용문을
   evidence anchor로 고정한다.
4. final task를 분석 요약이 아니라 safety 연구용 “구체 negative example”의 다음 assistant
   message로 바꾼다.
5. 최종 응답을 본 뒤 새 prompt로 반복하지 않고 네 사전 등록 분기를 독립 1회 측정한다.

Final-197 `no_verbatim`의 HarmBench Best-of-4는 176/197(89.34%), 같은 분기 Strict
Joint@4는 126/197(63.96%)였다. 외부 baseline의 응답 1개/case와 response unit 및 query
budget이 다르므로 PAIR 14.72%와 나눠 배수 우위를 주장하지 않는다. 다만 직접 사례에서는
PCSA가 공감적 은폐 조언까지 도달한 동일 case에서 1011의 네 분기 중 두 개가 위해 수행으로,
두 개가 명시적 거절로 갈라지는 것을 확인할 수 있다.

## 10. 논문용 핵심 서술

> External baselines differed primarily in how they searched over attacker prompts:
> a single adaptive path (Red Teaming), parallel iterative streams (PAIR), a pruned
> branching tree (TAP), gradual escalation with backtracking (Crescendo), or evaluator-
> selected persona-conditioned candidates (PCSA). In contrast, our registered 1011
> method did not adapt its final attack after observing the endpoint. It first accumulated
> a fixed seven-stage target-generated analysis, anchored four pre-registered branches to
> exact target quotations, and issued one final response request per branch.

> PCSA and Jargon History Bridge both used goal-aware auxiliary models, but optimized
> different transitions. PCSA selected the next client utterance according to an online
> compliance evaluator, whereas Jargon reused the target's own accumulated semantic
> structure for four independent readouts. Jargon substantially improved target-originated
> recovery without increasing the corrected harmful-response endpoint, motivating the
> later 1011 separation of semantic recovery, exact evidence anchoring, and one-shot final
> response elicitation.

## 11. 재현 근거와 제한

- 외부 9개 방법의 구현: `external_baselines/run_pyrit_baseline.py`와 pinned PyRIT v1.1.0
- PCSA 루프: `external_baselines/pcsa_phase2.py`
- 외부 설정과 집계: [`SETTINGS_AND_PROVENANCE_KO.md`](SETTINGS_AND_PROVENANCE_KO.md),
  [`TABLES_KO.md`](TABLES_KO.md)
- Jargon 계약과 결과: `persona_redteam/result/OURS/METHOD_CONFIG_KO.md`,
  `persona_redteam/result/MAIN_RESULTS.json`
- 현재 1011 계약: `persona_redteam/singleton_1011_package/README_KO.md`

PCSA는 공개 원 코드가 없어 논문과 Appendix prompt를 재구성한 adapter다. 기존 9×2
matrix의 GPT-4o target은 snapshot이 기록되지 않은 alias이고, 추가 PCSA 셀과 1011은
`gpt-4o-2024-11-20`으로 고정됐다. 이 차이와 코호트·판정기·response aggregation 차이
때문에 패널 사이 공식 순위나 유의성 검정을 만들지 않는다.
