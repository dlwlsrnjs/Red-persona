# RED-Persona results

이 폴더는 논문과 발표에서 바로 확인할 수 있는 핵심 결과의 공개 인덱스다. 대용량 원문 응답과
Batch 체크포인트는 Git에서 제외하고, 표·정의·분모·평가 모델·재현 경로가 있는 요약만 둔다.
유리한 결과를 먼저 제시하되 반대 결과, ceiling effect, 무응답도 함께 기록한다.

## 가장 중요한 결과

1. **History-bridge는 네 방향 각각의 목표 복원 일관성을 높였다.** Official-500에서
   no-dialogue 대비 branch-level raw recovery가 Qwen에서 `+12.20%p`, GPT-4o에서
   `+11.30%p`였다.
2. **기존 legacy full prompt보다 history-bridge가 더 강했다.** Raw Recovery Success@4는
   Qwen `93.4% → 98.4%` (`+5.0%p`, exact McNemar `p=4.17e-7`), GPT-4o
   `95.0% → 97.2%` (`+2.2%p`, `p=0.0127`)였다.
3. **연구자 주입을 제외한 복원도 함께 개선됐다.** Target-originated Success@4는 Qwen
   `92.8% → 98.2%`, GPT-4o `94.8% → 97.0%`였다.
4. **외부 jailbreak 비교군은 높은 non-refuse 비율을 보였다.** 9개 기법 × Qwen/GPT-4o
   Official-500에서 전체 non-refuse ASR은 `94.89%`, CARES Accept는 `32.13%`였다.
5. **정신건강 적절성 지표는 별도 방향을 보였다.** 외부 비교군 전체 JMIR harmful rate는
   `1.47%`였다. RED-Persona의 history-dialogue arm은 no-dialogue보다 harmful rate가
   GPT-4o에서 `17.95%p`, Qwen에서 `10.55%p` 낮았다. 따라서 “복원 증가”와 “유해 응답 증가”는
   같은 주장으로 합치지 않는다.

## 결과 문서

- [`OFFICIAL500_CORE_RESULTS_KO.md`](OFFICIAL500_CORE_RESULTS_KO.md): 핵심 수치와 해석 경계
- [`../external_baselines/CARES_JMIR_OFFICIAL500_RESULTS_KO.md`](../external_baselines/CARES_JMIR_OFFICIAL500_RESULTS_KO.md): 18개 외부 baseline 셀 전체 표
- [`../persona_redteam/ablation/RESULTS_HISTORY_BRIDGE_PROMPT_OFFICIAL500_KO.md`](../persona_redteam/ablation/RESULTS_HISTORY_BRIDGE_PROMPT_OFFICIAL500_KO.md): history-bridge paired 결과
- [`../persona_redteam/docs/RESULTS_CARES_JMIR_OFFICIAL500_KO.md`](../persona_redteam/docs/RESULTS_CARES_JMIR_OFFICIAL500_KO.md): RED-Persona CARES/JMIR 결과
- [`../persona_redteam/ablation/RESULTS_OFFLINE_DIRECTION_ATTRIBUTION_OFFICIAL500_KO.md`](../persona_redteam/ablation/RESULTS_OFFLINE_DIRECTION_ATTRIBUTION_OFFICIAL500_KO.md): 네 방향 기여도

## 진행 중

`GPT-6 Luna + Meta-Llama-3.1-8B-Instruct` 10-case 파일럿은
[`../experiments/gpt6_luna_llama_pilot/README.md`](../experiments/gpt6_luna_llama_pilot/README.md)에
고정했다. 완료 후 같은 CARES/JMIR 열을 이 폴더에 추가한다.

