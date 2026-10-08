# Qwen2.5-7B-Instruct 교체 파일럿

## 모델

- `Qwen/Qwen2.5-7B-Instruct`
- revision: `a09a35458c702b33eeacc393d103063234e8bc28`
- GPU 0: persona analysis frame
- GPU 1: research/latent-request inference frame
- 출력 계약: 내담자 평문 발화만 허용, JSON·라벨·분석문 금지

공식 generation config에 맞춰 `temperature=0.7`, `top_p=0.8`, `top_k=20`,
`repetition_penalty=1.05`를 사용했다.

## 결과

두 프레임에서 각각 6개, 총 12개를 생성했다. 12개 모두 내담자 평문으로 출력되어
Lexi 파일럿의 JSON 형식 실패가 사라졌다. goal의 self-schema와 관계 의미도 Lexi보다
선명하게 나타났다.

그러나 goal 전체, 정규화 결과와 persona schema를 한 번에 넣고 높은 정보량을 요구하면
Qwen도 근거 없는 세부사항을 연결했다.

- `at work`
- `you get mad at me`
- `you just shut down`

이는 모델 선택만의 문제가 아니라 입력 계약 문제다. 정규화 태그와 생성된 schema는
분석·매칭 근거이며 문자 그대로의 사건 근거가 아니다.

## 채택 결정

동적 다음 발화 생성기는 Qwen2.5-7B-Instruct로 교체한다. Lexi는 비교 기준으로만
보존한다. 실제 교대 파이프라인에서는 다음을 적용한다.

1. goal 전체를 Qwen의 비공개 참고 정보로 제공한다.
2. 한 라운드에는 goal atom 하나와 원문 문자 근거 하나만 활성화한다.
3. R3-R5는 persona 분석에 필요한 자기해석, 기능 의미, 관계 예측을 한 층씩 누적한다.
4. R6에서 연구 프레임으로 잠재 요청을 추론하게 하되 감정 인정과 사실 동의를 구분한다.
5. Qwen은 다음 내담자 발화만 말한다. 상태, atom, 근거와 평가는 Python controller가
   별도로 기록한다.
6. 생성문에 원문 근거 밖의 사람, 장소, 직장, 학교, 반응 또는 사건이 생기면 재생성한다.

## 산출물

- GPU 0: `outputs/qwen_instruct/persona_analysis_gpu0.json`
- GPU 1: `outputs/qwen_instruct/research_inference_gpu1.json`
- 실행기: `experiments/pilot_qwen_goal_informed_frames.py`
- 활성 설정: `configs/qwen_instruct_interleaved_dialogue_spec.json`

결과 파일은 실험 감사용 JSON이다. Qwen이 생성한 `client_message` 자체는 모두 평문이다.
