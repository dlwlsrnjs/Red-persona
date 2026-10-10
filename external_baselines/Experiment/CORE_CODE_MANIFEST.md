# 외부 베이스라인 핵심 코드 snapshot

| snapshot | canonical source | 역할 |
|---|---|---|
| `core_code/matrix_gpt6_luna_llama.json` | `../matrix_gpt6_luna_llama.json` | 두 target·9개 방법·Batch transport 고정 |
| `core_code/run_luna_llama_pilot.sbatch` | `../run_luna_llama_pilot.sbatch` | 7 GPU 서버, matrix, 최종 평가 실행 |
| `core_code/run_luna_llama_accelerator.sbatch` | `../run_luna_llama_accelerator.sbatch` | 완료된 Llama 결과 재사용, Luna와 Llama-PCSA의 두 번째 노드 가속 |
| `core_code/run_luna_llama_full_shard.sbatch` | `../run_luna_llama_full_shard.sbatch` | 모든 GPU를 활용하는 비중복 정식 shard 실행 |
| `core_code/run_luna_llama_full_finalize.sbatch` | `../run_luna_llama_full_finalize.sbatch` | dependency 완료 후 병합·검증·최종 Batch 평가 |
| `core_code/merge_baseline_shards.py` | `../merge_baseline_shards.py` | 18개 target×method 셀의 500개 완전성 및 중복 검증 |
| `core_code/run_baseline_matrix.py` | `../run_baseline_matrix.py` | 방법×target 병렬 orchestration과 retry |
| `core_code/run_pyrit_baseline.py` | `../run_pyrit_baseline.py` | 외부 방법 공통 실행 adapter |
| `core_code/openai_batch_transport.py` | `../openai_batch_transport.py` | wave별 Batch 제출·resume·부분 실패 복구 |
| `core_code/evaluate_cares_jmir.py` | `../evaluate_cares_jmir.py` | CARES SS·JMIR 공통 최종 평가 |
| `core_code/setup_env.sh` | `../setup_env.sh` | PyRIT 1.1.0과 평가 의존성 설치 |

사본은 독립 package가 아니다. 실행은 canonical source에서 한다.
