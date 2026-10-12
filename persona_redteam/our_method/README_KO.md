# `our_method/` 개발 작업공간 안내

이 디렉터리는 Final-197 메서드를 만들면서 사용한 개발 진입점, 파일럿 launcher,
ablation과 적응형·멀티턴 실험 코드를 보존한다. **논문 최종 실행의 기준 폴더는 아니다.**

최종 GPT-4o singleton 메서드는 다음 패키지에서만 실행한다.

- [최종 패키지 README](../singleton_1011_package/README_KO.md)
- [논문용 Methods 명세](../singleton_1011_package/docs/FINAL_METHOD_PAPER_SPEC_KO.md)
- [프롬프트 설계](../singleton_1011_package/docs/PROMPT_DESIGN_KO.md)
- [전체 흐름도](../singleton_1011_package/docs/ARCHITECTURE_KO.md)
- [버전 변경 이력](../singleton_1011_package/docs/VERSION_CHANGELOG_KO.md)

## 왜 이 폴더를 유지하는가

- 파일럿과 ablation의 provenance를 보존한다.
- 다른 세션에서 진행 중인 멀티턴·적응형 비교 연구를 중단시키지 않는다.
- 과거 결과의 launcher와 설정을 다시 확인할 수 있게 한다.

이 폴더의 `method_1011/adaptive_attack.py`, `run_attack_turn_ablation.py` 및 관련 파일은
삭제하지 않는다. 작업 중인 코드일 수 있으므로 final package를 갱신할 때도 자동 복사하거나
덮어쓰지 않는다.

## 최종 메서드와의 경계

논문용 `1011_method_v1`은 다음 계약을 따른다.

| 항목 | 최종 계약 |
|---|---|
| 타깃 | `gpt-4o-2024-11-20` |
| 연구 질문 생성기 | `Qwen/Qwen2.5-7B-Instruct` |
| 전송 | OpenAI Batch API |
| 연구 대화 | 7단계 고정 의미 순서 |
| 조건부 추적 | GOAL/인용 gate 실패 시 Case A/B 질문 1회 |
| 최종 측정 | 네 독립 분기에서 각각 한 번 |
| 보고 | metric별 Best-of-4와 같은-분기 엄격 결합 |
| 멀티턴 adapter | 코드 보존, canonical 실행 graph에서는 미사용 |

즉, 이 개발 폴더에 멀티턴 코드가 존재하는 것과 논문 최종 메서드가 멀티턴이라는 것은
같은 의미가 아니다. 최종 패키지의 launcher와 manifest가 실제 논문 실행 범위를 결정한다.

## 개발 파일 사용 시 주의

과거 README나 launcher에는 Qwen 타깃, explicit GOAL, 500건 cohort, 실패 후 반복 복구 등
서로 다른 시점의 설정이 남아 있을 수 있다. 비교 실험 자체에는 유효하지만 최종 본실험
설정으로 인용하면 안 된다. 본실험 재현, 결과 표 작성과 논문 Methods 기술에는 반드시
`singleton_1011_package/`의 코드·문서·manifest를 사용한다.

API 키와 실행 결과 원문은 Git에 저장하지 않는다.
