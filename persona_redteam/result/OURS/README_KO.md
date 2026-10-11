# OURS paper result package

> **해석 교정:** 이 폴더의 기존 Official-500은 `original_request`를 private goal로 사용한
> latent-request study다. 별도 유해 목표 공격 결과가 아니다. 공격 메서드 v2와 수치별 올바른
> 해석은 `INTERPRETATION_CORRECTION_KO.md` 및
> `../../Experiment/METHOD_V2_HARMFUL_GOAL_CONTRACT_KO.md`를 우선한다.

이 폴더가 논문에서 OURS를 정의하는 단일 진입점이다.

- `EXPERIMENT_CONTRACT.json`: 변하지 않아야 하는 canonical 설정
- `RESULTS.json`: 기계 판독 가능한 Official-500 aggregate
- `METHOD_CONFIG_KO.md`: 생성 Method와 고정 실행 설정만 정리한 문서
- `TABLES_KO.md`: CARES SS/JMIR 주 결과와 ablation 표
- `SUPPLEMENTARY_GOAL_RECOVERY_KO.md`: Method와 분리한 사후 보조 분석
- `RESULTS_KO.md`: 위 내용을 한 파일에서 보는 통합 보고서
- `INTERPRETATION_CORRECTION_KO.md`: 기존 수치를 harmful ASR로 읽을 수 없는 이유
- `SOURCE_REQUEST_STRATIFIED_RESULTS_KO.md`: `is_request × source h-level` 무호출 재분석
- `../../experiments/run_ours_official500.py`: canonical 설정을 강제로 잠그는 실행 진입점

기존 v1 OURS는 `neutral + jargon_history_bridge_v1 + four directions`다. `oracle_hint`,
`legacy_v15`, `no_dialogue`를 OURS로 표기하지 않는다.

Goal recovery는 생성 Method에 포함하지 않으며, 저장된 응답에 대한 사후 보조 분석으로만
보고한다. 기존 B3+는 `goal-conditioned response enactment`로만 보고하며 unsafe/ASR로
해석하지 않는다.

재생성:

```bash
python3 experiments/export_ours_paper_results.py
python3 experiments/stratify_official500_v1_by_request.py
```
