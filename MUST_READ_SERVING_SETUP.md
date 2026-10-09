# RED-Persona 로컬 서빙 설정

이 문서는 현재 서버에서 Qwen과 Lexi를 재현 가능하게 서빙하기 위한 고정 설정만 기록한다.
실험 진행 상황과 일회성 점검 결과는 기록하지 않는다.

## 환경

- 전용 venv: `/data1/users/ljk98/envs/redpersona-vllm`
- Python: 3.10.12
- vLLM: 0.28.0
- Hugging Face cache: `/data1/users/ljk98/hf_cache`
- Qwen port/GPU: `8000` / GPU 0
- Lexi port/GPU: `8002` / GPU 1

고정 모델:

- `Qwen/Qwen2.5-7B-Instruct`
  revision `a09a35458c702b33eeacc393d103063234e8bc28`
- `Orenguteng/Llama-3.1-8B-Lexi-Uncensored-V2`
  revision `f4617caeabd21f1820ac89bd125c80eda70901a7`

## 서버 실행

```bash
bash serve_models.sh both
bash serve_models.sh status
bash serve_models.sh stop
```

`serve_models.sh`는 모델 revision, localhost binding, eager mode, CUDA 도구 경로와 offline
cache 사용을 고정한다. 로그는 Git에서 제외되는 `serve_logs/`에 저장한다.

Qwen researcher가 in-process로 실행되는 본 실험 단계에서는 vLLM GPU와 다른 장치를 쓴다.

```bash
export QWEN_DEVICE=cuda:4
export QWEN_BATCH_SIZE=6
export HF_HOME=/data1/users/ljk98/hf_cache
```

OpenAI 자격 증명은 Git 파일이나 명령행에 넣지 않고 환경의 secret manager 또는 로컬
`.env`를 사용한다. 저장소에는 키의 값이나 유효성 상태를 기록하지 않는다.

## 실행 전 필수 확인

1. `bash serve_models.sh status`가 두 model ID를 정확히 반환해야 한다.
2. `data/personas/persona_category_labels.jsonl`이 31,733개 persona ID를 정확히 한 번씩
   포함해야 한다. 생성 명령은 `persona_redteam/pipeline/README.md`를 따른다.
3. 전체 파이프라인 명령은
   `persona_redteam/docs/JMIR_FULL_EXPERIMENT_RUNBOOK_KO.md`를 따른다.
4. 생성 데이터와 checkpoint는 Git에 추가하지 않는다.
