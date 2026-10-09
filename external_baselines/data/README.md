# External-baseline data

`baseline_persona_assignments_official_500.jsonl` is the canonical persona map for every
external baseline run. Its 500 `case_id` values and order exactly match
`../../data/red_persona_official_500.jsonl`.

The source goals use `jmir-test-*` IDs while generated RED-Persona cases use `jmir-full-*` IDs.
`source_goal_id` and `canonical_source_index` preserve that crosswalk; consumers must not join the
two namespaces by string equality or truncate the first 500 source rows.

Current invariants:

- rows: 500
- unique official case IDs: 500
- unique assigned persona IDs: 500
- SHA-256: `43316f55cd7576eaac4ad0f24c515e98efa845fc728b0b0427c665322b54214e`
- official cohort SHA-256: `2163b518bbc1a266f83c27c3dea5c0f6a7edc3ac7671cb7ee7a75ac143d61f43`

Regenerate it from the source 625 goals, pathology routes, persona pool, and official cohort index:

```bash
python external_baselines/prepare_baseline_personas.py
```
