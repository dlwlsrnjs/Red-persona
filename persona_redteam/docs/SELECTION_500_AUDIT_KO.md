# 최종 500개 분석 집합 정제 및 사람 검수 기록

> 상태: 범주 균형화 500개 사례 ID 선택 완료, 추가 250개 생성·평가는 진행 중
>
> 기준일: 2026-10-09

이 문서는 625개 생성 후보에서 왜 500개 분석 집합을 만들었는지, 무엇을 “손상된 사례”로
정의했는지, 자동 검사와 사람 검수를 어떻게 결합했는지 기록한다. 500개는 단순히 앞의
500개를 잘라 만든 집합이 아니다. 실험의 blind 조건을 훼손하는 사례를 먼저 제외하고,
유효성 검사를 통과한 사례만으로 정확히 500개를 구성한 quality-controlled subset이다.

## 1. 정제 결과 요약

```text
전체 persona-history 후보                         625
  - private goal 원문이 target-visible history에 노출  17
                                                    ---
자동 계약을 통과한 유효 후보                       608
  - 현재 분석 범위 밖으로 보류한 유효 후보             108
                                                    ---
최종 선택 사례                                     500
  = 이미 생성·평가를 검증한 사례                      250
  + Batch로 추가할 신규 유효 사례                     250
```

중요하게도 108개는 손상되거나 품질이 낮아서 제외한 것이 아니다. 625개 전체 중 17개만
실험 무결성 훼손으로 제외했으며, 나머지 608개 가운데 사전 정한 분석 규모와 실행 비용에 맞춰
500개를 선택했다. 보류한 108개는 후속 확장 분석에 사용할 수 있다.

## 2. “손상된 사례”의 조작적 정의

이 문서에서 손상은 JSON 파일이 열리지 않는다는 뜻만이 아니다. 본 실험의 인과적·측정적
전제를 깨뜨린 상태를 포함한다. 다음 중 하나라도 발생하면 damaged/invalid case로 정의한다.

1. private goal 정답 문장이 target-visible persona 또는 prior dialogue에 그대로 복사됨
2. 마지막 누적 `persona_state`와 active persona가 불일치함
3. prior dialogue가 4턴 미만이거나 Qwen plan/verification이 모든 turn을 덮지 못함
4. 필수 필드나 provenance가 누락됨
5. 세 조건 × 네 방향의 완전한 행렬을 만들 수 없음
6. target history에 허용되지 않은 system prompt가 섞임
7. manifestation candidate와 research analysis가 분리되지 않음
8. CARES가 정확한 candidate response가 아닌 다른 텍스트를 평가함

현재 625개 active case 검사에서 발견된 17개는 모두 첫 번째 유형이었다. 즉 private goal
전체 문장이 대소문자 정규화 후 target-visible prior history에서 그대로 발견되었다. 다른
형식 손상 유형의 추가 사례는 이 선택 시점에는 없었다.

## 3. 왜 원문 누출 사례를 제외했는가

RED-Persona의 핵심 결과변수는 target이 persona와 누적 대화의 간접 증거로부터 잠재 목표를
복원하는지 여부다. 정답 문장 자체가 history에 보이면 다음 문제가 생긴다.

- target이 추론하지 않고 문자열을 되풀이해도 recovery 성공으로 보일 수 있다.
- neutral과 structural 조건이 사실상 oracle 조건으로 오염된다.
- `target_originated_recovery_success`의 provenance 전제가 무너진다.
- 정상 사례보다 Success@4와 unsafe manifestation이 인위적으로 높아질 수 있다.
- 누출 이후 생성된 모든 target turn이 오염된 context에 의존하므로 마지막 응답만 고쳐서
  복구할 수 없다.

따라서 이 사례들은 텍스트 일부를 사후 삭제해 살리지 않았다. 원본과 실패 사유는 감사용으로
보존하되, 500개 분석 분모와 후속 API 제출 대상에서 제외했다. 다시 사용하려면 persona-history
생성 단계부터 재생성하고 동일 계약을 다시 통과해야 한다.

## 4. 자동 검사와 사람 검수의 이중 절차

### 4.1 1차: 자동 전수 검사

625개 전체를 `pipeline.contracts.validate_active_cases`로 검사했다. 비교는 private goal을
`strip().casefold()`한 뒤 persona와 직렬화된 history의 정규화 문자열에서 전체 문장 일치를
찾는 방식이다. 동시에 active persona derivation, 최소 turn 수, Qwen plan, turn verification,
profile selection과 sample adaptation provenance를 검사했다.

자동 검사 결과는 다음과 같았다.

| 판정 | 사례 수 | 처리 |
|---|---:|---|
| 계약 통과 | 608 | 500개 선택 후보로 유지 |
| private-goal 원문 누출 | 17 | 최종 500개에서 제외 |
| 그 밖의 active-case 계약 실패 | 0 | 해당 없음 |

### 4.2 2차: 연구자 사람 검수

자동 판정을 최종 결정으로 바로 사용하지 않고, 연구자가 다음 항목을 사람이 확인하는 이차
검수를 수행했다.

1. 17개 자동 제외 사례의 case ID와 validator 사유가 일치하는지 확인
2. 누출 위치가 evaluator-only metadata가 아니라 실제 target-visible history인지 확인
3. 기존 완료 run 가운데 같은 손상 사례 7개가 valid-existing count에서 빠졌는지 확인
4. 기존 유효 250개와 신규 250개의 ID가 서로 겹치지 않는지 확인
5. 최종 목록이 정확히 500개이고 duplicate case ID가 없는지 확인
6. 500개 모두 625개 canonical source에 존재하는지 확인
7. 범주별 개수와 선택 manifest의 총계가 맞는지 확인

이 사람 검수는 **제외 판정과 데이터 무결성에 대한 검수**다. 500개 응답의 임상적 적절성을
전문가가 전수 annotation했다는 뜻은 아니다. 응답 수준의 human clinical annotation은 별도의
후속 평가로 보고해야 한다.

## 5. 제외한 17개 사례

민감한 private goal 원문은 이 문서에 재인용하지 않고 ID, 범주, 제외 사유만 남긴다.

| case ID | crisis category | 사람 검수 후 확정한 제외 사유 |
|---|---|---|
| `jmir-full-0008` | suicidal ideation | private goal 원문이 target-visible history에 그대로 존재 |
| `jmir-full-0026` | anxiety crisis | private goal 원문이 target-visible history에 그대로 존재 |
| `jmir-full-0062` | suicidal ideation | private goal 원문이 target-visible history에 그대로 존재 |
| `jmir-full-0110` | anxiety crisis | private goal 원문이 target-visible history에 그대로 존재 |
| `jmir-full-0198` | substance abuse or withdrawal | private goal 원문이 target-visible history에 그대로 존재 |
| `jmir-full-0209` | substance abuse or withdrawal | private goal 원문이 target-visible history에 그대로 존재 |
| `jmir-full-0244` | anxiety crisis | private goal 원문이 target-visible history에 그대로 존재 |
| `jmir-full-0366` | suicidal ideation | private goal 원문이 target-visible history에 그대로 존재 |
| `jmir-full-0433` | suicidal ideation | private goal 원문이 target-visible history에 그대로 존재 |
| `jmir-full-0503` | suicidal ideation | private goal 원문이 target-visible history에 그대로 존재 |
| `jmir-full-0516` | suicidal ideation | private goal 원문이 target-visible history에 그대로 존재 |
| `jmir-full-0521` | suicidal ideation | private goal 원문이 target-visible history에 그대로 존재 |
| `jmir-full-0524` | substance abuse or withdrawal | private goal 원문이 target-visible history에 그대로 존재 |
| `jmir-full-0526` | suicidal ideation | private goal 원문이 target-visible history에 그대로 존재 |
| `jmir-full-0529` | suicidal ideation | private goal 원문이 target-visible history에 그대로 존재 |
| `jmir-full-0536` | suicidal ideation | private goal 원문이 target-visible history에 그대로 존재 |
| `jmir-full-0541` | suicidal ideation | private goal 원문이 target-visible history에 그대로 존재 |

제외 범주 분포는 suicidal ideation 11, anxiety crisis 3, substance abuse or withdrawal 3이다.
self-harm, violent thoughts, risk-taking behaviours에서는 이 유형의 제외가 없었다.

## 6. 유효 608개 중 최종 500개를 고른 방법

17개를 제외하면 유효 후보는 608개다. 여기서 임의로 108개를 “품질 불량”으로 판정하지
않았으며, 이미 완료된 첫 250개의 범주 편중을 뒤 250개가 최대한 보정하도록 결정적
capacity-constrained category balancing을 적용했다.

1. 현재 4방향 계약으로 생성·평가가 검증된 250개는 재호출하지 않고 고정했다.
2. 유효 608개의 `crisis_label`별 공급량과 기존 250개의 범주별 완료 수를 계산했다.
3. 기존 완료 수를 각 범주의 하한, 유효 공급량을 상한으로 두었다.
4. 남은 슬롯을 현재 최종 수가 가장 작은 비고갈 범주에 한 개씩 배정하는 water-filling 규칙을
   사용했다. 이는 가용 샘플을 중복·생성하지 않는 범위에서 최종 범주 수 차이를 최소화한다.
5. 산출된 범주별 신규 수만큼 아직 사용하지 않은 유효 사례를 canonical source order로
   선택했다. 따라서 난수나 결과값을 선택에 사용하지 않았다.
6. 기존 250개와 신규 250개의 합집합이 정확히 500개이고, 남은 유효 사례가 정확히 108개인지
   확인했다.

초기 canonical-order 선택은 범주 층화가 아니어서 폐기했다. 범주 균형화로 전환하면서 신규
목록의 81개를 빼고 부족 범주의 81개를 넣었으며, 기존 완료 250개는 바꾸지 않았다. 최종
집합은 random sample도 모집단 비례 표본도 아니다. **첫 250개의 편중을 뒤 250개가 가능한
최대로 보정한 deterministic capacity-constrained balanced subset**이다. 희소 범주는 유효
사례를 전부 포함해도 동일한 표본 수에 도달할 수 없으므로 완전한 equal allocation은 불가능하다.

## 7. 최종 500개 범주 분포

| crisis category | 최종 500개 | 비율 |
|---|---:|---:|
| suicidal ideation | 179 | 35.8% |
| anxiety crisis | 174 | 34.8% |
| self-harm | 63 | 12.6% |
| substance abuse or withdrawal | 65 | 13.0% |
| violent thoughts | 12 | 2.4% |
| risk-taking behaviours | 7 | 1.4% |

보류된 유효 108개는 모두 공급량이 가장 많고 첫 250개에도 가장 많이 포함된 suicidal
ideation 범주다. 다른 다섯 범주의 유효 사례는 모두 최종 500개에 포함된다.

| crisis category | 유효 608 | 기존 완료 | 신규 선택 | 최종 500 | 보류 108 |
|---|---:|---:|---:|---:|---:|
| suicidal ideation | 287 | 122 | 57 | 179 | 108 |
| anxiety crisis | 174 | 76 | 98 | 174 | 0 |
| self-harm | 63 | 18 | 45 | 63 | 0 |
| substance abuse or withdrawal | 65 | 28 | 37 | 65 | 0 |
| violent thoughts | 12 | 4 | 8 | 12 | 0 |
| risk-taking behaviours | 7 | 2 | 5 | 7 | 0 |
| **합계** | **608** | **250** | **250** | **500** | **108** |

## 8. 재현용 무결성 값

아래 hash는 파일 내용이나 정렬된 ID 목록이 바뀌었는지 확인하기 위한 감사 값이다.

| 대상 | 사례 수 | SHA-256 |
|---|---:|---|
| active-case 파일 | 625 | `e2ed9f9bc869070dddbc1d6eb362152132ce9d0a3b936381f35f6c7c760f94d2` |
| category-balanced selection checkpoint | 500 최종 ID 포함 | `065e148226a005008304a4aae903378b9347a0578b171aae5105615352d0ae30` |
| 기존 유효 ID 목록 | 250 | `79477226836e2ad5f8d612a71c669d4f5cd958a84d54676222a8438da5ffb3d9` |
| 신규 ID 목록 | 250 | `310828e787b03e033f45a6ea65372f8c26aaaacdc41c4e23536aaa8f384ca9fa` |
| 최종 정렬 ID 목록 | 500 | `69a3b3368caf27c66bf0f24953cb7375219c5d9e72d77a43aac56fd24f77fb5d` |
| 보류 ID 목록 | 108 | `2e5c4af3b0390f65edbf3d725c290ce9cc7ef96b615d2412c0f26cd87540246a` |

ID 목록 hash는 case ID를 사전식 정렬하고 각 ID 뒤에 newline을 붙인 UTF-8 문자열의
SHA-256이다. selection checkpoint와 생성·평가 결과는 민감성 및 용량 때문에 Git 밖의 실행
artifact로 유지하지만, 이 문서의 count와 hash로 최종 목록의 변화를 탐지할 수 있다.

## 9. 논문에 사용할 수 있는 정제 방법 문단

초기 625개 persona-history 사례 전체에 대해 자동 무결성 검사를 수행하고, 그 결과를 연구자가
이차 검수하였다. 검사는 active persona가 마지막 누적 persona state에서 파생되었는지, 최소
대화 길이와 Qwen 계획·turn 검증 계약을 만족하는지, 필수 provenance가 존재하는지, 그리고
private goal 원문이 target-visible persona 또는 history에 노출되지 않았는지를 확인하였다.
17개 사례에서 private goal 전체 문장이 target-visible prior history에 그대로 포함된 것을
확인하였다. 이 사례들은 잠재 목표 복원을 실제 추론이 아닌 문자열 재현으로 과대평가하고
neutral/structural 조건을 오염시킬 수 있으므로 손상 사례로 분류해 제외하였다.

자동 제외 목록, 누출 위치, 기존 run과의 교차 일치, ID 중복, 범주별 총계는 연구자가 수동으로
재확인하였다. 17개를 제외한 608개 유효 후보 중 이미 생성·평가가 완료된 250개를 유지하고,
기존 완료 수를 범주별 하한, 유효 공급량을 상한으로 둔 water-filling 배정을 수행하였다. 각
범주 안에서는 canonical source order를 유지해 아직 사용하지 않은 유효 사례 250개를 추가하고
최종 분석 목표인 500개를 구성하였다. 이 절차는 첫 250개의 범주 편중을 가용 자료 범위에서
최대한 보정한다. 나머지 108개는 품질 문제가 아니라 최다 범주인 suicidal ideation의 초과
공급분이며, 후속 확장 분석용으로 보류하였다.

## 10. 보고 시 금지할 표현

- “625개 중 품질이 가장 좋은 500개를 사람이 주관적으로 골랐다”
- “108개도 손상되어 제외됐다”
- “500개 전체 응답을 임상 전문가가 전수 annotation했다”
- “500개는 무작위·모집단 비례 표본이다” 또는 “여섯 범주에서 같은 수를 뽑았다”
- “17개 원본 데이터가 잘못됐다”

정확한 표현은 **“17개의 실험 무결성 손상 사례를 자동 검출하고 사람이 제외 사유를
검수한 뒤, 기존 완료 사례를 유지하면서 뒤 250개를 부족 범주에 우선 배정해 가용 범위에서
최종 범주 편중을 최소화한 500개를 구성했다”**이다.
