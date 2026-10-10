# RED-Persona 논문용 실험 번들

이 폴더는 Official-500 실험을 논문 Methods와 재현 부록에서 바로 설명할 수 있도록 고정한
snapshot이다. 실제 실행 가능한 canonical 구현은 저장소의 `experiments/`, `ablation/`,
`pipeline/`에 있으며, `core_code/`는 이번 실험에 직접 쓰인 핵심 파일의 감사용 사본이다.

## 읽는 순서

1. `METHOD_AND_DESIGN_KO.md`: 무엇을 왜 비교했는지, 샘플이 단계마다 어떻게 변하는지
2. `REPRODUCE_KO.md`: 무호출 점검, 누락분 평가, 결과 검증 명령
3. `CORE_CODE_MANIFEST.md`: 사본과 canonical source의 대응
4. `ARTIFACT_STORAGE_KO.md`: Git 밖 대용량 원시 산출물 위치
5. `prompts/`: 실행 당시 CARES/JMIR 평가 프롬프트와 연구 지침

논문 결과표는 `../result/README_KO.md`에서 시작한다.

