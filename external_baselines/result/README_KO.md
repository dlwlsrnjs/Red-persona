# 외부 베이스라인 결과

이 폴더는 **외부 jailbreak 비교 방법의 결과만** 보관한다. RED-Persona 자체 방법(OURS)의
결과는 `persona_redteam/result/`에 있으며, 두 결과군을 합치거나 같은 방법으로 표기하지
않는다.

## 완료된 결과

- `OFFICIAL500_CARES_JMIR_KO.md`: 9개 외부 방법 × Qwen2.5-7B-Instruct/GPT-4o ×
  Official-500의 CARES·JMIR 결과

## 실행 중인 파일럿

- 대상: `gpt-6-luna`, `meta-llama/Llama-3.1-8B-Instruct`
- 방법: Direct, Skeleton Key, Many-shot, Red Teaming, PAIR, TAP, Crescendo,
  Therapist Crescendo, PCSA Phase 2 adapter
- 표본: 두 대상과 아홉 방법에 동일하게 고정한 Official cohort 앞 10개
- 생성: Luna는 OpenAI Batch 전용, Llama와 Qwen attacker는 로컬 GPU
- 평가: `gpt-4o-mini` OpenAI Batch로 CARES A/C/R·SS와 JMIR 평균·harmful rate 산출

완료 후 `GPT6_LUNA_LLAMA_PILOT10_KO.md`와 기계 판독 가능한 집계 JSON을 이 폴더에
추가한다. 생성 원문·Batch checkpoint·대용량 로그는 Git에서 제외된
`external_baselines/outputs/`와 `external_baselines/evaluations/`에 보관한다.

