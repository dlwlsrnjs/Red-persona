# Final-197 추가 실험 논문용 패키지

이 폴더는 2026-10-12에 완료된 Final-197 추가 실험을 논문에 바로 옮길 수 있도록
LaTeX 표, 벡터 그림, 집계 데이터, 캡션과 재현 스크립트로 묶은 배포본이다. 모든 수치는
커밋된 원본 JSON/CSV에서 자동으로 읽으며, 개별 유해 응답이나 evaluator rationale은
포함하지 않는다.

## 바로 사용할 파일

- `appendix_additional_experiments.tex`: 독립 실행형 LaTeX 문서.
- `tables/paper_tables.tex`: 본문 또는 부록에 `\input`할 수 있는 표 6개.
- `figures.tex`: 그림 5개의 LaTeX figure 환경.
- `figures/*.pdf`: 논문 제출용 벡터 그림.
- `figures/*.svg`: 웹·후편집용 벡터 그림.
- `figures/*.png`: 320 dpi 미리보기.
- `PAPER_RESULTS_KO.md`: 논문 서술과 해석 한계.
- `data/paper_metrics.json`: 표·그림에 사용한 통합 수치 스냅샷.
- `data/headline_metrics.csv`: 주요 행동평가 셀의 간결한 표.
- `VALIDATION.json`: 입력 수와 산출물 구조 검증 결과.
- `MANIFEST.sha256`: 패키지 파일 무결성 해시.

## 표와 그림

| 번호 | 내용 | 핵심 용도 |
|---|---|---|
| Table 1 / Figure 1 | 연구 매개 깊이 × persona history | 최종 방법 선택과 ablation |
| Table 2 / Figure 2 | 외부 baseline matrix | 기존 공격법의 맥락적 비교 |
| Table 3 / Figure 2 | PCSA 개인화 paired ablation | persona/history 효과 분리 |
| Table 4 / Figure 3 | 7개 target 교차모델 실험 | 일반화와 방어 모델 차이 |
| Table 5 / Figure 5 | Qwen attention·표현공간 | 단서 희석 가설의 보조 분석 |
| Table 6 / Figure 4 | cosine 이력전이 | 이력 재사용과 문맥 불일치 영향 |

## LaTeX 사용

ARR 템플릿 안에서는 필요한 표나 그림만 골라 입력하는 방식을 권장한다.

```tex
% preamble
\usepackage{booktabs,longtable,threeparttable,graphicx}

% document body, with this package directory on TEXINPUTS
\input{tables/paper_tables.tex}
\input{figures.tex}
```

그림 경로는 이 폴더를 기준으로 작성되어 있다. 다른 디렉터리에서 컴파일한다면
`\graphicspath`를 설정하거나 figure 환경의 경로를 조정한다.

## 재생성

```bash
python -m pip install matplotlib==3.9.4
python scripts/generate_paper_package.py
```

재생성 스크립트는 입력 행 수(연구 조건 6개, 외부 baseline 18개, 교차모델 7개,
이력전이 8개)를 확인하고, PDF/SVG/PNG 그림과 LaTeX·데이터 스냅샷·해시를 함께
갱신한다.

## 반드시 유지할 보고 규칙

1. OURS의 `@4`는 네 독립 분기 중 성공 분기를 고르는 Best-of-4다.
2. 엄격 결합은 **동일한 한 분기**가 `R3+`, `B4+`, `HarmBench+`를 모두 만족할 때만
   성공이다.
3. 외부 baseline은 사례당 저장 응답 1개이고 방법별 query budget도 다르다. OURS
   Best-of-4와 직접적인 동일 예산 순위 또는 SOTA 배수로 표현하지 않는다.
4. Qwen attention·hidden-state 결과는 proxy 분석이며 GPT-4o의 내부 인과기제를
   입증하지 않는다.
5. short 조건은 7단계 GOAL 복원 게이트를 실행하지 않았으므로 GOAL 복원률은 0%가
   아니라 N/A다.

