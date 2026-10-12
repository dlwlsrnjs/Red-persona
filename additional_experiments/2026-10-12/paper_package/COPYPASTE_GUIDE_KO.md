# 논문에 그대로 붙이는 방법

## ARR 본문

1. `ARR_PREAMBLE_COPYPASTE.tex`의 패키지와 `\graphicspath`를 논문 preamble에 붙인다.
2. `ARR_RESULTS_SECTION_COPYPASTE.tex` 전체를 본문의 Results 위치에 붙인다.
3. `figures/`의 PDF 다섯 개를 Overleaf의 `figures/` 폴더에 올린다.

본문 파일은 다음 내용을 이미 포함한다.

- 평가 규약과 엄격 결합@4 정의
- 연구 대화 깊이 × history 핵심 표와 그림
- 수치가 포함된 결과 해석
- 7개 target 교차모델 표와 그림
- 부록으로 이어지는 교차참조

## ARR 부록

`ARR_APPENDIX_SECTION_COPYPASTE.tex` 전체를 appendix에 붙인다. 다음 내용이 표·그림·본문
해석까지 완성된 상태로 들어 있다.

- GPT-4o/Qwen 외부 baseline 전체 표
- PCSA Persona+History paired ablation과 McNemar 검정
- Qwen attention·표현공간 proxy 분석과 해석 제한
- cosine 이력전이 전체 8개 셀과 paired bootstrap CI
- query-budget 및 인과 해석 제한

## 복사 후 확인할 것

- 본문에서 부록을 사용하지 않으면 `Appendix~\ref{sec:additional-experiments-appendix}` 문장을
  삭제하거나 해당 논문의 부록 라벨로 바꾼다.
- ARR 템플릿이 이미 `booktabs`, `graphicx`, `xcolor`를 불러왔다면 중복 `\usepackage`는
  한 번만 남긴다.
- Figure PDF 파일명은 바꾸지 않는 것이 가장 간단하다.
- 외부 baseline은 OURS와 query budget이 다르므로 현재 캡션의 주의문을 유지한다.

