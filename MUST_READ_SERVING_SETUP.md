# 🛑 MUST READ — RED-Persona 로컬 서빙/환경 설정

이 문서는 이 서버에서 RED-Persona 파이프라인을 **돌리기 위한 고정 환경**을 기록한다.
새 세션/새 사람이 실행하기 전에 **반드시 먼저 읽는다**. (작성: 2026-10-09)

---

## 1. 전용 가상환경 (이름 중요)

| 항목 | 값 |
|---|---|
| **venv 이름** | **`redpersona-vllm`** |
| **경로** | `/data1/users/ljk98/envs/redpersona-vllm` |
| Python | 3.10.12 |
| 핵심 패키지 | `vllm==0.28.0` (torch 2.13.0+cu130 포함) |
| 용도 | Qwen·Lexi 로컬 서빙 + 파이프라인 클라이언트 실행 |

> 이 venv는 **이 프로젝트 전용**이다. 다른 작업의 env(`VLLM-VL-LABEL` 등)와 섞지 않는다.
> pip는 `python -m venv --without-pip` 후 get-pip.py로 부트스트랩했다(시스템에 ensurepip 없음).

활성화:
```bash
source /data1/users/ljk98/envs/redpersona-vllm/bin/activate
```

---

## 2. 디스크 / 모델 가중치 위치

- 루트 디스크 `/` 는 **12GB만 남음(95% 사용)** → 모델·venv·캐시는 전부 `/data1/users/ljk98` 아래에 둔다.
- **HF 캐시**: `HF_HOME=/data1/users/ljk98/hf_cache`
- 이미 받아놓은 가중치(재다운로드 불필요):
  - `Qwen/Qwen2.5-7B-Instruct` — revision `a09a35458c702b33eeacc393d103063234e8bc28` (15GB, 파이프라인 핀과 일치)
  - `Orenguteng/Llama-3.1-8B-Lexi-Uncensored-V2` — revision `f4617caeabd21f1820ac89bd125c80eda70901a7` (16GB)
- 연구 대화의 in-process Qwen 경로가 기대하는 snapshot 심링크도 걸어둠:
  `persona_redteam/.cache/qwen2.5-7b-instruct/a09a35…` → hf_cache 스냅샷

---

## 3. GPU

- `NVIDIA H100 80GB × 8`, 전부 유휴. driver 580.105.08 (CUDA 13).
- 기본 배치: **Qwen → GPU0**, **Lexi → GPU1**. (`CUDA_VISIBLE_DEVICES`로 지정)

---

## 4. 서버 실행 (OpenAI 호환, 파이프라인이 HTTP로 호출)

파이프라인 런북 기준 포트: **Qwen :8000**, **Lexi :8002**.

```bash
# 시작 (검증된 런처)
bash launch_servers.sh
# 상태 / 중지
bash serve_models.sh status
bash serve_models.sh stop
```

준비까지 **약 3~4분**(Lustre에서 가중치 로드 + flashinfer JIT). `status`가 두 포트 모두
model id를 출력하면 완료.

### ⚠️ 서빙에 꼭 필요한 환경변수 (런처에 내장됨 — 빼면 기동 실패)
- `--enforce-eager` : vLLM 0.28 기본 torch.compile/cudagraph 캡처가 수 분씩 걸려서 끈다.
- `PATH`에 `venv/bin`(ninja)과 `site-packages/nvidia/cu13/bin`(nvcc) 추가 +
  `CUDA_HOME=.../nvidia/cu13` : flashinfer가 샘플러를 JIT 컴파일할 때 ninja/nvcc가
  PATH에 없으면 `FileNotFoundError: 'ninja'`로 EngineCore가 죽는다.
- `VLLM_USE_FLASHINFER_SAMPLER=0` : 런타임 JIT 의존을 줄이는 안전장치.
- `HF_HUB_OFFLINE=1` : 캐시된 가중치만 쓰고 네트워크로 안 나간다.

### 검증 완료 (2026-10-09)
- `GET /v1/models` → 두 서버 200, 올바른 model id
- Qwen·Lexi `POST /v1/chat/completions` → 정상 생성
- 파이프라인 `pipeline.runtime_io.complete`(local base_url) 경로로 양쪽 응답 확인

---

## 5. API 키

- repo 루트 `repo/.env` 에 있음 (상위 `/home/ljk98/red-persona/.env`와 동일 내용).
  repo 루트에서 **상대경로**로 로드: `set -a; . ./.env; set +a`
  (`pipeline.runtime_io`도 `repo/.env`를 자동 탐지한다.)
- `OPENAI_API_KEY`, `OPENAI_API_KEY_2`, `HF_API_KEY`, `GITHUB_TOKEN` 전부 유효(2026-10-09 확인).
- OpenAI 키로 `gpt-4o-mini-2024-07-18`, `gpt-4o-2024-11-20` 호출 가능.

---

## 6. 진행 중 작업 메모

- **persona pool 품질**: `data/personas/personas.jsonl`(31,733개)에는 매칭에 쓰는
  임상 pathology 필드(core_condition/symptoms/crisis_tags/… )가 **0% 채워져 있음**.
  → `extraction/enrich_persona_pathology.py`(신규)로 gpt-4o-mini를 써서 goal과 동일한
  pathology 스키마를 채운다. 파일럿 검증 완료, **전체 31,733 실행은 아직 미실행**(사용자 확정 대기).
- **위기 분포 주의**: 풀의 **95.2%가 no_crisis**, 위기 관련은 4.8%(suicidal 0.1%).

### 결정된 방향 (2026-10-09)
1. **전체 enrichment 실행 중**: `data/personas/personas.jsonl` → `data/personas/personas_enriched.jsonl`
   (gpt-4o-mini, 48 workers, 증분 체크포인트 `*.partial`, `--resume` 가능). 완료 후 아래 스왕.
2. **임상 grounding 게이트** (crisis 하드 필터를 대체, 2026-10-09):
   `pipeline/persona_pool.py`의 `retrieve(..., grounding_gate=True)`가 goal pathology와
   **core_condition / symptoms / functional_impairments / cognitive_distortions 중 하나라도
   겹치는** 페르소나만 후보로 둔다(= 논문의 structural grounding). crisis_tags는 soft boost로
   남아 crisis-태그 페르소나가 있으면 더 높게 랭크된다(자살 goal→자살 페르소나 확인). 겹침이
   0개인 경우에만 전체 풀로 폴백한다. `evidence.grounding_mode`(clinical_grounding/fallback_full)
   와 `crisis_tag_match`를 감사 기록.
   - 이유: enriched 풀의 crisis_tags가 희소(suicidal 114·self-harm 1·나머지 0)해서 crisis_tags
     동치 하드 필터는 6개 중 5개 범주에서 전부 폴백했다. 임상축 겹침 게이트는 **6개 범주 전부
     clinical_grounding**으로 매칭된다(실측). 약한 범주(substance/violent/risk)는 공유 증상·인지
     축으로 매칭되고, 원격 신규 **goal-atom coverage**가 선택 persona의 goal 뒷받침을 강제한다.

### enrichment 완료 후 풀 교체 (필수)
```bash
# 검증 후 새 풀을 기본 풀로 지정 (원본은 그대로 두고 env로 교체)
export PERSONA_POOL_PATH=/home/ljk98/red-persona/repo/data/personas/personas_enriched.jsonl
```
`pipeline.persona_pool`은 `$PERSONA_POOL_PATH`가 있으면 그걸 사용한다.

---

## 7. 실행 운영 노트 (스모크런 2026-10-09에서 확정)

전체 파이프라인을 1개 자살 케이스로 end-to-end 검증 완료
(build → adapt → generate_histories → run_batch → evaluate_batch, preflight 전부 valid).
crisis 하드 필터가 실제로 발화해 **자살 goal → 자살 페르소나**(`cactus-02900`, crisis_tags=['suicidal_ideation'])가 선택됨.

### 스테이지별 실행 환경 (중요)
| 스테이지 | python | 비고 |
|---|---|---|
| `generate_histories` | 시스템 python3 가능 | vLLM 서버(:8000/:8002)로 HTTP 호출만, stdlib |
| `run_batch` | **반드시 venv python** (`redpersona-vllm/bin/python`) | QwenResearcher가 **in-process transformers**로 Qwen을 올림 → torch 필요 |
| `evaluate_batch` | 시스템 python3 가능 | gpt-4o-mini 호출만, stdlib |

### run_batch 필수 env (안 하면 실패)
```bash
QWEN_DEVICE=cuda:4        # vLLM이 쓰는 GPU(0/1) 말고 빈 GPU 지정. 생략 시 cuda:0 → vLLM과 충돌/OOM
QWEN_BATCH_SIZE=6         # 생략 시 자동 24 → 긴 누적대화에서 CUDA OOM. 6~8 권장
HF_HOME=/data1/users/ljk98/hf_cache
OPENAI_API_KEY=...        # gpt-4o target
--target-workers 128      # gpt 호출 병렬도(최대 128)
```

### 이번에 수정한 버그
1. `pipeline/persona_generation.py` — 존재하지 않는 `candidate_payload` import로 **ImportError** → 제거(수정 완료).
2. `experiments/evaluate_persona_co_research.py` — 평가기가 간헐적으로 enum 밖 `first_source`
   (예: `qwen_researcher`)를 반환하면 3회 재시도 후 케이스 전체가 실패하던 취약점
   → 별칭 정규화(`qwen_researcher`/`researcher`→`qwen`) + 오류메시지에 허용 enum 명시 + 재시도 5회로 강화.
3. `pipeline/persona_pool.py` — crisis 하드 필터(`crisis_filter=True`) 추가.

### 전체 실행 시 주의
- `run_batch`/`evaluate_batch`는 케이스별 checkpoint + `--retry-failed` 지원. 일부 케이스 실패해도 재시도로 복구.
- CARES Safety Score는 `evaluation.cares_harmful_level`이 None이면 집계 안 됨(라벨은 계산). 점수까지 원하면 harmful level 사전 주석 필요.
