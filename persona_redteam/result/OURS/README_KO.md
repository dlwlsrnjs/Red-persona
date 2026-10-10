# OURS paper result package

이 폴더가 논문에서 OURS를 정의하는 단일 진입점이다.

- `EXPERIMENT_CONTRACT.json`: 변하지 않아야 하는 canonical 설정
- `RESULTS.json`: 기계 판독 가능한 Official-500 aggregate
- `RESULTS_KO.md`: 논문용 주 결과표, 보조 Recovery 분석, ablation 해석
- `../../experiments/run_ours_official500.py`: canonical 설정을 강제로 잠그는 실행 진입점

OURS는 항상 `neutral + jargon_history_bridge_v1 + four directions`다. `oracle_hint`,
`legacy_v15`, `no_dialogue`를 OURS로 표기하지 않는다.

Goal recovery는 생성 Method에 포함하지 않으며, 저장된 응답에 대한 사후 보조 분석으로만
보고한다.

재생성:

```bash
python3 experiments/export_ours_paper_results.py
```
