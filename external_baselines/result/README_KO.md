# 외부 baseline 결과

현재 논문 코호트의 단일 기준은
[`final197_external_baselines_v2/README_KO.md`](final197_external_baselines_v2/README_KO.md)다.
완료된 외부 baseline 21개 셀의 내용, 전체 표, 설정, 해석, CSV/JSON, provenance와 재생성
코드를 한 폴더에 정리했다.

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
