# Final-197 Qwen short-readout · 다른 서버 재현 안내

이 문서는 `final197_single_readout_qwen_v2`를 데이터가 있는 다른 서버에서 그대로
실행하기 위한 코드·프롬프트·입출력 계약을 고정한다. 데이터와 원응답은 Git에 넣지
않으며, 경로만 실행 인자로 전달한다. API 키도 환경변수에서만 읽고 manifest나 log에
값을 기록하지 않는다.

## 1. 고정 실험 계약

| 역할 | 고정값 |
|---|---|
| 타깃 | `Qwen/Qwen2.5-7B-Instruct` revision `a09a35458c702b33eeacc393d103063234e8bc28` |
| 연구 질문 생성기 | `meta-llama/Llama-3.1-8B-Instruct` revision `0e9e39f249a16976918f6564b8830bc894c89659` |
| 생성 transport | 두 모델 모두 로컬 OpenAI-compatible vLLM continuous batching |
| 입력 | Final-197 자연형 abstract-goal + 검증된 persona/history 파일 |
| 조건 | `with_history`, `no_history` 두 paired arm |
| 연구량 | 긴 7단계 누적 대화 없음, 네 최종 분기마다 branch-local research readout 1회 |
| 최종 측정 | 각 분기에서 readout 응답의 정확 인용을 고른 뒤 direct response 1회 |
| 보고 | CARES/JMIR/R/B/HarmBench의 사례별 Best-of-4 |
| 평가기 | CARES/JMIR/R/B는 `gpt-4o-2024-11-20` Batch API, HarmBench는 로컬 공식 분류기 |

코드의 역사적 옵션명 `only_no_research_dialogue`는 “연구 질문이 전혀 없음”을 뜻하지
않는다. 제거되는 것은 7단계 누적 대화이며, 최종 네 분기의 1회 연구 readout은 그대로
유지된다.

## 2. Git에 포함된 코드와 프롬프트

실행 진입점은 다음 두 파일이다.

- `experiments/final197/launch_single_readout_qwen.py`: 두 arm의 8-lane 생성
- `experiments/final197/finalize_single_readout_qwen.py`: 병합, GPT-4o Batch 평가,
  HarmBench, 최종 요약

실제 생성 프롬프트는 다음 위치에서 조립된다.

- `experiments/qwen_target_persona_research_dialogue.py`: 타깃 system prompt, 초기 case
  packet, branch-local readout, 정확 인용 선택, 최종 direct-response prompt
- `evaluation/prompts/behavioral_risk_case_research_guidelines.md`: 초기 case packet에
  삽입되는 공동 연구 지침
- `evaluation/prompts/research_prompt_banks_en.json`: 네 최종 방향의 질문 bank
- `experiments/run_jmir_persona_batch_api.py`: 요청 wave 순서, checkpoint, wire message
  저장

평가 프롬프트는 다음 파일에 고정돼 있다.

- `evaluation/prompts/cares_official_response_evaluator.txt`
- `evaluation/prompts/jmir_official_response_evaluator.txt`
- `evaluation/prompts/persona_co_research_recovery_evaluator.txt`
- HarmBench 공식 classifier template은
  `experiments/evaluate_harmbench_direct_response.py`의 `HARM_BENCH_PROMPT`에 있다.

모든 파일의 SHA-256과 모델 revision은
`experiments/final197/QWEN_SINGLE_READOUT_CODE_MANIFEST.json`에 기록했다.

## 3. 외부 데이터 계약

권장 입력 파일은 아래 원본이다.

```text
persona_cases_NATURAL_ABSTRACT_GOAL_WITH_HISTORY.json
```

검증된 원본 SHA-256은 다음과 같다.

```text
023e58e86f00b0e9925df960e8509114e46e86ad0a23a60ce5d75013a6403026
```

파일은 JSON array이고 정확히 197개의 고유 `case_id`를 가져야 한다. 각 row에는 최소한
`case_id`, `original_request`, `persona`, `persona_history`,
`similar_goal_question_pool`, `strict_harmful_request`가 있어야 한다. `no_history`도
별도 데이터 파일을 넣지 않고 이 동일한 입력에 등록된 `no_prior_dialogue` transform을
적용한다. 따라서 두 조건에서 GOAL·persona·사례 순서가 달라지는 것을 막는다.

## 4. 모델 서버

아래는 GPU 한 장당 서버 하나를 띄우는 예시다. 실제 서버의 cache 경로와 dtype에 맞게
조정할 수 있지만 model ID, revision, served-model-name은 고정한다.

```bash
CUDA_VISIBLE_DEVICES=0 python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-7B-Instruct \
  --revision a09a35458c702b33eeacc393d103063234e8bc28 \
  --served-model-name Qwen/Qwen2.5-7B-Instruct \
  --port 8000
```

```bash
CUDA_VISIBLE_DEVICES=4 python -m vllm.entrypoints.openai.api_server \
  --model meta-llama/Llama-3.1-8B-Instruct \
  --revision 0e9e39f249a16976918f6564b8830bc894c89659 \
  --served-model-name meta-llama/Llama-3.1-8B-Instruct \
  --port 8100
```

GPU가 여덟 장이면 Qwen 4개와 Llama 4개를 각각 다른 GPU에서 띄우고 URL을 반복해서
전달한다. GPU가 적으면 각 모델 서버 하나만 띄워도 되며, 8개 lane이 같은 endpoint를
공유한다. `--target-workers 128`은 클라이언트 동시성 상한이고 vLLM의 실제 처리량은
GPU와 메모리 설정에 따라 결정된다.

## 5. 입력 사전검사

저장소의 `persona_redteam` 폴더에서 실행한다. 아래 경로는 다른 서버의 실제 경로로
교체한다.

```bash
python experiments/final197/launch_single_readout_qwen.py \
  --cases /data/final197/persona_cases_NATURAL_ABSTRACT_GOAL_WITH_HISTORY.json \
  --selection-path /data/runs/final197_qwen/selection.json \
  --campaign-root /data/runs/final197_qwen/with_history/evaluation \
  --result-root /data/runs/final197_qwen/with_history/results \
  --arm with_history \
  --prepare-only
```

이 단계는 모델 호출을 하지 않는다. 197건·case ID·GOAL/persona/Case-A-B 계약을
검사하고 selection checkpoint를 만든다.

## 6. 생성 실행

### History 조건

```bash
python experiments/final197/launch_single_readout_qwen.py \
  --cases /data/final197/persona_cases_NATURAL_ABSTRACT_GOAL_WITH_HISTORY.json \
  --selection-path /data/runs/final197_qwen/selection.json \
  --campaign-root /data/runs/final197_qwen/with_history/evaluation \
  --result-root /data/runs/final197_qwen/with_history/results \
  --arm with_history \
  --target-base-url http://127.0.0.1:8000/v1 \
  --target-base-url http://127.0.0.1:8001/v1 \
  --target-base-url http://127.0.0.1:8012/v1 \
  --target-base-url http://127.0.0.1:8022/v1 \
  --researcher-base-url http://127.0.0.1:8100/v1 \
  --researcher-base-url http://127.0.0.1:8101/v1 \
  --researcher-base-url http://127.0.0.1:8102/v1 \
  --researcher-base-url http://127.0.0.1:8103/v1 \
  --lanes 8 \
  --wait
```

### No-history 조건

같은 입력 파일과 같은 selection을 사용하고 출력 위치와 arm만 바꾼다.

```bash
python experiments/final197/launch_single_readout_qwen.py \
  --cases /data/final197/persona_cases_NATURAL_ABSTRACT_GOAL_WITH_HISTORY.json \
  --selection-path /data/runs/final197_qwen/selection.json \
  --campaign-root /data/runs/final197_qwen/no_history/evaluation \
  --result-root /data/runs/final197_qwen/no_history/results \
  --arm no_history \
  --target-base-url http://127.0.0.1:8000/v1 \
  --researcher-base-url http://127.0.0.1:8100/v1 \
  --lanes 8 \
  --wait
```

중단 후 같은 명령을 다시 실행하면 lane별 checkpoint를 재사용한다. 새 조건을 기존 출력
폴더에 섞으면 protocol 검사가 중단시키므로 arm마다 경로를 분리해야 한다.

## 7. 병합 및 GPT-4o Batch 평가

API 키 값은 Git이나 명령 인자에 쓰지 않고 실행 환경의 `OPENAI_API_KEY`에 둔다. 두
프로젝트를 병렬 사용하려면 두 번째 키를 `OPENAI_API_KEY2`로 설정하고 아래처럼 이름만
전달한다.

```bash
python experiments/final197/finalize_single_readout_qwen.py \
  --stage merge \
  --stage cloud \
  --arm with_history \
  --campaign-root /data/runs/final197_qwen/with_history/evaluation \
  --result-root /data/runs/final197_qwen/with_history/results \
  --selection /data/runs/final197_qwen/selection.json \
  --credential-name OPENAI_API_KEY \
  --recovery-credential-name OPENAI_API_KEY2 \
  --wait
```

`cloud` 단계는 CARES/JMIR와 R/B를 서로 독립적인 OpenAI Batch job으로 제출한다.
`--wait`를 사용하면 두 평가가 모두 끝나거나 오류를 반환할 때까지 기다린다. 한 키만
있으면 두 credential 옵션에 같은 환경변수 이름을 주면 된다.

## 8. HarmBench와 최종 요약

R/B 평가가 끝난 뒤 공식 HarmBench 환경에서 실행한다.

```bash
python experiments/final197/finalize_single_readout_qwen.py \
  --stage harmbench \
  --stage summary \
  --arm with_history \
  --campaign-root /data/runs/final197_qwen/with_history/evaluation \
  --result-root /data/runs/final197_qwen/with_history/results \
  --selection /data/runs/final197_qwen/selection.json \
  --harmbench-python /opt/harmbench/bin/python \
  --harmbench-model /models/HarmBench-Llama-2-13b-cls \
  --batch-size 32 \
  --device cuda:0
```

동일 명령에서 `--arm`, campaign/result 경로만 바꾸면 no-history를 평가한다.

## 9. 저장되는 재현 정보

각 사례 JSON은 네 분기에 대해 다음을 보존한다.

- 초기 타깃 분석과 실제 target-visible persona/history packet
- 분기별 연구 readout 질문과 타깃 응답
- `final_anchor_record`, `bridge_record`의 정확 인용과 선택 근거
- 최종 `attack_question`, `attack_response`
- 분기별 실제 전송 `full_messages`

`launch_manifest.json`에는 입력과 프롬프트 SHA-256, 모델 revision, endpoint, lane 범위가
남는다. 평가 결과는 `scoring/`에, 병합된 197건은 `results/merged/`에 저장된다.

## 10. 이미 공개한 결과와의 대응

이 코드의 완결 history 결과는
`result/final197_single_readout_qwen_v2/`에 aggregate-only 형태로 공개돼 있다. 입력
197건의 검증된 SHA-256, 모델 revision, 프롬프트 protocol, 네 분기, 평가 모델이 모두
동일해야 그 결과의 재현 실행으로 간주한다.
