# RELATED_WORK — Related Work 작성 자료

RED-Persona 논문의 Related Work를 쓰기 위한 문헌 분석, 설계 문서, 참고문헌.

| 파일 | 내용 |
|---|---|
| [`RELATED_WORK_STRATEGY_KO.md`](RELATED_WORK_STRATEGY_KO.md) | 첨부 논문 2편(PCSA, JARGON) 정밀 분석(§2), 3자 비교표(§4), **Related Work 소절별 설계(§14)**, 게재처 검증 참고문헌(§18), 주장→근거 매핑(§19), 문헌 조사 영향(§20), **유사 연구 지도(§22)**, **JMIR goal 데이터와 persona 풀의 출처 계보(§23)** |
| [`references_related_work.bib`](references_related_work.bib) | 전체 BibTeX (93건, 게재처 검증 결과 반영) |

- Introduction 설계는 [`../INTRO/`](../INTRO/)에 있다.
- 마스터 문서(전체 합본): [`../persona_redteam/docs/PAPER_POSITIONING_AND_WRITING_STRATEGY_KO.md`](../persona_redteam/docs/PAPER_POSITIONING_AND_WRITING_STRATEGY_KO.md)
- 섹션 번호(`§N`)는 마스터 문서 기준이며 두 폴더에서 동일하다.

## 참고문헌 등급 (§18)

- **A**: 주요 학회 본회의·데이터셋 트랙, 저널 · **B**: Findings·워크숍 · **C**: arXiv·기업 블로그·보고서만 확인
- `PCSA`는 EMNLP 2026 Findings, `JARGON`은 ACL 2026 main이다.
- 게재처를 찾지 못한 최신 정신건강 평가 문헌 다수는 C등급이므로 주장의 기둥으로 쓰지 않는다.

## 데이터 출처 주의 (§23)

JMIR 벤치마크 유래 625 goal은 **혼합 성격의 공개 데이터셋 12종**에서 왔다. "실제 사용자 발화 625개"라고 쓰지 않는다.
