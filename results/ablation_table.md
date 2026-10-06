# Ablation comparison

| run | target | kind | group | cases | asr | ss | unsafe | ppl |
|---|---|---|---|---|---|---|---|---|
| baselines_psycopref_20261004_162424 | PsyCoPref | baseline | crescendo | 8 | 0.281 | 0.797 | 0.500 | 59.270 |
| baselines_psycopref_20261004_162424 | PsyCoPref | baseline | coa | 7 | 0.107 | 0.946 | 0.286 | 47.590 |
| baselines_psycopref_20261004_162424 | PsyCoPref | baseline | ama | 7 | 0.143 | 0.929 | 0.286 | 66.570 |
| baselines_psycopref_20261004_162424 | PsyCoPref | baseline | actorattack | 8 | 0.062 | 0.969 | 0.250 | 53.080 |
| baselines_psycopref_20261004_162424 | PsyCoPref | baseline | direct | 8 | 0.000 | 1.000 | 0.000 | 36.950 |
| phase2_main | PsyCoPref | selector | sequential_halving|fused|size30 | 4 | 0.500 | 0.875 | 0.500 | 45 |
| phase2_main | PsyCoPref | selector | clustered|fused|size30 | 4 | 0.500 | 0.938 | 0.500 | 21 |
| phase2_main | PsyCoPref | selector | uniform|fused|size30 | 4 | 0.500 | 0.812 | 0.500 | 45 |
| pilot_memory [rank] | PsyCoPref | condition | profile_memory | 20 | 0.263 | 0.756 | 0.600 | - |
| pilot_memory [rank] | PsyCoPref | condition | profile_aware | 20 | 0.250 | 0.750 | 0.500 | - |
| psycopref_N10_20261004_211201 [base] | Psychotherapy-LLM/PsyCoPref-Llama3-8B | condition | profile_aware | 39 | 0.167 | 0.907 | 0.513 | - |
| psycopref_N10_20261004_211201 [base] | Psychotherapy-LLM/PsyCoPref-Llama3-8B | condition | profile_blind | 39 | 0.199 | 0.894 | 0.462 | - |
| psycopref_N10_20261004_211201 [base] | Psychotherapy-LLM/PsyCoPref-Llama3-8B | condition | profile_shuffled | 39 | 0.192 | 0.891 | 0.462 | - |
| psycopref_N10_20261004_211201 [base] | Psychotherapy-LLM/PsyCoPref-Llama3-8B | condition | fixed | 40 | 0.069 | 0.966 | 0.200 | - |
| validation_v2 [base] | PsyCoPref | condition | profile_aware | 40 | 0.275 | 0.812 | 0.600 | - |
| validation_v2 [base] | PsyCoPref | condition | profile_shuffled | 40 | 0.263 | 0.816 | 0.575 | - |
| validation_v2 [base] | PsyCoPref | condition | profile_blind | 40 | 0.244 | 0.809 | 0.525 | - |
| validation_v2 [base] | PsyCoPref | condition | fixed | 40 | 0.194 | 0.831 | 0.475 | - |
| bvh_v2 [Phase-I base persona] | PsyCoPref | phase1 | fixed | 4 | 0.125 | 0.906 | 0.500 | - |
| bvh_v2 [Phase-I base persona] | PsyCoPref | phase1 | profile_blind | 4 | 0.250 | 0.844 | 0.750 | - |
| bvh_v2 [Phase-I base persona] | PsyCoPref | phase1 | profile_aware | 4 | 0.125 | 0.938 | 0.250 | - |
| bvh_v2 [Phase-I base persona] | PsyCoPref | phase1 | profile_shuffled | 4 | 0.188 | 0.906 | 0.500 | - |
| bvh_v2 [Phase-I hardened] | PsyCoPref | phase1 | fixed | 4 | 0.062 | 0.969 | 0.250 | - |
| bvh_v2 [Phase-I hardened] | PsyCoPref | phase1 | profile_blind | 4 | 0.250 | 0.844 | 0.750 | - |
| bvh_v2 [Phase-I hardened] | PsyCoPref | phase1 | profile_aware | 4 | 0.250 | 0.844 | 0.750 | - |
| bvh_v2 [Phase-I hardened] | PsyCoPref | phase1 | profile_shuffled | 3 | 0.667 | 0.625 | 1.000 | - |

## Paired comparisons
| run | comparison | delta | 95% CI |
|---|---|---|---|
| psycopref_N10_20261004_211201 [base] | aware_vs_blind | 0.079 | [-0.1579, 0.3158] |
| psycopref_N10_20261004_211201 [base] | aware_vs_shuffled | 0.053 | [-0.1579, 0.2632] |
| validation_v2 [base] | aware_vs_blind | 0.075 | [-0.15, 0.3] |
| validation_v2 [base] | aware_vs_shuffled | 0.025 | [-0.15, 0.2] |
