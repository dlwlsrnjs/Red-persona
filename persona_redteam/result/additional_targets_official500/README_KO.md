# Additional Targets Official-500 결과

이 폴더는 현재 Official-500 전체에 대한 GPT-6 Luna와 Llama 3.1 8B Instruct 추가 타겟
결과만 담는다. 실험 계약은
`Experiment/additional_targets_official500/EXPERIMENT_CONTRACT.json`을 기준으로 한다.

## 포함할 결과

| Target | Arm | Cases | Responses |
|---|---|---:|---:|
| GPT-6 Luna | dialogue + history bridge | 500 | 2,000 |
| GPT-6 Luna | no dialogue | 500 | 2,000 |
| Llama 3.1 8B | dialogue + history bridge | 500 | 2,000 |
| Llama 3.1 8B | no dialogue | 500 | 2,000 |

최종 공개 산출물은 다음과 같다.

- `RESULTS_KO.md`: 논문용 네 arm 표와 paired 비교
- `RESULTS.json`: 기계 판독 가능한 집계
- `LABELED_ROWS.jsonl`: 원문 대신 hash와 평가 라벨을 담은 8,000개 공개 행
- `STATUS.json`: shard별 생성·평가·비용·완결성 상태
- `QUALITY_AUDIT_KO.md`: 누락·빈 응답·중복·잘림·누출 검사

CARES SS, A/C/R, input h-level, JMIR appropriateness, harmful-response rate, harmful@4를 모두
보고한다. CARES와 JMIR이 서로 다른 방향을 보이면 하나만 선택하지 않고 입력 위험도 분포와
함께 해석한다.

