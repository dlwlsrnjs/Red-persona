# 핵심 코드 snapshot manifest

`core_code/`는 논문 제출 시점의 감사·보존용 사본이다. 실행과 수정은 오른쪽 canonical source에서
한다.

| snapshot | canonical source | 역할 |
|---|---|---|
| `core_code/experiments/run_jmir_persona_batch_api.py` | `experiments/run_jmir_persona_batch_api.py` | 500개 생성, checkpoint, resume, arm 실행 |
| `core_code/experiments/qwen_target_persona_research_dialogue.py` | `experiments/qwen_target_persona_research_dialogue.py` | multi-turn 연구 대화와 네 final branch |
| `core_code/experiments/run_history_bridge_prompt_pilot.py` | `experiments/run_history_bridge_prompt_pilot.py` | 동일 history의 final-readout 교체 |
| `core_code/ablation/specs.py` | `ablation/specs.py` | 허용 ablation registry |
| `core_code/ablation/context.py` | `ablation/context.py` | arm별 target-visible context 구성 |
| `core_code/ablation/cares_jmir_rq/evaluate.py` | `ablation/cares_jmir_rq/evaluate.py` | RQ1–RQ3 결합, 평가, paired 집계 |
| `core_code/ablation/aggregate.py` | `ablation/aggregate.py` | McNemar와 공통 집계 |
| `core_code/experiments/evaluate_cares_jmir_official500.py` | `experiments/evaluate_cares_jmir_official500.py` | CARES/JMIR request와 parser |
| `core_code/pipeline/openai_batch.py` | `pipeline/openai_batch.py` | Batch API, 비용 ledger, resume |
| `core_code/pipeline/openai_chat.py` | `pipeline/openai_chat.py` | standard API tail, partial checkpoint |

`prompts/`에는 CARES h-level, CARES A/C/R, JMIR evaluator, 안전 연구 지침과 출처 metadata를
복사했다. 사본은 독립 package가 아니므로 import를 수정해 직접 실행하지 않는다.

