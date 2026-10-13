# 외부 baseline 결과

현재 논문 코호트의 단일 기준은
[`final197_external_baselines_v2/README_KO.md`](final197_external_baselines_v2/README_KO.md)다.
완료된 외부 baseline 21개 셀의 내용, 전체 표, 설정, 해석, CSV/JSON, provenance와 재생성
코드를 한 폴더에 정리했다.

기존 18개 외부 baseline 셀의 최종 응답을 GPT-4o로 다시 판정한 별도 결과는
[`final197_gpt4o_evaluator_v1/README_KO.md`](final197_gpt4o_evaluator_v1/README_KO.md)에
있다. 이 패키지는 GPT-4o-mini R/B 및 CARES 판정을 GPT-4o로 대체 비교한 3,546행 결과,
strict-joint와 18개 셀 통합 JSON/CSV를 포함하며, 추가 PCSA 3개 셀은 범위에 포함하지
않는다.

호출 상한이 기존 4--6회였던 반복형 공격을 최대 16 target query로 다시 실행한
민감도 분석은
[`final197_query16_matched_v1/README_KO.md`](final197_query16_matched_v1/README_KO.md)에
분리했다. 이 폴더에는 GPT-4o/Qwen × 3개 방법의 6개 셀, 호출 수 분포, 이전 예산 대비
HarmBench 변화, 논문용 LaTeX와 재생성 감사가 있다. 기존 canonical 행렬을 덮어쓰지 않으며
query-budget RQ/부록용으로 사용한다.

외부 공격이 실제 응답의 어느 지점에서 실패했는지는
[`final197_external_baselines_v2/QUALITATIVE_FAILURE_ANALYSIS_KO.md`](final197_external_baselines_v2/QUALITATIVE_FAILURE_ANALYSIS_KO.md)의
대표 3건 정성 분석에서 확인할 수 있다.

각 기법의 멀티턴 제어 흐름과 PCSA–Jargon–1011의 차이는
[`final197_external_baselines_v2/METHOD_TURN_STRUCTURE_AND_FAILURE_MAP_KO.md`](final197_external_baselines_v2/METHOD_TURN_STRUCTURE_AND_FAILURE_MAP_KO.md),
안전정렬 유지와 경계 통과의 직접 사례는
[`final197_external_baselines_v2/DIRECT_SAMPLE_CASEBOOK_KO.md`](final197_external_baselines_v2/DIRECT_SAMPLE_CASEBOOK_KO.md)에
분리했다.

## Canonical source aggregate

아래 파일은 통합 패키지를 재생성하는 검증된 기계 source다.

| 파일 | 범위 |
|---|---|
| `final197_main_results.json` / `.csv` | 9개 방법 × GPT-4o/Qwen = 18개 셀 |
| `final197_evaluation_audit.json` | 위 3,546행의 평가별 coverage 감사 |
| `pcsa_persona_ablation_final197.json` | Qwen Persona+History 대 No-Persona paired 2셀 |
| `pcsa_persona_history_gpt4o_final197.json` | GPT-4o-2024-11-20 Persona+History 추가 1셀 |

개별 Markdown 결과표, 10건 pilot, 미완료 progress snapshot과 다른 코호트의 오래된 결과는
canonical 통합 문서로 대체해 삭제했다. 제외 사유와 원 커밋은
[`final197_external_baselines_v2/AUDIT.json`](final197_external_baselines_v2/AUDIT.json)에
남아 있어 Git 이력에서 복구할 수 있다.

OURS와 나란히 보는 논문용 분리 패널은
[`../../persona_redteam/result/final197_paper_comparison_v1/README_KO.md`](../../persona_redteam/result/final197_paper_comparison_v1/README_KO.md)를
사용한다. 외부 방법을 OURS로 표기하거나 서로 다른 response unit/query budget을 하나의
공식 순위로 합치지 않는다.
