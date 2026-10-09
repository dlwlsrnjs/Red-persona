# 최종 500개 분석 집합 정제 및 사람 검수 기록

> 상태: 공식 500개 사례 ID 확정, 추가 250개 생성·평가는 진행 중
>
> 기준일: 2026-10-09

이 문서는 JMIR 공개 test 입력에서 출발해 goal 선별, pathology 연결, persona adaptation,
Lexi prior-history 생성을 거쳐 종합한 625개 생성 후보에서 왜 500개 분석 집합을 만들었는지,
무엇을 “손상된 사례”로 정의했는지, 자동 검사와 사람 검수를 어떻게 결합했는지 기록한다.
500개는 단순히 앞의
500개를 잘라 만든 집합이 아니다. 실험의 blind 조건을 훼손하는 사례를 먼저 제외하고,
유효성 검사를 통과한 사례만으로 정확히 500개를 구성한 quality-controlled subset이다.

상위 계보는 `DATA_LINEAGE_AND_EXTRACTION_KO.md`에 고정돼 있다. 요약하면 JMIR 원천 2,046개
→ 6개 위기 범주 813개 → 1인칭 client 발화 652개 → 최소 10단어 goal 625개 → pathology와
persona-history가 결합된 625개 후보다. 즉 이 단계에서 새로운 외부 goal을 추가한 것이 아니라,
앞 단계에서 종합한 동일 후보군을 무결성과 과대 분포 기준으로 다시 정제했다.

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

17개를 제외하면 유효 후보는 608개다. 이 중 suicidal ideation이 287개(47.2%)로 단일
과대표집 범주였다. 500개로 줄이는 데 필요한 108개를 이 범주에서만 보류하고, 다른 다섯
범주의 유효 사례는 모두 유지하는 결정적 downsampling을 적용했다.

1. 현재 4방향 계약으로 생성·평가가 검증된 250개는 재호출하지 않고 고정했다.
2. 유효 608개의 범주 분포에서 가장 큰 suicidal ideation을 과대표집 범주로 식별했다.
3. anxiety, self-harm, substance, violent thoughts, risk-taking의 유효 사례는 모두 포함했다.
4. suicidal ideation은 기존 완료 122개를 유지하고, 아직 사용하지 않은 사례를 해당 범주 안의
   canonical source order로 57개 추가하여 최종 179개로 제한했다.
5. 이에 따라 추가 250개와 기존 250개의 합집합이 정확히 500개가 되도록 했다.
6. 보류된 108개가 모두 suicidal ideation이며, 어떤 관측 모델 결과도 선택에 사용되지 않았는지
   확인했다.

이 방식은 여섯 범주를 같은 수로 만드는 완전 균형 표집이 아니다. 608개에서 한 범주만
명백하게 과다했기 때문에 그 범주의 초과분만 줄이고, 희소 범주를 복제하거나 새로 생성하지
않은 **single-overrepresented-category downsample cohort**다. 범주 안에서는 canonical 순서를
사용했으므로 관측된 model success나 연구자의 사례별 선호가 선택에 개입하지 않는다.

## 7. 최종 500개 범주 분포

| crisis category | 최종 500개 | 비율 |
|---|---:|---:|
| suicidal ideation | 179 | 35.8% |
| anxiety crisis | 174 | 34.8% |
| self-harm | 63 | 12.6% |
| substance abuse or withdrawal | 65 | 13.0% |
| violent thoughts | 12 | 2.4% |
| risk-taking behaviours | 7 | 1.4% |

보류된 유효 108개는 모두 과대표집된 suicidal ideation 범주다. 다른 다섯 범주의 유효 사례는
전부 포함했다. 이는 희소 범주를 중복 oversampling한 것이 아니라, 실제 존재하는 고유 사례를
그대로 유지한 것이다.

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
| execution selection checkpoint | 500 최종 ID 포함 | `6e5e2eefb273a8f80f9831bca832ba52b11f10801bcc637dca5a433eba03d7e6` |
| Git 공식 500 index JSONL | 500 | `2163b518bbc1a266f83c27c3dea5c0f6a7edc3ac7671cb7ee7a75ac143d61f43` |
| Git 공식 500 audit JSON | 1 | `07417a6e0d564149d52f04857fbb48613337225d79e7e681f144e1b18f738f3a` |
| 기존 유효 ID 목록 | 250 | `79477226836e2ad5f8d612a71c669d4f5cd958a84d54676222a8438da5ffb3d9` |
| 신규 adjusted-fill ID 목록 | 250 | `310828e787b03e033f45a6ea65372f8c26aaaacdc41c4e23536aaa8f384ca9fa` |
| 공식 500 ID 목록 | 500 | `69a3b3368caf27c66bf0f24953cb7375219c5d9e72d77a43aac56fd24f77fb5d` |
| 보류 ID 목록 | 108 | `2e5c4af3b0390f65edbf3d725c290ce9cc7ef96b615d2412c0f26cd87540246a` |

ID 목록 hash는 case ID를 canonical/사전식 순서로 정렬하고 각 ID 뒤에 newline을 붙인 UTF-8
문자열의 SHA-256이다. 실행 checkpoint와 생성·평가 결과는 Git 밖에 두지만, 공식 cohort
index와 audit은 저장소 `data/red_persona_official_500.*`에 포함한다. index에는 private goal이나
persona 본문이 없고 ID, category, canonical 위치, selection role만 있다.

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
유효 608개 중 suicidal ideation이 287개로 과대표집되어 있었으므로, 다른 다섯 범주의 유효
사례는 모두 유지하고 이 범주에서만 108개를 결정적으로 downsample하였다. 기존 완료 사례는
모두 유지했으며, 추가 suicidal ideation 사례의 선택과 보류에는 범주 내부 canonical source
order를 사용했다. 모델 출력은 선택에 사용하지 않았다. 이 절차로 500개 고유 사례를 구성하고
최종 ID와 선택 역할을 Git의 공식 cohort index에 고정하였다.

## 10. 보고 시 금지할 표현

- “625개 중 품질이 가장 좋은 500개를 사람이 주관적으로 골랐다”
- “108개도 손상되어 제외됐다”
- “500개 전체 응답을 임상 전문가가 전수 annotation했다”
- “500개는 무작위·모집단 비례·범주별 동일 수 표본이다”
- “17개 원본 데이터가 잘못됐다”

정확한 표현은 **“17개의 실험 무결성 손상 사례를 자동 검출하고 사람이 제외 사유를
검수한 뒤, 유효 608개에서 단일 과대표집 범주인 suicidal ideation만 108개 downsample하여
500개 cohort를 구성했다”**이다.
