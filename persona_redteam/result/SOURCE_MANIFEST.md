# Result snapshot provenance

`result/`는 아래 canonical 산출물을 논문 작성 편의를 위해 복사한 snapshot이다. 원본 수정 후에는
사본도 함께 갱신하고 checksum 차이를 검토한다.

| snapshot | canonical source |
|---|---|
| `tables/CARES_JMIR_ABLATION_OFFICIAL500_KO.md` | `ablation/cares_jmir_rq/RESULTS_KO.md` |
| `machine_readable/CARES_JMIR_ABLATION_OFFICIAL500.json` | `ablation/cares_jmir_rq/RESULTS.json` |
| `tables/HISTORY_BRIDGE_PROMPT_OFFICIAL500_KO.md` | `ablation/RESULTS_HISTORY_BRIDGE_PROMPT_OFFICIAL500_KO.md` |
| `tables/DIRECTION_ATTRIBUTION_OFFICIAL500_KO.md` | `ablation/RESULTS_OFFLINE_DIRECTION_ATTRIBUTION_OFFICIAL500_KO.md` |
| `tables/DIALOGUE_METRIC_SCORECARD_OFFICIAL500_KO.md` | `ablation/RESULTS_DIALOGUE_METRIC_SCORECARD_KO.md` |
| `machine_readable/HISTORY_BRIDGE_*_OFFICIAL500.json` | `docs/results/history_bridge_prompt_official500_*.json` |

민감한 prompt/response 원문과 evaluator rationale은 snapshot에 넣지 않는다. 공개 row에는 label,
분석 키와 SHA-256만 두며 canonical 공개 파일은 `ablation/cares_jmir_rq/`에 있다.

