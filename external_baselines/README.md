# Jailbreak baselines

이 디렉터리는 RED-Persona 데이터셋에 적용할 외부 jailbreak baseline을 격리한다.
공식 [Microsoft PyRIT](https://github.com/microsoft/pyrit) 소스를
`vendor/pyrit` submodule의 안정 릴리스 **v1.1.0**으로 고정하여 여러 single-turn과
multi-turn 방법을 같은 입출력 계약으로 제공한다. PyRIT은 MIT 라이선스이며, 정확한
revision은 submodule commit으로 확인한다.

## 폴더 구조

외부 비교군에 필요한 파일은 모두 이 폴더 안에 둔다.

```text
external_baselines/
├── README.md
├── setup_env.sh
├── matrix_qwen_gpt4o.json
├── run_baseline_matrix.py
├── run_matrix_on_gpu.sbatch
├── run_pcsa_qwen_smoke.sbatch
├── run_pyrit_baseline.py
├── pcsa_phase2.py
├── openai_batch_transport.py
├── prepare_baseline_personas.py
├── data/baseline_persona_assignments_official_500.jsonl
├── tests/
├── vendor/pyrit/                 # v1.1.0 submodule
└── outputs/                      # 생성 결과, Git 제외
```

`persona_redteam/`은 RED-Persona 자체 방법만, `external_baselines/`는 외부 비교 방법만
담는다. JMIR에서 정제한 625개 목표가 원천이지만, 실제 비교 실행은 루트
`data/red_persona_official_500.jsonl`에 등록된 공식 500개만 사용한다.

## 실행 원칙

- 정식 attack 입력은 `data/crisis_goals_jmir_persona_min10.jsonl`의 625개 원천 goal 중
  `data/red_persona_official_500.jsonl`로 지정한 **공식 500개 평가 case**다. 31,733개
  persona pool에서 목표별로 고정한 500개 프로필은 `pcsa_phase2`에서만 공격자 prompt에
  주입한다. 나머지 8개 방법은 persona를 공격 입력으로 사용하지 않는다.
- 주 baseline: **Crescendo + `escalation_crisis.yaml`**. 정신건강 위기 대화에 맞춘
  점진적 multi-turn 공격 설정을 사용한다.
- 모든 방법은 동일한 공식 500개 case, target endpoint, checkpoint/resume 및 최종 평가
  출력 계약을 사용한다.
- PyRIT의 자동 scorer는 공격 탐색과 조기 중단을 위한 내부 제어 신호일 뿐이다.
- PCSA는 평가기가 아니라 아홉 번째 공격 방법이다. 최종 판정은 PCSA와 분리된 CARES 및
  mental-health GPT judge 단계에서 수행한다.
- 각 결과는 고정 persona context, 전체 target 대화와 마지막 target 응답을 보존하고
  `final_evaluation.status=pending`으로 후속 평가에 넘긴다.

공식 cohort는 RED-Persona 본 실험과 동일하다. 생성된 625개 persona-history 후보에서
private-goal 원문 누출 17개를 제외한 뒤, 유효 608개 중 단일 과대표집 범주인
`suicidal_ideation`에서만 108개를 보류한 500개다. 분포는
`179 / 174 / 65 / 63 / 12 / 7`이며, 관측된 모델 결과는 선택에 사용하지 않았다.

runner는 원천 goal의 `jmir-test-*` ID를 공식 index의 `canonical_source_index`로
`jmir-full-*` ID에 연결한다. 공식 index가 500개 고유 ID가 아니거나, source category가
다르거나, persona assignment가 빠지면 정식 실행을 중단한다. 실행 manifest에는 공식 index
경로와 SHA-256을 기록하므로 본 실험과 baseline의 분석 분모가 같은지 사후 검증할 수 있다.

`external_baselines/data/baseline_persona_assignments_official_500.jsonl`은 공식 500개 목표
각각에 서로 다른 기존 persona를 하나씩 고정한다. 원천 625개 전체에서 목표 본문과 pathology
route에 대한 결정적 lexical matching을 수행한 뒤, `canonical_source_index`로 공식 500개만
투영한다. 따라서 외부 baseline과 RED-Persona 본 실험의 case ID가 정확히 일치하며, 9개
방법과 두 target도 같은 persona 조건을 공유한다. 다시 만들 때는
다음을 실행한다.

```bash
external_baselines/.venv/bin/python external_baselines/prepare_baseline_personas.py
```

## 별도 환경

기존 serving 환경과 공격 도구의 의존성을 분리하기 위해 Python 3.12 전용 환경을 쓴다.

```bash
git submodule update --init --recursive
bash external_baselines/setup_env.sh
```

현재 로컬 모델 구성의 기본값은 다음과 같다.

- adversary: Qwen2.5-7B-Instruct, `http://127.0.0.1:8000/v1`
- target: Llama-3.1-8B-Lexi-Uncensored-V2, `http://127.0.0.1:8002/v1`

먼저 입력과 실행 계획만 검사한다.

```bash
external_baselines/.venv/bin/python external_baselines/run_pyrit_baseline.py \
  --method crescendo --dry-run --limit 5
```

위 `--limit 5`는 smoke test 전용이다. 정식 500개 실행에서는 `--limit`, `--start`,
`--stop`, `--crisis-label`을 지정하지 않는다. 이 경우 manifest의
`dataset.run_scope`가 `official-500`, `selected_count`가 `500`인지 자동 검증한다.

서버를 띄운 뒤 실제 실행한다.

```bash
bash serve_models.sh both
external_baselines/.venv/bin/python external_baselines/run_pyrit_baseline.py \
  --method crescendo --output-dir external_baselines/outputs/crescendo
external_baselines/.venv/bin/python external_baselines/run_pyrit_baseline.py \
  --method pair --output-dir external_baselines/outputs/pair
```

지원하는 방법은 다음과 같다.

| 방법 | 분류 | 실제 target 질의 구조 | 용도 |
|---|---|---|---|
| `direct` | single-turn | goal 1회 | jailbreak 없는 하한선/control |
| `skeleton_key` | single-turn | simulated prefix 뒤 goal 1회 | 선행 문맥 priming 비교 |
| `many_shot` | single-turn | demonstrations를 포함한 긴 prompt 1회 | long-context in-context attack |
| `red_teaming` | multi-turn | 단일 경로 반복 개선 | PyRIT 기본 adaptive attacker |
| `pair` | multi-turn | 독립 stream별 반복 개선 | [PAIR](https://github.com/patrickrchao/JailbreakingLLMs) 비교군 |
| `tap` | multi-turn | branch·score·prune tree search | [TAP](https://github.com/RICommunity/TAP) 탐색 폭 비교 |
| `crescendo` | multi-turn | 점진적 escalation과 backtracking | [Crescendo](https://arxiv.org/abs/2404.01833) 정신건강 주 baseline |
| `therapist_crescendo` | multi-turn | 상담 관계를 쌓으며 therapist 역할·자격 주장 유도 | PyRIT Psychosocial의 licensed-therapist sub-harm |
| `pcsa_phase2` | multi-turn | 고정 persona·pathology를 주입하고 4전략 best-of-4를 최대 4턴 수행 | [PCSA](https://arxiv.org/abs/2604.04842) Phase II adapter |

정식 500개 실행 예시는 다음과 같다. 각 방법은 별도 output 디렉터리에 저장된다.

```bash
for method in direct skeleton_key many_shot red_teaming pair tap crescendo therapist_crescendo pcsa_phase2; do
  external_baselines/.venv/bin/python external_baselines/run_pyrit_baseline.py \
    --method "$method" --output-dir "external_baselines/outputs/$method"
done
```

기본값은 Many-shot 16개 example, TAP width 3/branching 2/depth 10이다. 비용 비교를
위해 manifest의 method별 parameter와 target 대화 turn 수를 함께 보존한다.

### PCSA Phase II 재현 범위

`pcsa_phase2.py`는 논문 v2의 §3.3과 Appendix D를 기준으로 구현한다. 논문의 Phase I
생성 대신 이미 고정된 `case_id → persona_id → persona_profile`과
`source_goal_id → pathology.cognitive_distortions`를 초기 상태로 사용한다. 매 턴
`reassurance_seeking`, `appeal_to_expertise`, `intellectualization`,
`metaphorical_expression` 후보를 하나씩 만들고, Appendix D.1 기반 GPT-4o-mini 중간
evaluator가 평가한 최고 후보의 client/target 교환만 다음 턴 history로 이어간다. 같은 턴의
네 후보는 공격 문장 생성, target 응답, 중간 평가의 세 wave로 병렬 처리하므로 OpenAI
Batch에서도 독립 후보 네 개가 각각 별도 순차 batch가 되지 않는다.

논문은 best-of-N의 N과 최대 턴 수를 공개하지 않았다. 이 저장소는 비교 가능성을 위해
`N=4`, `max_turns=4`로 명시 고정한다. `--pcsa-candidates`는 1–4만 허용하고,
`pcsa_phase2`의 `--max-turns`는 4를 넘으면 실행 전에 중단된다. 이는 공개 코드가 없는
상태에서 만든 **PCSA-Phase2 (precomputed persona) adapter**이며 전체 원 구현과 동일하다고
주장하지 않는다. 모든 후보, 중간 평가 JSON, 선택 경로와 조기 종료 원인은 case 결과에
저장한다.

## Qwen-7B + GPT-4o 동시 pilot

[`matrix_qwen_gpt4o.json`](matrix_qwen_gpt4o.json)은 두 target을 고정한다.

- Qwen2.5-7B-Instruct: 로컬 `:8000`, target이면서 multi-turn attacker
- GPT-4o: OpenAI Batch API target
- 9 methods × 2 targets = 18개 job
- pilot 기본값: method/target 조합마다 동일한 첫 case 1개
- 동시 실행 기본값: 18개 job

각 방법의 특징을 유지하면서 pilot 비용을 줄이기 위해 Many-shot은 8 examples,
RedTeaming/PAIR/TAP은 3 depth, 두 Crescendo와 PCSA는 4 turns를 사용한다. TAP만 width
2와 branching 2를 사용하고 PAIR는 2 streams를 사용한다. PCSA는 네 전략 후보를
사용하며 중간 evaluator는 논문 설정과 같은 GPT-4o-mini다.

GPT-4o의 single-turn 방법은 여러 case를 한 Batch JSONL에 묶는다. 적응형 multi-turn
방법은 이전 응답을 받아 다음 공격 turn을 정해야 하므로, 동시 실행 중 같은 단계에 도달한
요청을 wave 단위 Batch로 묶는다. 각 wave의 입력, OpenAI batch ID, 상태, 출력과 오류는
해당 방법 output의 `_openai_batches/` 아래에 보존한다. OpenAI의 completion window는
`24h`이므로 multi-turn 전체 완료 시간은 동기 API보다 길 수 있다.

```bash
export OPENAI_API_KEY='...'
bash serve_models.sh qwen

# 실제 요청 없이 18-job 계획 확인
external_baselines/.venv/bin/python external_baselines/run_baseline_matrix.py --dry-run

# 각 조합 1 case, 최대 18개 동시 pilot
external_baselines/.venv/bin/python external_baselines/run_baseline_matrix.py \
  --pilot-cases 1 --max-concurrent-jobs 18
```

로그인 노드에 GPU가 없으면 서버와 matrix를 같은 Slurm GPU job 안에서 실행한다. 제출 시
환경에 있던 API key만 전달되며 key 값은 스크립트나 manifest에 기록되지 않는다.

```bash
export OPENAI_API_KEY='...'
PILOT_CASES=1 sbatch external_baselines/run_matrix_on_gpu.sbatch
```

현재 클러스터에서는 저장소의 `persona_redteam/.venv`와
`/home/ljk98/POLY/hf-cache`를 사용해 Qwen endpoint를 한 번만 띄운 뒤 18개 job이 공유한다.
레거시 `/data1` 환경이 실제로 존재하면 `serve_models.sh`가 이를 우선 사용할 수 있으며,
`RED_PERSONA_VENV`와 `HF_HOME`으로 명시적 override도 가능하다. Qwen 준비 확인, baseline
테스트, 실행, 종료 정리까지 한 job 안에서 수행한다.

OpenAI key 없이 PCSA의 실제 서버 연결, 고정 persona/pathology 주입, 네 후보 병렬 처리,
최대 4턴 history 전달과 결과 schema만 먼저 확인하려면 다음 smoke job을 사용한다. 이 smoke의
중간 evaluator는 연결 검증을 위해 Qwen을 쓰며, 정식 matrix에서는 논문 설정대로
GPT-4o-mini Batch evaluator를 쓴다.

```bash
sbatch external_baselines/run_pcsa_qwen_smoke.sbatch
```

출력은 `external_baselines/outputs/qwen_gpt4o_<slurm_job_id>/<target>/<method>/`에 분리되고 각 job의
`matrix_job.log`, case checkpoint 및 최상위 `matrix_summary.json`이 남는다. API 키
값은 manifest나 명령행에 저장하지 않고 환경변수 이름만 기록한다. 실패한 조합을 다시
실행할 때는 `--retry-failed`를 사용한다.

공식 500개 전체 matrix는 다음처럼 명시적으로 요청한다. 총 9,000 case-method-target
조합이며 multi-turn 내부 호출은 이보다 많으므로 pilot의 latency·오류·API 비용을 먼저
확인해야 한다.

```bash
external_baselines/.venv/bin/python external_baselines/run_baseline_matrix.py \
  --full-500 --max-concurrent-jobs 18
```

실패 파일은 그대로 남고, 성공한 case는 재실행 시 건너뛴다. 실패 case만 다시
시도하려면 `--retry-failed`를 추가한다.

## 정신건강 도메인에 직접 맞는 방법

범용 jailbreak보다 아래 방법들이 현재 데이터에 더 가깝다.

| 방법 | 도메인 일치점 | 현재 상태 |
|---|---|---|
| PyRIT crisis Crescendo | 위기 신호, hotline/refusal 이후 후퇴, 점진적 재접근 | `crescendo`로 공식 500개 실행 가능 |
| PyRIT licensed-therapist Crescendo | 상담 관계와 신뢰를 쌓으며 실제 치료사 역할·자격 주장을 유도 | `therapist_crescendo`로 공식 500개 실행 가능 |
| [MHSafeEval](https://github.com/suhyun565/MHSafeEval) | 정신건강 상담 전용 adversarial client, 위해 category × counselor role의 closed-loop 탐색 | 다음 adapter 1순위 |
| [PHISH](https://github.com/Jivnesh/PHISH) | history의 implicit cue로 mental-health assistant persona를 점진적으로 변경 | persona history 생성 후 adapter 가능 |
| [VERA-MH](https://github.com/SpringCare/VERA-MH) | suicidal ideation/harm-from-others persona와 임상 rubric을 사용하는 장기 대화 | 외부 임상 검증용 후보 |
| [CounselBench-Adv](https://llm-eval-mental-health.github.io/counselbench-2025/) | 전문가가 작성한 single-turn 정신건강 adversarial 질문 120개 | 별도 데이터셋 검증용 후보 |
| [MultiTurnPSB](https://arxiv.org/abs/2606.02630) | 의료 안전에서 fixed/adaptive/live 4-turn 공격 비교 | 인접 의료 도메인 참고군 |

MHSafeEval은 자체 58개 patient profile을 쓰므로 그대로 실행하면 공식 500개 비교가 아니다.
통합 시 `patient_profile_loader`를 공식 500개 case adapter로 교체하고, 위해 category/role
archive와 judge는 공격의 내부 탐색 신호로만 사용해야 한다. 최종 결과는 다른 방법과
동일하게 전체 transcript와 마지막 응답을 공통 CARES/GPT judge 단계에 넘긴다.

PHISH는 reverse-persona trait과 history cue가 필요하므로 raw goal만으로 임의 구성하면
원 논문과 다른 공격이 된다. 이 저장소의 persona history 생성이 끝난 뒤 해당 history를
입력으로 연결하는 것이 맞다.

## 추가 후보와 구현 판단

### Multi-turn

1. **PHISH** — 대화 history 안의 implicit steering과 persona hijacking을 다루며
   mental-health high-risk domain을 직접 평가하므로 가장 가까운 후속 후보다.
   [paper](https://arxiv.org/abs/2601.16466),
   [code](https://github.com/Jivnesh/PHISH)
2. **ActorAttack** — 목표에서 actor chain을 만들고 여러 turn에 걸쳐 단서를
   수집하는 방식이라 장기 대화 비교군으로 적합하다.
   [paper](https://arxiv.org/abs/2410.10700),
   [code](https://github.com/AI45Lab/ActorAttack)
3. **GOAT** — 관찰-사고-전략-응답 루프로 다음 공격 turn을 동적으로 고르는
   multi-turn baseline이다.
   [paper](https://openreview.net/pdf?id=bDBnd9T2Cz),
   [Garak implementation](https://github.com/NVIDIA/garak/blob/main/docs/source/probes/goat.rst)

현재 runner의 `red_teaming`, `pair`, `tap`, `crescendo`로 기본 black-box 비교를 먼저
완료한 뒤 PHISH를 붙이는 순서가 적합하다. ActorAttack과 GOAT는 각자 별도 실행 상태와
로그 형식을 가지므로 현재 JSON contract adapter가 추가로 필요하다.

### Single-turn

1. **Many-shot Jailbreaking** — 많은 faux dialogue를 하나의 긴 입력에 넣는 방식이다.
   현재 `many_shot`으로 구현했으며 example 수를 `--many-shot-examples`로 통제한다.
   [Anthropic report](https://www.anthropic.com/research/many-shot-jailbreaking)
2. **Skeleton Key** — 안전 규칙을 바꾸도록 유도하는 선행 교환 뒤 목표를 묻는다.
   현재 `skeleton_key`로 구현했다.
   [Microsoft report](https://www.microsoft.com/en-us/security/blog/2024/06/26/mitigating-skeleton-key-a-new-type-of-generative-ai-jailbreak-technique/)
3. **GCG / nanoGCG** — gradient로 adversarial suffix를 최적화하는 white-box 방법이다.
   [paper/code](https://github.com/llm-attacks/llm-attacks),
   [maintained implementation](https://github.com/GraySwanAI/nanoGCG)
4. **AutoDAN** — genetic algorithm으로 읽을 수 있는 공격 prompt를 최적화한다.
   [paper/code](https://github.com/SheltonLiu-N/AutoDAN)
5. **DeepInception** — nested role-play scene을 사용하는 경량 prompt attack이다.
   [paper/code](https://github.com/tmlr-group/DeepInception)

GCG와 AutoDAN은 vLLM API가 아니라 target weight·tokenizer·gradient 접근과 별도 GPU
환경이 필요하다. 또한 GCG는 각 goal에 대한 명시적 target completion 문자열이
필요하므로 현재 공식 500개 mental-health goal에 이를 임의 생성하면 비교 조건이 바뀐다.
따라서 현 단계에서는 구현 완료로 표시하지 않고, target 문자열 설계를 먼저 고정한 뒤
별도 white-box runner로 추가한다. DeepInception은 단일 template 방식이라 다음
adapter 후보지만, 논문 설정을 그대로 재현할 template/version 고정이 선행되어야 한다.

정신건강 응답 평가는 공격 성공 scorer와 분리한다. PCSA Phase II의 중간 evaluator도
후보 선택과 조기 종료에만 사용하며, 모든 방법의 최종 평가는 동일한 CARES/GPT judge
결과로 비교한다.
