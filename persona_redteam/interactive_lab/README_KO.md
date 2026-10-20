# RED-Persona Interactive Lab

기존 대량 실험을 대체하는 실행기가 아니라, **한 사례의 실제 prompt 전개와 모델/기법 간
차이를 검사하는 비교 도구**다. 개별 레인은 prompt를 확인하고 한 단계씩 보낼 수 있다.
일괄 실행은 사용자가 `선택 레인 · 다음` 또는 `선택 레인 · Auto`를 명시적으로 누르고 비용
확인에 동의한 경우에만 시작한다.

## 제공 기능

- Final-197 사례를 ID/키워드로 찾거나 과거 strict-joint 성공·실패 집합에서 무작위 선택
- 선택된 persona, persona history, 원 GOAL과 과거 분기별 평가 표시
- 31,733개 persona 원본 pool 검색과 사례별 retrieval top-12, rerank 사유, fit audit 표시
- 사전 생성된 유사-GOAL Case A/B 질문 풀과 실제 질문/인용 선택 audit 표시
- `Compact dialogue`, `Direct-final-only`, `Seven-stage dialogue`, Direct baseline 비교
- PCSA Phase II의 client simulator → Target → progress evaluator 한 stream을 수동 검사
- OpenAI Chat Completions와 Hugging Face Inference Providers 연결
- 사용자가 별도 GOAL을 입력하고 모든 마지막 prompt를 전송 전 수정
- 저장된 본실험 응답과 새 실시간 응답을 같은 단계에서 비교
- 여러 실행 레인을 열어 모델 또는 알고리즘을 나란히 비교
- `기법 고정→여러 모델`, `모델 고정→여러 기법`, `선택 기법×선택 모델` 실행 매트릭스
- 선택 레인 전체에 다음 단계 1회씩 병렬 전송하는 Step 모드
- 선택 레인을 각 프로토콜 종료점까지 라운드 단위로 병렬 진행하는 Auto 모드와 중지 제어
- 저장된 모델별 실행 선택: Compact의 GPT-4o, Qwen2.5-7B, Mistral, Gemma,
  Phi-4, Llama 계열과 GPT 계열 및 Direct-final/Seven-stage의 GPT-4oㆍQwen
- `여러 레인 비교`와 `한 레인 집중` 표시 전환
- personaㆍlongitudinal history와 전체 레인 진행상황의 전체화면 stage

## GitHub Pages 무료 호스팅

브라우저 단독 실행본은 `docs/interactive-lab/`에 있으며 GitHub Actions가 다음 주소로 배포한다.

<https://dlwlsrnjs.github.io/Red-persona/>

첫 화면은 기능을 명확히 나눈다.

- `viewer.html`: 공개 Final-197 snapshot 전용. API 키 필드와 외부 전송 코드가 없는 read-only viewer
- `live.html`: OpenAI/Hugging Face에 단계별로 직접 요청하는 online real-time lab
- 로컬 Python 앱: 같은 실시간 기능을 localhost 서버가 중계하는 개발ㆍ검사 버전

Pages 화면에서도 실행 레인마다 또는 provider별 공용 칸에 OpenAI API key/Hugging Face
token을 입력할 수 있다. 개별 전송, 선택 레인 Step, 명시적으로 시작한 Auto 실행을 지원한다.
정적 페이지이므로 요청은 브라우저에서
선택한 provider endpoint로 직접 전송된다. 키는 Pages 데이터나 저장소에 기록하지 않는다.
각 레인은 저장된 197-case 실행의 실제 token usage로 호출 1회, 한 분기와 4분기 전체의
평균 사용량을 먼저 표시한다. GPT-4o는 날짜와 출처가 표시된 공개 단가로 달러 추정치도
계산하며, 전송 직전 확인 대화상자에서 승인해야 실제 요청이 나간다.
197개 persona/history와 저장된 모델별 점수는 `export_pages_snapshot.py`로 내보낸 정적
snapshot에서 읽는다.

snapshot 갱신:

```bash
python -m persona_redteam.interactive_lab.export_pages_snapshot
```

### 과거 본실험 generation preset

Live Lab은 단순한 화면 기본값이 아니라 등록된 Final-197 target generation 계약을 단계별로
복원한다. GPT-4o 본실험의 모델 식별자는 `gpt-4o-2024-11-20`이고 temperature는 0이다.
`top_p`와 seed는 요청에 넣지 않아 provider 기본값을 사용했다. 출력 상한은 초기 분석 650,
seven-stage의 중간 분석 900, focused readoutㆍfinal queryㆍdirect-final 1200 tokens다. 화면은
단계 준비 시 이 값을 자동으로 적용하고 실제 전송 전 표시한다. 사용자가 값을 바꾸면 재현
preset에서 벗어난 새 실행이다.

과거 저장 응답을 그대로 재생하는 경우에는 같은 branch의 `bridge_record` exact quote와
등록된 attack-style suffix를 사용한다. 새 응답에는 저장 quote가 실제 substring으로 존재할
때만 이를 사용하고, 그렇지 않으면 새 응답 안에서 exact quote를 다시 선택한다.

## 실행

저장소 루트에서:

```bash
python -m persona_redteam.interactive_lab.app
```

브라우저에서 <http://127.0.0.1:7865>를 연다. 포트를 바꾸려면:

```bash
python -m persona_redteam.interactive_lab.app --port 8090
```

기본 bind는 `127.0.0.1`이다. `--host 0.0.0.0`도 가능하지만, prompt와 브라우저에 입력한
키가 네트워크에 노출될 수 있으므로 인증·TLS가 없는 서버에서는 사용하지 않는다.

## API 키 계약

1. 키는 HTML이나 Python 설정 파일에 쓰지 않는다.
2. 브라우저 `localStorage`/`sessionStorage`에 저장하지 않는다. 입력창의 현재 값으로만 유지한다.
3. 키는 `POST /api/session/<id>/send` 한 요청에만 포함된다.
4. 서버는 키를 세션 객체, 결과 파일 또는 로그에 복사하지 않는다.
5. `confirm_send=true`가 없으면 서버가 호출을 거부한다.
6. 공용 키도 새 레인의 DOM 입력값으로만 복사하며 세션 객체에는 넣지 않는다.
7. 페이지를 닫거나 새로고침하면 입력한 키가 사라진다.
8. Auto는 페이지 로드나 레인 생성으로 시작되지 않고 별도 확인 대화상자 승인 후에만 시작한다.

## 단계 계약

### RED-Persona Compact

1. 저장된 실험 계약으로 persona/history 초기 분석 prompt를 보여준다.
2. 선택 분기의 저장된 goal-focused follow-up과 question-selection audit를 보여준다.
3. 새 Target readout에서 1--3개 연속 문장 exact substring 후보를 만든다.
4. GOAL token coverage, request-language와 output-form 신호로 후보를 정렬한다.
5. 사용자가 후보를 확인·교체한 후에만 동일 분기의 final query를 만든다.

자동 selector는 대시보드용 설명 가능한 보조 선택기다. 논문 본실험의 Qwen semantic selector
결과는 `historical_anchor_audit`로 별도 표시되며, 대시보드의 새 실시간 응답을 다시 논문 수치로
섞지 않는다.

### Direct-final-only와 Seven-stage

각각 저장된 완결 실험의 실제 단계 prompt를 사용한다. Seven-stage는 선택한 history 조건에 맞는
과거 실행 artifact가 있을 때만 활성화된다. 마지막 인용은 새 readout의 exact substring으로 다시
구성한다.

### PCSA Phase II inspector

저장소의 PCSA system/candidate/evaluator prompt 계약을 사람이 한 단계씩 검사하기 위한
**한 전략 stream**이다. 전체 baseline의 turn당 네 후보 Best-of-4 실행 및 최종 논문 성능을
대체하지 않는다. 각 단계에서 Attacker, Target, Evaluator를 서로 다른 provider/model로 선택할 수
있다.

## Custom GOAL 주의

Custom GOAL은 Direct와 PCSA prompt에 직접 반영된다. RED-Persona 레인은 선택 사례에서 이미
검증된 persona와 질문 scaffold를 보존하므로 새 GOAL과 자동으로 재매칭하지 않는다. 화면에서
persona/질문 풀 정합성을 확인하고 마지막 prompt를 직접 수정해야 한다. 새 GOAL에 맞춘 정식
persona retrieval·history 생성은 기존 오프라인 pipeline을 사용한다.

## 테스트

```bash
python -m unittest persona_redteam.interactive_lab.test_interactive_lab -v
```

테스트는 외부 API를 호출하지 않는다.

## 기존 산출물 자동 탐색

UI는 결과를 복제하지 않고 다음 순서로 기존 모델별 산출물을 찾는다.

```bash
1. RED_PERSONA_RESULTS_ROOT / RED_PERSONA_EVALUATIONS_ROOT 환경변수
2. 현재 clone의 persona_redteam/result/OURS 및 persona_redteam/data/evaluations
3. 기존 /data1 런타임 캐시
```

발견된 실행과 history 조건별 사례 수, 평가 수 및 실제 경로는 `/api/config`의
`historical_runs`에 표시된다. 다른 서버에서는 위 두 환경변수만 기존 결과 루트로 지정하면
코드나 데이터를 복사하지 않고 그대로 사용할 수 있다.
