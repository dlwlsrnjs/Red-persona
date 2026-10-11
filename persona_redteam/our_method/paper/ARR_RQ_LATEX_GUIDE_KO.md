# ARR RQ 실험·결과 LaTeX 사용 안내

본문 파일:

`our_method/paper/arr_rq_experiments_results.tex`

ACL/ARR 메인 파일의 preamble에 다음 패키지를 추가한다.

```latex
\usepackage{booktabs}
```

실험 및 결과 절을 넣을 위치에서 다음과 같이 불러온다.

```latex
\input{our_method/paper/arr_rq_experiments_results}
```

파일은 다음 네 RQ로 구성되어 있다.

1. RQ1: GPT-4o와 Qwen에서의 cross-target effectiveness
2. RQ2: 타깃에 대한 GOAL 원문 직접 노출의 필요성
3. RQ3: 사전 생성 페르소나 대화 이력의 기여
4. RQ4: HarmBench, Qwen3Guard, Nemotron 간 결과 일관성

조건 명칭은 다음과 같이 통일했다.

- `OURS-Full`: 원문 명시+이력. 사전에 고정된 GPT-4o 주 조건
- `OURS-Latent`: 원문 비공개+이력
- `OURS-Streamlined`: 원문 비공개+이력 없음. 관측상 최적 ablation

주의할 점:

- RQ 구조는 완료된 고정 6셀 행렬을 논문에서 설명하기 위한 조직 방식이다.
- 프롬프트, 주 조건과 주 지표는 전체 평가 전에 고정됐지만, RQ 문구 자체나
  `OURS-Streamlined`의 우수성을 사전등록했다고 쓰지 않는다.
- 대응 McNemar 검정은 Holm 보정 후 유의하지 않았다. 따라서 ablation 차이는
  `observed trend`로 기술한다.
- 기존 64건 베이스라인과 Final-197은 평가 집합이 다르므로 정식 순위나 SOTA 주장을
  하지 않는다.
- 외부 베이스라인을 동일 197건·동일 Best-of-4 예산으로 실행하면 마지막 단락을
  동일 조건 비교 결과로 교체할 수 있다.

이 서버에는 `pdflatex`, `latexmk`, `chktex`가 설치되어 있지 않아 PDF 컴파일 검사는
수행하지 못했다. 대신 LaTeX 환경의 begin/end 수, 표 열 수와 저장소 diff 형식을
검사했다.
