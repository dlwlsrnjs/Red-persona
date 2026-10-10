# 외부 9개 jailbreak baseline Official-500

- 설계: 9 methods × Qwen2.5-7B/GPT-4o × 500 = 9,000
- 실제 target 응답: 8,905; TAP 사전 가지치기 무응답: 95
- CARES A/C/R: `2,861 / 5,589 / 455`
- Accept: `32.13%`
- Non-refuse ASR: `94.89%`
- CARES SS: `41.51%`
- JMIR 평균: `4.0119`
- JMIR harmful: `1.4711%`

주요 셀은 GPT-4o Red Teaming의 CARES SS `59.9%`, Qwen Red Teaming의 `54.2%`, Qwen PCSA
Phase 2의 non-refuse ASR `100%`, GPT-4o PCSA Phase 2의 `99.6%`다. 하지만 서로 다른 지표를
하나의 우열로 합치지 않는다. 전체 18개 셀과 분모·복구·비용은
[`../../external_baselines/CARES_JMIR_OFFICIAL500_RESULTS_KO.md`](../../external_baselines/CARES_JMIR_OFFICIAL500_RESULTS_KO.md)에 있다.

평가 생성은 OpenAI Batch로 완료했으며 Batch 평가비는 `$4.91147145`였다. 9,000개 기대 행 중
응답이 존재한 8,905개를 채점하고, 무응답 95개는 만들거나 대체하지 않았다.
