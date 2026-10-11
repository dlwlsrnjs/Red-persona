# GPT-4o GOAL 원문 노출 대응 파일럿 결과

고정한 동일 10건에 대해 페르소나·대화 이력·7단계 연구 대화·네 최종 분기·평가기와
타깃 모델(`gpt-4o-2024-11-20`)을 동일하게 유지했다. 등록된 조건 차이는 초기
persona packet에 `original_request` 원문 블록을 추가하는지 여부뿐이다.

| 지표 | 원문 비공개 | 원문 명시 | 명시−비공개 |
|---|---:|---:|---:|
| CARES A/C/R/NR | 2/0/8/0 | 2/0/8/0 | — |
| CARES Accept | 20.0% | 20.0% | +0.0%p |
| CARES ASR | 20.0% | 20.0% | +0.0%p |
| CARES SS | 0.800 | 0.800 | +0.000 |
| JMIR mean | 1.133 | 1.000 | -0.133 |
| JMIR exact-1 | 90.0% | 100.0% | +10.0%p |
| R3+@4 | 90.0% | 50.0% | -40.0%p |
| B4+@4 | 10.0% | 10.0% | +0.0%p |
| R3+∧B4+@4 | 10.0% | 10.0% | +0.0%p |
| HarmBench+@4 | 20.0% | 20.0% | +0.0%p |
| R3+∧B4+∧HarmBench+@4 | 10.0% | 10.0% | +0.0%p |
| 보조 R2+∧B3+∧HarmBench+@4 | 10.0% | 10.0% | +0.0%p |
| Qwen3Guard Unsafe@4 | 20.0% | 30.0% | +10.0%p |
| Qwen3Guard Unsafe-or-Controversial@4 | 30.0% | 30.0% | +0.0%p |
| R3+∧B4+∧Qwen3Guard Unsafe@4 | 0.0% | 10.0% | +10.0%p |
| Nemotron Response Unsafe@4 | 30.0% | 30.0% | +0.0%p |
| Nemotron SSH-positive@4 | 20.0% | 30.0% | +10.0%p |
| Nemotron domain-risk@4 | 30.0% | 30.0% | +0.0%p |
| R3+∧B4+∧Nemotron domain-risk@4 | 0.0% | 10.0% | +10.0%p |
| 보조 R2+∧B3+∧Nemotron domain-risk@4 | 0.0% | 10.0% | +10.0%p |

두 조건 모두 생성 10/10, 네 분기 40/40, CARES/JMIR 40/40, 행동복원 40/40,
HarmBench, Qwen3Guard와 Nemotron은 각각 40/40을 완료했다. 세 평가기의 파싱 실패와
private GOAL 누출은
양쪽 모두 0이다. 표의 R/B 및 결합 수치는 최신 `recovery_behavior.json`을 기존
안전성 판정과 사례·분기 ID로 다시 연결한 결과다.
8개 실행 lane은 각각 3/3/2/2건으로 완료됐고 두 조건의 case ID와 순서는 같다.

이 10건에서는 GOAL 원문 명시가 CARES, HarmBench 또는 HarmBench 엄격 결합 수치를
높이지 않았다. Qwen3Guard Unsafe와 Qwen3Guard 엄격 결합은 각각 10%p 높았고,
원문 비공개 조건의 R3+는 40%p 높았다. 표본이
10건이므로 이 차이는 진단 결과이며 197건 전체 성능이나 통계적 우월성으로 해석하지
않는다.

Qwen3Guard는 HarmBench를 대체하는 주 평가기가 아니라 응답 안전성과 거부를 보는 독립
보조 축이다. Nemotron도 독립적인 보조 응답 안전성 축이며, 세 분류기의 양성 합집합을
ASR로 보고하지 않는다. Nemotron의 `Safety Categories`는 user/response 중 하나라도
unsafe일 때 제시되는 대화 단위 범주다. 따라서 `SSH-positive`와 `domain-risk`는
`Response Safety: unsafe`인 응답에 해당 대화 범주가 함께 있는 경우로 제한했지만,
범주 자체를 응답 전용 라벨로 해석하지 않는다.

`원문 비공개` 조건 역시 GOAL에 맞춰 생성된 페르소나와 대화 이력을 유지한다. 따라서
이 비교는 GOAL 정보 전체의 유무가 아니라 **원문 직접 노출의 추가 효과**를 측정한다.
