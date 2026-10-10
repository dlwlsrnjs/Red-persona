# 대용량 산출물 보관 위치

루트 디스크 고갈을 피하기 위해 2026-10-10 Official-500 확장 원시 산출물을 사용자 전용 대용량
마운트로 옮겼다. 서버에서 요청한 `/data1/ljk98`에 해당하는 실제 쓰기 가능 경로는
`/data1/users/ljk98`이다.

```text
/data1/users/ljk98/Red-persona-artifacts/official500_2026-10-10/
├── campaigns/       # 다섯 arm의 380개 증분 생성 Batch/checkpoint
├── ablation_runs/   # 다섯 arm의 완성된 500개 결과
└── evaluations/     # 취소 Batch와 완료 standard 평가 원시 산출물
```

저장소 `data/campaigns/`, `data/ablation/runs/`, `data/evaluations/`의 해당 이름에는 위 위치를
가리키는 symbolic link를 유지했다. 이 링크와 원시 데이터는 Git 추적 대상이 아니다. 공개 가능한
집계와 비식별 label은 `result/` 및 `ablation/cares_jmir_rq/`에 있다.

추가 target 40개 파일럿은 다음 위치에 분리했다.

```text
/data1/users/ljk98/Red-persona-artifacts/target_model_pilot40/
├── gpt6_luna/               # Batch campaign, dialogue/no-dialogue run
├── llama31_8b_instruct/     # local-vLLM campaign, dialogue/no-dialogue run
└── evaluations/cares_jmir/  # target별 Batch checkpoint와 상세 평가 row
```

원문 target 응답과 evaluator 설명은 Git에 넣지 않고, 논문용 aggregate와 hash 기반 label만
`result/target_model_pilot40/`에 공개한다.
