# 최종 500개 분석 집합 정제 및 사람 검수 기록

> 상태: 500개 사례 ID 선택 완료, 추가 250개 생성·평가는 진행 중
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
않았다. 다음과 같은 결정적 선택 절차를 사용했다.

1. 이미 현재 4방향 계약으로 생성·평가가 검증된 250개를 고정했다.
2. 625개 canonical 입력 순서를 유지했다.
3. 기존 250개와 17개 손상 사례를 건너뛰었다.
4. 아직 사용하지 않은 유효 사례를 stable source order로 250개 선택했다.
5. 기존 250개와 신규 250개의 합집합이 정확히 500개인지 확인했다.
6. 나머지 유효 108개는 삭제하지 않고 후속 확장용으로 보류했다.

따라서 최종 500개는 random sample이나 category-stratified sample이 아니다. 기존에 완료된
유효 사례를 보존하면서 canonical order로 채운 deterministic quality-controlled subset이다.
논문에서 무작위 표집 또는 범주 균형 표집이라고 표현해서는 안 된다.

## 7. 최종 500개 범주 분포

| crisis category | 최종 500개 | 비율 |
|---|---:|---:|
| suicidal ideation | 260 | 52.0% |
| anxiety crisis | 130 | 26.0% |
| self-harm | 52 | 10.4% |
| substance abuse or withdrawal | 39 | 7.8% |
| violent thoughts | 12 | 2.4% |
| risk-taking behaviours | 7 | 1.4% |

보류된 유효 108개는 anxiety crisis 44, self-harm 11, substance abuse or withdrawal 26,
suicidal ideation 27이다. violent thoughts와 risk-taking behaviours의 유효 사례는 최종 500개에
모두 포함되었다.

## 8. 재현용 무결성 값

아래 hash는 파일 내용이나 정렬된 ID 목록이 바뀌었는지 확인하기 위한 감사 값이다.

| 대상 | 사례 수 | SHA-256 |
|---|---:|---|
| active-case 파일 | 625 | `e2ed9f9bc869070dddbc1d6eb362152132ce9d0a3b936381f35f6c7c760f94d2` |
| corrected selection checkpoint | 250 신규 | `ca6956957184f171cd92cc035af303624d0c19078b26f66dc3de7982b0577609` |
| 기존 유효 ID 목록 | 250 | `79477226836e2ad5f8d612a71c669d4f5cd958a84d54676222a8438da5ffb3d9` |
| 신규 ID 목록 | 250 | `fef58b02375f2f3ed61dd05ad06d139e00449ba516207a709cea4a074b3b2fc5` |
| 최종 정렬 ID 목록 | 500 | `7b1a366f28e67ec0d21537b5b94c116d31036ef0386740dafc92c08b5684ed84` |

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
canonical source order에서 아직 사용하지 않은 유효 사례 250개를 추가하여 최종 분석 목표인
500개를 구성하였다. 나머지 108개는 품질 문제로 제외한 것이 아니라 사전 정한 분석 규모와
실행 비용에 따라 후속 확장 분석용으로 보류하였다.

## 10. 보고 시 금지할 표현

- “625개 중 품질이 가장 좋은 500개를 사람이 주관적으로 골랐다”
- “108개도 손상되어 제외됐다”
- “500개 전체 응답을 임상 전문가가 전수 annotation했다”
- “500개는 무작위 또는 범주 균형 표본이다”
- “17개 원본 데이터가 잘못됐다”

정확한 표현은 **“17개의 실험 무결성 손상 사례를 자동 검출하고 사람이 제외 사유를
검수한 뒤, 남은 유효 후보에서 결정적 순서로 500개를 구성했다”**이다.
