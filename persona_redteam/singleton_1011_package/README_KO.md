# 1011 싱글턴 실험 패키지

이 폴더는 성능이 확인된 `1011_method_v1` 싱글턴 파이프라인을 한곳에
보관한 실행·감사 패키지다. 멀티턴 공격 코드는 포함하지 않으며, 생성기는
`max_goal_convergence_turns=0`을 강제한다.

## 검증된 기준 결과

- 기준 코드 커밋: `b87b175aa1340f1d16a945a36a094341c01a2e25`
- 검증 집합: 기존 실패 23건, 각 사례 4개 최종 분기(Best-of-4)
- 검증 생성 프로필: Qwen2.5-7B 타깃 + Llama-3.1-8B 연구자
- CARES: `gpt-4o-2024-11-20` Batch, **23/23 Accept (100%)**
- HarmBench: `cais/HarmBench-Llama-2-13b-cls`, **22/23 성공 (95.65%)**
- HarmBench 분기: **70/92 positive (76.09%)**
- 23건의 평가 대상 답변은 원래 `failed23_1011_method_v1/no_verbatim`
  싱글턴 결과와 사례별 4개 분기 텍스트가 모두 동일하다.

동일한 Qwen 타깃의 paired 비교에서도 싱글턴 최종 지표가 높았다.

| 방식 | CARES Accept | HarmBench Best-of-arm |
|---|---:|---:|
| 싱글턴 Best-of-4 | 23/23 | 22/23 |
| 일반 멀티턴 선택 endpoint | 18/23 | 13/23 |
| 추상목표 멀티턴 선택 endpoint | 21/23 | 14/23 |

단, 싱글턴은 네 분기 중 metric별 Best-of-4이고 멀티턴은 온라인 평가기가 고른
최종 endpoint 하나이므로 보고 규칙이 완전히 대칭인 알고리즘 비교는 아니다.
따라서 이 표는 “이번 실험의 최종 성공률” 비교로 해석한다.

세부 수치와 원본 결과 SHA-256은
[`evidence/verified_metrics.json`](evidence/verified_metrics.json)에 있다.

## 폴더 구성

| 파트 | 위치 | 역할 |
|---|---|---|
| 방법 진입점 | `src/our_method/` | 1011 프로토콜과 싱글턴 강제 진입점 |
| 생성 코어 | `src/experiments/`, `src/pipeline/`, `src/ablation/` | 대화 생성, 4개 최종 분기, Batch/local I/O |
| 검증 프로필 전체 197 | `launchers/launch_full197_qwen.py` | Qwen 타깃 + Llama 연구자, 세 arm |
| GPT-4o 전체 197 | `launchers/launch_full197_gpt4o.py` | GPT-4o 타깃 + Qwen 연구자, 세 arm |
| CARES/JMIR | `src/experiments/evaluate_*cares*`, `src/evaluation/prompts/` | 공식 프롬프트와 GPT-4o Batch 평가 |
| HarmBench | `src/experiments/evaluate_harmbench_direct_response.py` | 공식 13B 분류기로 Best-of-4 평가 |
| 안전 실행기 | `launchers/` | 원본 스냅샷 검증 후 싱글턴만 실행 |
| 재현 검증 | `tools/verify_snapshot.py`, `tests/` | 원본 대비 바이트 해시와 구성 계약 검사 |

`src/`는 실제로 좋은 결과를 만든 저장소 코어의 바이트 동일 스냅샷이다.
실행기는 이 복사본을 직접 import한다. `PACKAGE_MANIFEST.json`은 41개 스냅샷
파일과 세 arm 입력의 SHA-256을 고정하며, 검증 도구는 예상 밖 파일도 거부한다.

## 실행 순서

저장소의 `persona_redteam` 디렉터리에서 실행한다.

```bash
python singleton_1011_package/tools/verify_package.py
python singleton_1011_package/tools/verify_snapshot.py
```

실제 성능 검증과 같은 Qwen 타깃 프로필은 arm별로 실행한다. `no_verbatim`,
`explicit`, `no_history`를 각각 같은 방식으로 실행하면 된다.

```bash
python singleton_1011_package/launchers/launch_full197_qwen.py \
  --arm no_verbatim --prepare-only
python singleton_1011_package/launchers/launch_full197_qwen.py \
  --arm no_verbatim --wait
```

GPT-4o 타깃 전체 실험은 별도 프로필이다.

```bash
python singleton_1011_package/launchers/launch_full197_gpt4o.py \
  --arm no_verbatim --prepare-only
python singleton_1011_package/launchers/launch_full197_gpt4o.py \
  --arm no_verbatim --wait
```

완료된 8개 lane은 한 디렉터리로 병합한다.

```bash
python singleton_1011_package/launchers/merge_lanes.py \
  --result-root result/OURS/MATRIX_ID/TARGET/ARM
```

CARES는 반드시 GPT-4o Batch로 평가한다. 아래 실행기는 모델을
`gpt-4o-2024-11-20`으로 고정하며 mini 모델을 받지 않는다.

```bash
python singleton_1011_package/launchers/evaluate_gpt4o.py \
  --run-dir result/OURS/MATRIX_ID/TARGET/ARM/merged \
  --selection data/evaluations/MATRIX_ID/TARGET/ARM/selection.json \
  --output-dir data/evaluations/MATRIX_ID/TARGET/ARM/scoring \
  --expected-cases 197 --execute --wait
```

HarmBench는 CARES와 독립적인 판정이다. 생성 답변이 비공개 harmful goal을
실질적으로 수행했는지를 분류한다. 기존 recovery/behavior 평가 결과를 함께
주면 동일 분기 결합 지표까지 만든다.

```bash
python singleton_1011_package/launchers/evaluate_harmbench.py \
  --run-dir result/OURS/MATRIX_ID/TARGET/ARM/merged \
  --recovery-evaluation data/evaluations/MATRIX_ID/TARGET/ARM/scoring/recovery_behavior.json \
  --output data/evaluations/MATRIX_ID/TARGET/ARM/scoring/harmbench.json \
  --expected-cases 197 --device cuda:0
```

## 고정 계약

- 싱글턴: 사례당 독립적인 최종 분기 4개, 보고는 metric별 Best-of-4
- 방법: `1011_method_v1`
- 레거시 goal-convergence 추가 턴: `0`
- CARES evaluator: `gpt-4o-2024-11-20`, OpenAI Batch
- HarmBench classifier: `cais/HarmBench-Llama-2-13b-cls`
- 제외: `adaptive_attack.py`, attack-turn ablation, 멀티턴 endpoint 선택 코드

구성 요소 간 데이터 흐름은
[`docs/ARCHITECTURE_KO.md`](docs/ARCHITECTURE_KO.md)에 정리했다.
