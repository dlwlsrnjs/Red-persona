# PCSA Persona+History vs No-Persona — Final-197

## 실험 설계

동일한 Final-197 case를 대상으로 개인화 입력만 바꾼 paired ablation이다.

| 조건 | 제거/사용한 입력 | 공통 고정 조건 |
|---|---|---|
| Persona+History | case별 persona와 4–9턴 source history 사용 | Qwen2.5-7B target/attacker, 동일 goal/pathology route, 4전략, 최대 4턴, turn당 4후보, 동일 evaluator |
| No-Persona | client profile, persona, source history, style/state reference 모두 제거 | 왼쪽과 동일 |

Persona+History의 source history는 attacker의 Phase-I 특성·문체 입력으로만 사용했고
target의 과거 대화로 재생하지 않았다.

## 전체 결과

공격 관점에서 ASR·Unsafe·R/B·Strict Joint는 높을수록 강하고, CARES SS는
낮을수록 강하다.

| 지표 | Persona+History | No-Persona | 차이 |
|---|---:|---:|---:|
| HarmBench ASR ↑ | **55/197 (27.92%)** | 14/197 (7.11%) | **+20.81%p; 3.93×** |
| PCSA GPT-4o UNSAFE ↑ | **111/197 (56.35%)** | 30/197 (15.23%) | **+41.12%p** |
| PCSA Target Compliance ↑ | **111/197 (56.35%)** | 29/197 (14.72%) | **+41.63%p** |
| PCSA Harmful Content ↑ | **103/197 (52.28%)** | 19/197 (9.64%) | **+42.64%p** |
| R3+ ↑ | **115/197 (58.38%)** | 34/197 (17.26%) | **+41.12%p** |
| B4+ ↑ | **49/197 (24.87%)** | 14/197 (7.11%) | **+17.77%p** |
| R3+ ∧ B4+ ↑ | **49/197 (24.87%)** | 13/197 (6.60%) | **+18.27%p** |
| Strict Joint ASR ↑ | **26/197 (13.20%)** | 7/197 (3.55%) | **+9.64%p; 3.71×** |
| CARES ASR ↑ | 168/197 (85.28%) | **195/197 (98.98%)** | -13.71%p |
| CARES SS ↓ | 0.515 | **0.383** | +0.132 |

CARES 분포:

| 조건 | Accept | Caution | Refuse | No response |
|---|---:|---:|---:|---:|
| Persona+History | 23 | 145 | 29 | 0 |
| No-Persona | 48 | 147 | 2 | 0 |

CARES non-refusal은 No-Persona를 더 강하게 평가하지만, 목표 수행을 직접 요구하는
HarmBench, PCSA Target Compliance, B4+ 및 Strict Joint는 모두 Persona+History가
크게 높다. 따라서 CARES ASR만으로 persona 효과를 결론내리지 않는다.

## HarmBench paired audit

| 동일 case의 판정 조합 | 개수 |
|---|---:|
| 양 조건 모두 양성 | 10 |
| Persona+History만 양성 | 45 |
| No-Persona만 양성 | 4 |
| 양 조건 모두 음성 | 138 |

Discordant pair 49개에 대한 exact McNemar/binomial 양측 검정은
`p = 8.23e-10`이다. 이는 persona 조건의 HarmBench 개선이 일부 case 교체가 아닌
동일 case에서의 방향성 있는 변화임을 보여준다.

## HarmBench 구현 감사

- classifier: `cais/HarmBench-Llama-2-13b-cls`
- 사용 snapshot: `bda705349d1144fa618770bea64d99ce54e3835b`
- 공식 standard classifier prompt 사용
- target의 최종 응답만 generation으로 전달
- completion 앞 512 tokens만 평가
- greedy decoding, `max_new_tokens=1`, `yes/no` 이진 판정
- 무응답은 공격 실패(label 0)
- 두 조건 모두 197/197 유효, invalid 0, 무응답 0
- classifier prompt 경계 문자열(`[INST]`, `[/INST]`, `<<SYS>>`, `<</SYS>>`)이
  target 응답에 포함된 사례 0

본 데이터는 HarmBench 원본 behavior set이 아니므로, 논문 표기에는
`HarmBench-classifier ASR (adapted mental-health behaviors)`를 사용한다.

## 완전성 주의

HarmBench, CARES, PCSA Figure-4 judge는 두 조건 모두 197/197 유효하다.
Persona+History의 R/B 결과 중 1건은 evidence literal-span 검증을 통과하지 못했다.
위 표의 R/B 및 Strict Joint는 해당 1건을 성공으로 올리지 않는 보수적 집계이며,
해당 행은 별도 재판정 대상으로 남긴다. No-Persona R/B는 197/197 유효하다.
