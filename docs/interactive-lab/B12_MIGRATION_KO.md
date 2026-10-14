# RED-Persona Interactive Lab — B12 이전 입력문

이 문서는 B12를 논문·방법 소개용 메인 사이트로 사용하면서, 이미 검증된 GitHub Pages 실험 도구를 손상 없이 연결하기 위한 입력문과 설정 절차다.

## 권장 구조

- B12: 연구 소개, 논문 그림, 역할·도구·단계·프로토콜 설명, 실행 진입점
- GitHub Pages: 197개 데이터셋 뷰어, 저장 실험 재생, 실행 트리, Live Lab
- 이유: B12의 외부 사이트 참조 기능은 기존 페이지를 정확히 복제하지 않고 내용을 새 디자인으로 재구성한다. 실험 도구의 상태 머신과 JSON 로더는 기존 배포본을 그대로 연결해야 재현성이 유지된다.

## B12 최초 생성 prompt

아래 내용을 B12 가입 화면의 첫 prompt에 그대로 붙여 넣는다.

```text
Build a research project website named “RED-Persona Interactive Lab” for an academic audience studying persona-conditioned LLM safety evaluation.

Use the existing project at https://dlwlsrnjs.github.io/Red-persona/interactive-lab/ as the factual source. Do not rewrite experimental scores, model names, protocol names, or paper claims. The site should be a clear research portal, not a marketing or medical-service website.

Visual direction:
- dark research-console aesthetic with deep green surfaces, mint accents, high-contrast typography, and spacious cards;
- responsive on desktop and mobile;
- Korean-first interface while preserving English protocol and model names;
- accessible keyboard focus states and readable text sizes.

Create these sections in this order:
1. Hero: “RED-Persona Interactive Lab” and a short explanation that the portal lets researchers inspect stored trajectories and run explicitly initiated model comparisons.
2. Primary actions: three large buttons for Method Guide, Dataset Viewer, and Live Lab.
3. Method overview: explain the roles Persona/history planner, History renderer, Runtime planner, Target, and Evaluator. Distinguish tools/models from stages.
4. Execution flow: Persona and history input → shared initial analysis → protocol-specific interaction → four independent branches → exact Target-authored quotation where applicable → final response → CARES/R/B/HarmBench evaluation.
5. Protocol comparison: Direct-final-only, Compact dialogue, and Seven-stage dialogue. Every protocol card must show its purpose, target-call budget, whether it uses a goal-focused follow-up, whether it uses a Target-authored quotation, and where R/B/HB are scored.
6. Reproducibility notice: stored historical runs must be visually separated from new live API calls. API keys must never be shown, stored in page content, analytics, or server logs. A live request must only be sent after the visitor explicitly clicks a send/next button; auto mode must be clearly labeled.
7. Paper figures: include the two supplied method figures with captions and explain what each figure represents.
8. Footer with links to the GitHub repository and the full interactive tool.

Use these exact links:
- Method Guide: https://dlwlsrnjs.github.io/Red-persona/interactive-lab/method.html
- Dataset Viewer: https://dlwlsrnjs.github.io/Red-persona/interactive-lab/viewer.html
- Live Lab: https://dlwlsrnjs.github.io/Red-persona/interactive-lab/live.html
- GitHub repository: https://github.com/dlwlsrnjs/Red-persona

Do not invent testimonials, institutions, clinical endorsements, publication venues, authors, or new benchmark results. Do not replace the interactive tools with static screenshots. Keep all three tool links prominent and open them in the same tab.
```

## 기존 기능을 페이지 안에 표시하는 HTML integration

B12에서 `Website > Pages > Add section > Integration > HTML`을 선택하고 아래 코드를 넣는다. GitHub Pages 응답에는 iframe을 막는 `X-Frame-Options` 또는 frame-ancestors CSP가 현재 없으므로 이 방식으로 원본 기능을 유지할 수 있다.

```html
<section aria-label="RED-Persona interactive tools" style="width:100%;">
  <nav style="display:flex;gap:.6rem;flex-wrap:wrap;margin:0 0 1rem;">
    <button type="button" data-redp-url="https://dlwlsrnjs.github.io/Red-persona/interactive-lab/method.html">Method Guide</button>
    <button type="button" data-redp-url="https://dlwlsrnjs.github.io/Red-persona/interactive-lab/viewer.html">Dataset Viewer</button>
    <button type="button" data-redp-url="https://dlwlsrnjs.github.io/Red-persona/interactive-lab/live.html">Live Lab</button>
  </nav>
  <iframe
    id="red-persona-tool"
    title="RED-Persona Interactive Lab"
    src="https://dlwlsrnjs.github.io/Red-persona/interactive-lab/method.html"
    loading="lazy"
    referrerpolicy="strict-origin-when-cross-origin"
    style="display:block;width:100%;height:82vh;min-height:720px;border:1px solid #245b47;border-radius:16px;background:#06130e;"
  ></iframe>
  <p style="margin-top:.7rem;font-size:.9rem;">
    If the embedded tool is too small, <a id="red-persona-open" href="https://dlwlsrnjs.github.io/Red-persona/interactive-lab/method.html">open it in a full page</a>.
  </p>
</section>
<script>
  (() => {
    const frame = document.getElementById('red-persona-tool');
    const full = document.getElementById('red-persona-open');
    document.querySelectorAll('[data-redp-url]').forEach((button) => {
      button.addEventListener('click', () => {
        const url = button.getAttribute('data-redp-url');
        frame.src = url;
        full.href = url;
      });
    });
  })();
</script>
```

## 공개 전 확인

1. B12 Preview에서 세 탭이 모두 전환되는지 확인한다.
2. Dataset Viewer에서 사례를 바꾸고 모델별 최종 성공/실패 응답이 가장 위에 나타나는지 확인한다.
3. 프로토콜 이름을 클릭했을 때 실행 계약과 트리가 열리는지 확인한다.
4. Live Lab은 API key를 입력하기 전에는 외부 요청을 보내지 않는지 확인한다.
5. 수동 모드에서는 `다음` 또는 `전송` 클릭 전 호출이 없어야 한다.
6. 모바일 Preview에서 iframe이 가로로 넘치지 않는지 확인한다.
7. 무료 `b12sites.com` 주소로 먼저 공개하고, 기능 확인 뒤에만 custom domain을 연결한다.

