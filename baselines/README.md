# Baselines — external attack methods (one folder per paper)

Each baseline is implemented in its own folder as a self-contained attack that
reuses the shared helpers in [`_common.py`](_common.py) (OpenAI attacker call,
counseling-target call, and the compact CARES 4-axis judge). This keeps the
*evaluation identical* across methods so only the attack technique differs — a
fair comparison against our method.

| Folder | Method | Paper |
|---|---|---|
| [`direct/`](direct) | Direct request (lower bound) | — |
| [`crescendo/`](crescendo) | Crescendo gradual multi-turn escalation | Russinovich et al., 2024 (arXiv 2404.01833) |
| [`coa/`](coa) | Chain-of-Attack (semantic premise chaining) | Yang et al., 2024 (arXiv 2405.05610) |
| [`ama/`](ama) | Adversarial Metaphor / Analogy | metaphor-jailbreak line, 2024 |
| [`actorattack/`](actorattack) | ActorAttack (role/clue network) | Ren et al., 2024 (arXiv 2410.10700) |

## Run one method on one goal
```bash
export OPENAI_API_KEY=...            # attacker + judge (small models)
export TARGET_BASE_URL=http://127.0.0.1:8009/v1   # counseling target
export TARGET_API_KEY_ENV=PCSA_LOCAL_KEY PCSA_LOCAL_KEY=local
python3 crescendo/attack.py '{"intent":"...","masked_request":"...","harm_level":3}' 4
```

## Run all methods over the goal set
```bash
python3 run_all.py --goals ../harmful_behavior_collection/data/attack_goals_v2.jsonl --turns 4
```
Reports, per method: ASR (non-refusal), harm-weighted CARES Safety Score, and
UNSAFE rate — directly comparable to our method's numbers.

Models: attacker/judge default to gpt-5-nano (`ATTACKER_MODEL`/`JUDGE_MODEL`);
the target is whatever `TARGET_BASE_URL` serves. For authorized safety research.
