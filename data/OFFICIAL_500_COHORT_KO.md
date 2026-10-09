# RED-Persona 공식 500개 분석 cohort

## 공식 파일

- membership: `data/red_persona_official_500.jsonl`
- selection audit: `data/red_persona_official_500.audit.json`
- 상세 방법: `persona_redteam/docs/SELECTION_500_AUDIT_KO.md`

논문 본 분석, Batch 실행, ablation은 이 JSONL의 500개 `case_id`를 공식 분모로 사용한다.
실행용 selection checkpoint가 있더라도 membership은 이 Git-tracked index와 일치해야 한다.

## 어디에서 시작된 500개인가

이 cohort의 출발점은 JMIR *Between Help and Harm* 저자 공개 test 입력이다. 공개 입력
2,046개에서 6개 정신건강 위기 범주 813개를 남기고, 1인칭 client 발화 652개와 최소 10단어
goal 625개를 순차적으로 정제했다. 이 625개 goal에 pathology route를 연결하고, persona pool
검색·Qwen reranking과 sample adaptation을 거쳐 Lexi prior history를 생성했다. 따라서 아래
625개는 단순 원문 행이 아니라, **JMIR 기반 goal 샘플에서 시작해 goal–pathology–persona–history를
종합한 생성 후보군**이다. 공식 500개는 바로 이 후보군을 다시 검사하고 추린 부분집합이다.

## 625개에서 500개로 줄인 이유와 방법

위 계보로 만든 persona-history 후보는 625개였다. 이 중 private goal 전체 문장이 target-visible prior
history에 그대로 노출된 17개를 자동 검출하고 사람이 위치와 제외 사유를 확인했다. 이 사례는
정답 복사를 추론 성공으로 오인하게 하므로 분석에서 제외했다. 남은 유효 후보는 608개다.

608개 중 suicidal ideation이 287개로 단일 과대표집 범주였다. 목표 분석 규모 500개를 맞추기
위해 필요한 108개를 이 범주에서만 보류했다. 다른 다섯 범주의 유효 사례는 모두 유지했다.
기존에 생성·평가가 끝난 유효 250개는 그대로 보존하고, 추가 사례는 범주 안의 canonical source
order로 선택했다. 관측된 target/evaluator 성능은 선택에 전혀 사용하지 않았다.

이 절차는 여섯 범주를 똑같은 수로 만드는 equal allocation이 아니다. **한 범주가 원래
과대표집되어 있었기 때문에 그 범주의 초과분만 결정적으로 줄인 것**이다. 중복 oversampling,
합성 사례 추가, 결과 기반 cherry-picking은 하지 않았다.

## 공식 분포

| crisis category | 유효 608 | 공식 500 | 보류 |
|---|---:|---:|---:|
| suicidal ideation | 287 | 179 | 108 |
| anxiety crisis | 174 | 174 | 0 |
| substance abuse or withdrawal | 65 | 65 | 0 |
| self-harm | 63 | 63 | 0 |
| violent thoughts | 12 | 12 | 0 |
| risk-taking behaviours | 7 | 7 | 0 |
| **합계** | **608** | **500** | **108** |

17개 무결성 손상 사례는 이 표의 유효 608에 포함되지 않는다. 보류 108개는 손상되거나 품질이
낮다는 뜻이 아니며, 과대표집 범주 downsampling으로 본 분석에서만 제외된 유효 사례다.

## 재현과 검증

공식 index는 500행이어야 하며, `case_id`는 모두 고유해야 한다. 현재 SHA-256은 다음과 같다.

- official index JSONL: `2163b518bbc1a266f83c27c3dea5c0f6a7edc3ac7671cb7ee7a75ac143d61f43`
- official case-ID sequence: `69a3b3368caf27c66bf0f24953cb7375219c5d9e72d77a43aac56fd24f77fb5d`
- audit JSON: `07417a6e0d564149d52f04857fbb48613337225d79e7e681f144e1b18f738f3a`

실행 환경의 active-case 파일과 selection checkpoint가 준비된 뒤 다음 명령으로 공식 파일을
재생성하고 checksum을 비교할 수 있다.

```bash
cd persona_redteam
python -m pipeline.export_official_selection
```

## 논문용 권장 문구

> We screened all 625 generated persona-history cases for pipeline integrity and excluded 17 cases in
> which the complete private goal appeared verbatim in target-visible history. Among the remaining 608
> valid cases, suicidal-ideation cases were overrepresented (287/608). We therefore retained all valid
> cases from the other five crisis categories and deterministically downsampled 108 suicidal-ideation
> cases using within-category canonical source order, yielding an official 500-case analysis cohort.
> Previously completed valid cases were retained, and no observed model outcome was used for selection.

“사람이 품질이 좋아 보이는 500개를 골랐다”, “108개도 손상되어 제거됐다”, “범주별로 같은
수를 뽑았다”라고 쓰면 안 된다.
