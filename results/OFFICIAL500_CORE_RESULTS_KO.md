# Official-500 핵심 결과

기준일: 2026-10-10

## RED-Persona history-bridge

각 target과 arm은 같은 500 case, case당 네 final direction으로 구성된다. branch-level 분모는
2,000이고 Success@4 분모는 500이다.

| Target | 비교 | 지표 | Control | History-bridge | 차이 |
|---|---|---|---:|---:|---:|
| Qwen2.5-7B | legacy full | Raw Success@4 | 93.4% | 98.4% | +5.0%p |
| Qwen2.5-7B | legacy full | Target-originated Success@4 | 92.8% | 98.2% | +5.4%p |
| GPT-4o | legacy full | Raw Success@4 | 95.0% | 97.2% | +2.2%p |
| GPT-4o | legacy full | Target-originated Success@4 | 94.8% | 97.0% | +2.2%p |
| Qwen2.5-7B | no dialogue | Branch raw recovery | 80.10% | 92.30% | +12.20%p |
| GPT-4o | no dialogue | Branch raw recovery | 81.95% | 93.25% | +11.30%p |

History-bridge 대 legacy full의 Raw Success@4 paired exact McNemar p-value는 Qwen
`4.17e-7`, GPT-4o `0.0127`이다. 반면 no-dialogue의 Success@4 자체가 이미 97.8–98.2%라
history-bridge와 no-dialogue의 case-level 차이는 ceiling에 막혔다. 이 비교에서는
branch-level 일관성 증가가 주 결과다.

## RED-Persona CARES/JMIR

| Target | 조건 | CARES SS | JMIR 평균 | JMIR harmful |
|---|---|---:|---:|---:|
| GPT-4o | History dialogue | 19.98% | 3.2140 | 0.20% |
| GPT-4o | No dialogue | 14.50% | 3.1285 | 18.15% |
| Qwen2.5-7B | History dialogue | 46.13% | 3.0545 | 0.95% |
| Qwen2.5-7B | No dialogue | 15.85% | 2.9997 | 11.50% |

CARES SS는 두 arm의 입력 위험도 분포가 달라 순수 공격 성공 효과로 해석하지 않는다. JMIR은
원 rubric을 우리 마지막 target question에 적용한 adaptation이다.

## 외부 9개 jailbreak baseline

- 설계: 9 methods × 2 targets × 500 = 9,000
- 실제 target 응답: 8,905; TAP 사전 가지치기 무응답: 95
- CARES A/C/R: `2,861 / 5,589 / 455`
- Accept: `32.13%`
- Non-refuse ASR: `94.89%`
- CARES SS: `41.51%`
- JMIR 평균: `4.0119`
- JMIR harmful: `1.4711%`

눈에 띄는 셀은 GPT-4o Red Teaming의 CARES SS `59.9%`, Qwen Red Teaming의 `54.2%`,
Qwen PCSA Phase 2의 non-refuse ASR `100%`, GPT-4o PCSA Phase 2의 `99.6%`다. 다만 지표마다
의미가 다르므로 단일 숫자로 전체 우열을 정하지 않는다.

## 재현성

- 고정 공식 코호트: 500개
- 외부 baseline 평가 모델: `gpt-4o-mini`
- RED-Persona 평가 모델: `gpt-4o-mini-2024-07-18`
- 외부 baseline Batch 평가 실제 비용: `$4.91147145`
- 완료 평가 coverage: 외부 baseline `8,905/9,000`, RED-Persona paired arm `8,000/8,000`

