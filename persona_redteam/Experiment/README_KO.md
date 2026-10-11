# RED-Persona 논문용 실험 번들

> 숨은 유해 목표 공격의 현재 계약은 `METHOD_V2_HARMFUL_GOAL_CONTRACT_KO.md`와
> `HARMFUL_GOAL_METHOD_V2_CONTRACT.json`이다. 기존 Official-500 문서는 상담 원문 기반
> latent-request v1 재현 자료로 보존한다.

이 폴더는 Official-500 실험을 논문 Methods와 재현 부록에서 바로 설명할 수 있도록 고정한
snapshot이다. 실제 실행 가능한 canonical 구현은 저장소의 `experiments/`, `ablation/`,
`pipeline/`에 있으며, `core_code/`는 이번 실험에 직접 쓰인 핵심 파일의 감사용 사본이다.

## 읽는 순서

1. `../experiments/final197/README_KO.md`: 최종 197건 고정 설정, 병렬 생성, 두 키 Batch 실행
2. `../result/OURS/RESULTS_KO.md`: OURS 고정 정의와 논문용 통합 결과표
3. `METHOD_AND_DESIGN_KO.md`: 무엇을 왜 비교했는지, 샘플이 단계마다 어떻게 변하는지
4. `REPRODUCE_KO.md`: 무호출 점검, 누락분 평가, 결과 검증 명령
5. `CORE_CODE_MANIFEST.md`: 사본과 canonical source의 대응
6. `OFFICIAL500_SALVAGE_DESIGN_KO.md`: 기존 500개를 살리면서 harmful-goal v2를 분리하는 설계
7. `METHOD_V2_HARMFUL_GOAL_CONTRACT_KO.md`: 수정 공격 메서드와 판정 계약
8. `ARTIFACT_STORAGE_KO.md`: Git 밖 대용량 원시 산출물 위치
9. `prompts/`: 실행 당시 CARES/JMIR 평가 프롬프트와 연구 지침
10. `TARGET_MODEL_PILOT40_KO.md`: GPT-6 Luna·Llama 3.1 8B 일반화 파일럿 설계

논문 결과표는 `../result/OURS/README_KO.md`에서 시작한다. OURS는 항상 `neutral` 연구 대화와
`jargon_history_bridge_v1`의 조합이며 oracle, legacy, no-dialogue는 ablation으로만 표기한다.
Canonical 재실행에는 설정 override를 거부하는 `../experiments/run_ours_official500.py`를 사용한다.
