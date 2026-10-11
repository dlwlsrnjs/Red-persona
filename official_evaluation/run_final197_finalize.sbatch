#!/usr/bin/env bash
#SBATCH --job-name=final197-finalize
#SBATCH --partition=h200
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=24:00:00
set -euo pipefail

REPO_ROOT="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$REPO_ROOT"

WORK="official_evaluation/work/final197"
INPUT="$WORK/input.jsonl"
PENDING="$WORK/pending_input.jsonl"
RB_PENDING="$WORK/rb_pending154.jsonl"
HB_PENDING="$WORK/harmbench_pending154.jsonl"
RB="$WORK/rb_all197.jsonl"
HB="$WORK/harmbench_all197.jsonl"

shopt -s nullglob
shards=("$WORK"/harmbench_shards14/shard-*.jsonl)
if [[ "${#shards[@]}" -ne 14 ]]; then
  echo "expected 14 HarmBench shards, found ${#shards[@]}" >&2
  exit 1
fi
cat "${shards[@]}" > "$HB_PENDING"

persona_redteam/.venv/bin/python official_evaluation/evaluate_b3_behavior.py \
  --input "$PENDING" \
  --output "$RB_PENDING" \
  --work-dir "$WORK/rb_batch" \
  --model gpt-4o-mini \
  --poll-seconds 30

cat "$WORK/seeded_rb.jsonl" "$RB_PENDING" > "$RB"
cat "$WORK/seeded_harmbench.jsonl" "$HB_PENDING" > "$HB"

persona_redteam/.venv/bin/python official_evaluation/aggregate_strict_joint.py \
  --input "$INPUT" \
  --rb "$RB" \
  --harmbench "$HB" \
  --output "$WORK/strict_joint_summary.json" \
  --csv "$WORK/strict_joint_summary.csv" \
  --joined "$WORK/strict_joint_joined.jsonl"
