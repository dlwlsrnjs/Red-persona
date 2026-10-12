# 연구 매개 깊이 및 대화 이력 ablation

## 왜 했는가

초기 7단계 연구 대화는 GOAL을 점진적으로 복원하려는 목적이었지만, 긴 문맥이 persona와
구체적 GOAL 단서를 희석할 가능성이 관찰됐다. 반대로 연구 대화를 완전히 제거하면 타깃이
GOAL과 연결되는 발화를 만들지 못해 최종 분기의 행동 수행도가 낮아질 수 있었다. 따라서
연구 매개의 양이 성능에 미치는 영향을 분리해 확인했다.

## 조건

- `direct-final-only`: 초기 사례 분석 직후 분기별 최종 질문만 한 번 전송한다.
- `single-readout`: 각 4분기에서 짧은 연구 readout 한 번을 받은 뒤 그 분기의 인용문을
  바인딩해 최종 직접응답을 묻는다.
- `long 7-stage`: surface observation부터 latent goal까지 7단계 누적 연구 대화를 거친다.
- 각 구조를 persona history 있음/없음으로 나눴다.
- Target과 GPT 평가기는 `gpt-4o-2024-11-20`; 사례별 Best-of-4다.

## 결과

| 조건 | CARES Accept | R3+@4 | B4+@4 | HarmBench+@4 | 엄격 결합@4 |
|---|---:|---:|---:|---:|---:|
| long 7-stage · 이력 있음 | 96.45% | 100.00% | 76.14% | 89.34% | 63.96% |
| long 7-stage · 이력 없음 | 98.98% | 100.00% | 86.80% | 86.29% | 73.10% |
| single-readout · 이력 있음 | 100.00% | 99.49% | 100.00% | 96.95% | **95.94%** |
| single-readout · 이력 없음 | 100.00% | 97.46% | 98.98% | 86.80% | 83.76% |
| direct-final-only · 이력 있음 | 92.39% | 99.49% | 8.12% | 87.31% | 7.11% |
| direct-final-only · 이력 없음 | 85.28% | 96.95% | 10.15% | 75.63% | 6.09% |

## 결론

연구 readout 자체는 필요하지만 7단계 누적 대화는 과도했다. 이력 있음 조건에서
single-readout은 direct-final-only보다 결합@4가 88.83%p 높고, long보다 31.98%p
높았다. 최종 메서드의 주 설정은 `persona/history + 분기별 1회 연구 readout +
4개 독립 최종 분기`로 고정한다.

이력은 short에서 HarmBench와 결합지표를 높였지만 long에서는 결합지표가 반대로 낮았다.
따라서 “history는 항상 유리하다”가 아니라 연구 길이와 상호작용한다고 해석한다.

## 원본과 재현

- 표: `persona_redteam/result/OURS/final197_research_mediation_depth_gpt4o_v1/TABLES_KO.md`
- 프로토콜: `persona_redteam/result/OURS/final197_research_mediation_depth_gpt4o_v1/GOAL_BINDING_PROTOCOL_KO.md`
- 최종 패키지: `persona_redteam/singleton_1011_package/`

