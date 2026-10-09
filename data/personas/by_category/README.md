# Persona category partitions

This directory is a deterministic, category-organized view of the canonical
`../persona_category_labels.jsonl` sidecar. Every canonical persona ID occurs in exactly one file.
The records retain category evidence and construction provenance without duplicating the 88 MB source
persona narratives; join `persona_id` to `../personas.jsonl` to recover each complete source profile.

| Category | File | Rows | Unique base families | Constructed adaptations |
|---|---|---:|---:|---:|
| Anxiety crisis | `anxiety_crisis.jsonl` | 31,046 | 4,187 | 0 |
| Risk-taking behaviours | `risk_taking_behaviours.jsonl` | 102 | 32 | 0 |
| Self-harm | `self-harm.jsonl` | 101 | 100 | 97 |
| Substance abuse or withdrawal | `substance_abuse_or_withdrawal.jsonl` | 216 | 51 | 0 |
| Suicidal ideation | `suicidal_ideation.jsonl` | 168 | 100 | 74 |
| Violent thoughts | `violent_thoughts.jsonl` | 100 | 100 | 97 |
| **Total** |  | **31,733** |  | **268** |

`index.json` is the machine-readable authority for per-file SHA-256 checksums, byte and row counts,
fit distributions, harm-direction distributions, label methods, and constructed-row counts. The
partition-set checksum is
`ed6758cd47fc4e65f895b22965d298604e4e2678c00032c205e36c42827f731a`.

Regenerate and verify the partitions from `persona_redteam/`:

```bash
python3 -m pipeline.export_persona_categories \
  --labels ../data/personas/persona_category_labels.jsonl \
  --output-dir ../data/personas/by_category

python3 -m pipeline.export_persona_categories \
  --labels ../data/personas/persona_category_labels.jsonl \
  --output-dir ../data/personas/by_category --check
```

The partition files are derived views, not independent labels. Edit or regenerate the canonical
sidecar first, rerun the exporter, and require `--check` to pass before committing an update.
