# Final-197 query-16 matched sensitivity analysis

이 폴더는 기존 호출 상한이 낮았던 Red Teaming, Crescendo, Therapist Crescendo를 사례당
최대 16 target 호출로 다시 실행한 민감도 분석의 단일 진입점이다. GPT-4o와
Qwen-2.5-7B-Instruct 각각 197개를 사용하며, 조기 성공은 허용한다.

## 파일

- `query16_results.json` / `query16_results.csv`: 6개 셀의 정규화 집계
- `TABLES_KO.md`: 사람이 읽는 전체 표와 이전 예산 대비 HarmBench 변화
- `paper_tables.tex`: `booktabs` 기반 논문용 표
- `paper_results_paragraphs.tex`: 논문 본문에 붙일 수 있는 결과 문단
- `CHANGELOG_AND_PAPER_GUIDE_KO.md`: 코드 변경 위치, RQ, 논문 삽입 위치와 해석 제한
- `AUDIT.json`: 입력·평가·manifest의 SHA-256과 비교 계약
- `build_results.py`: 패키지 재생성 및 검증

## 해석 제한

Query-16은 target 호출 상한을 맞춘 것이며 공격의 탐색 구조를 동일하게 만든 실험은 아니다.
이번 CARES와 R/B 판정기는 GPT-4o이므로 기존 GPT-4o-mini 판정 결과와 직접 증감 비교하지
않는다. HarmBench는 같은 고정 classifier를 사용하므로 이전 호출 예산과의 민감도 비교가
가능하다. OURS는 사례별 Best-of-4이고 외부 baseline은 하나의 최종 응답이므로, 호출 상한이
같더라도 response-selection unit이 완전히 같지는 않다.

Qwen Red Teaming의 R/B 보조 판정 1건은 반복 재판정 뒤에도 literal-evidence 검증을
통과하지 못해 invalid로 보존하고 관련 보조지표에 0을 기여시켰다. 주 지표 HarmBench와
CARES를 포함한 나머지 평가축은 모든 셀에서 197/197 valid다.

## 재생성

```bash
python3 external_baselines/result/final197_query16_matched_v1/build_results.py
python3 external_baselines/result/final197_query16_matched_v1/build_results.py --check
```
