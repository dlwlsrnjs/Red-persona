# Official-500 앞 10개 target-model 파일럿

외부 베이스라인과 동일한 `official_index` 1–10을 사용한 추가 타겟 파일럿이다. 정확한
`case_id`와 `canonical_source_index` 연결은
`ablation/TARGET_MODEL_PILOT10_OFFICIAL_FIRST10.json`에 고정했다.

## 현재 상태

- Llama 3.1 8B Instruct: 생성·CARES/JMIR Batch 평가 완료
- GPT-6 Luna: OpenAI Batch 생성 진행 중
- Recovery: 실행하지 않음

## 완료된 Llama 결과

| Arm | CARES SS ↑ | JMIR appropriateness ↑ | harmful-response rate ↓ | harmful@4 ↓ |
|---|---:|---:|---:|---:|
| dialogue + history bridge | 0.0375 | 3.2750 | 0.0% | 0.0% |
| no dialogue | 0.1250 | 3.1833 | 7.5% | 30.0% |

paired `dialogue − no_dialogue`는 CARES SS `−0.0875`, JMIR appropriateness `+0.0917`,
harmful-response rate `−0.0750`이다. 공격 효과 관점에서 CARES와 JMIR harmful 지표의 방향이
엇갈리므로, 이 10개 결과만으로 대화 조건이 일관되게 우월하다고 결론내리지 않는다.

세부 결과와 공개 라벨은 `llama31_8b/`에 있다. GPT-6 Luna와 그 평가가 완료되면 네 arm을
결합한 `RESULTS.json`, `RESULTS_KO.md`, `LABELED_ROWS.jsonl`을 이 폴더 최상위에 생성한다.
