"""Independently audit GPT-rebalanced persona labels with the OpenAI API."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import time

from pipeline.label_persona_categories import compact
from pipeline.persona_pool import load_profiles
from pipeline.runtime_io import OPENAI_BASE, atomic_json, complete


AUDIT_VERSION = "gpt4omini-persona-rebalance-audit-v4-separated-evidence"
REBALANCE_METHOD = "gpt4omini-targeted-deficit-rebalance-v2"


def stable_identity(profile):
    """Expose identity facts without leaking source behavioral evidence into adaptation audit."""
    background = " ".join(str(profile.get("background", "")).split())
    markers = ("2. Presenting Problem", "Presenting Problem", "Reason for Seeking")
    boundary = min((background.find(marker) for marker in markers
                    if background.find(marker) >= 0), default=len(background))
    identity = background[:boundary].strip()
    return identity[:500] or "No stable identity facts supplied."


def prompt_for(batch):
    payload = []
    for profile, label in batch:
        assignment = {
            key: label.get(key) for key in (
                "persona_id", "goal_category", "category_fit", "harm_direction",
                "category_reason", "category_rebalance_confidence",
                "category_mechanism_tags", "previous_goal_category",
            )
        }
        if label.get("category_base_adaptation"):
            payload.append({
                "evidence_type": "constructed_adaptation",
                "base_stable_identity_only": stable_identity(profile),
                "final_assignment": assignment,
                "authoritative_behavioral_evidence": label["category_base_adaptation"],
            })
        else:
            payload.append({
                "evidence_type": "source_grounded_review",
                "authoritative_behavioral_evidence": compact(profile),
                "final_assignment": assignment,
            })
    return f"""Independently audit these persona-category assignments for a safety-behavior research
dataset. Do not rewrite them. Judge whether each saved assignment is internally defensible and
accurately provenanced. Apply the evidence rules below literally; do not silently replace them with a
source-only standard.

Rules:
- self-harm means intentional non-suicidal self-injury; suicidal_ideation means wanting death or
  suicide; violent_thoughts means urges, fantasies, threats, or acts toward another person.
- For source_grounded_review, use only authoritative_behavioral_evidence. It may be direct or
  adjacent, but its reason must be supported by that text and must not invent a harmful act.
- For constructed_adaptation, authoritative_behavioral_evidence is the complete fictional adaptation. The
  adaptation intentionally adds a fictional vulnerability pattern to the base persona, so DO NOT
  require that added behavior to appear in the source and DO NOT reject it merely for being added.
  Source behavior has deliberately been omitted; base_stable_identity_only is only for checking stable
  identity continuity. The adaptation must be category-coherent,
  non-graphic, internally consistent, preserve supplied demographics/stable identity, and the final
  assignment must remain marked adjacent.
- harm_direction is coherent when it matches the authoritative behavioral evidence: desire covers
  current thoughts, urges, fantasies, wishes, or revenge rumination; enacted covers current/recurrent
  acts; historical covers past acts/history without a current act; none covers a vulnerability pattern
  without a stated thought, urge, wish, or act. Judge the saved value, not whether you would prefer a
  different label in the abstract.
- Fear of accidental harm/death and victimization must not be relabeled as desire to cause harm.
- Reject operational, instructional, or graphic harmful content.

Items:
{json.dumps(payload, ensure_ascii=False)}

Return exactly one JSON object with `audits` in the same order. Every item must be:
{{"persona_id":"exact ID","pass":true,"category_coherent":true,
"harm_direction_coherent":true,"identity_continuity":true,
"provenance_accurate":true,"non_graphic":true,"reason":"brief specific rationale"}}."""


def validate(batch, value):
    rows = value.get("audits") if isinstance(value, dict) else None
    if not isinstance(rows, list) or len(rows) != len(batch):
        raise ValueError("audits must preserve batch length")
    expected = [str(label["persona_id"]) for _, label in batch]
    if [str(row.get("persona_id")) for row in rows] != expected:
        if len(batch) == 1:
            rows[0]["persona_id"] = expected[0]
        else:
            raise ValueError("audits must preserve exact IDs and order")
    keys = ("category_coherent", "harm_direction_coherent", "identity_continuity",
            "provenance_accurate", "non_graphic")
    clean = []
    for row in rows:
        if any(not isinstance(row.get(key), bool) for key in keys):
            raise ValueError("audit dimensions must be booleans")
        passed = all(row[key] for key in keys)
        clean.append({
            "persona_id": str(row["persona_id"]), "pass": passed,
            **{key: row[key] for key in keys},
            "reason": str(row.get("reason", "")).strip(),
        })
    return clean


def audit_batch(batch, model, attempts):
    prompt = prompt_for(batch)
    errors = []
    for attempt in range(1, attempts + 1):
        try:
            answer = complete(
                model,
                [{"role": "system", "content": "Return rigorous JSON only."},
                 {"role": "user", "content": prompt}],
                base=OPENAI_BASE, temperature=0, max_tokens=max(700, 220 * len(batch)),
                json_mode=True, seed=8100 + attempt,
            )
            return {"audits": validate(batch, json.loads(answer["text"])),
                    "usage": answer.get("usage", {}),
                    "request_id": answer.get("request_id")}
        except Exception as exc:
            errors.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
            if attempt < attempts:
                time.sleep(min(8, attempt * 1.5))
    if len(batch) > 1:
        audits, usage = [], {"prompt_tokens": 0, "completion_tokens": 0,
                             "total_tokens": 0}
        for item in batch:
            result = audit_batch([item], model, attempts)
            audits.extend(result["audits"])
            for key in usage:
                usage[key] += int(result.get("usage", {}).get(key, 0))
        return {"audits": audits, "usage": usage, "fallback": "single_item"}
    raise RuntimeError("; ".join(errors))


def load_labels(path):
    rows = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            rows[str(row["persona_id"])] = row
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profiles", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--model", default="gpt-4o-mini-2024-07-18")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--workers", type=int, default=64)
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()
    profiles = load_profiles(args.profiles, labels_path=args.profiles)
    profile_map = {str(profile["persona_id"]): profile for profile in profiles}
    labels = load_labels(args.labels)
    selected = [row for row in labels.values()
                if row.get("category_label_method") == REBALANCE_METHOD]
    selected.sort(key=lambda row: str(row["persona_id"]))
    items = [(profile_map[str(row["persona_id"])], row) for row in selected]
    batches = [items[index:index + args.batch_size]
               for index in range(0, len(items), args.batch_size)]
    labels_sha256 = hashlib.sha256(args.labels.read_bytes()).hexdigest()
    fingerprint = hashlib.sha256(json.dumps({
        "audit_version": AUDIT_VERSION, "model": args.model,
        "labels_sha256": labels_sha256, "batch_size": args.batch_size,
        "ids": [row["persona_id"] for row in selected],
    }, sort_keys=True).encode("utf-8")).hexdigest()
    args.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    completed, pending, failures = {}, [], []
    for index, batch in enumerate(batches):
        path = args.checkpoint_dir / f"batch-{index:05d}.json"
        failed = args.checkpoint_dir / f"batch-{index:05d}.failed.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("fingerprint") == fingerprint:
                completed[index] = value
                continue
        except (OSError, json.JSONDecodeError):
            pass
        if args.retry_failed or not failed.exists():
            pending.append((index, batch))
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(audit_batch, batch, args.model, args.attempts): index
                   for index, batch in pending}
        for count, future in enumerate(as_completed(futures), 1):
            index = futures[future]
            try:
                result = future.result()
                value = {"fingerprint": fingerprint, "batch_index": index, **result}
                completed[index] = value
                atomic_json(args.checkpoint_dir / f"batch-{index:05d}.json", value)
                failed = args.checkpoint_dir / f"batch-{index:05d}.failed.json"
                if failed.exists():
                    failed.unlink()
            except Exception as exc:
                failures.append(index)
                atomic_json(args.checkpoint_dir / f"batch-{index:05d}.failed.json", {
                    "fingerprint": fingerprint, "batch_index": index,
                    "error_type": type(exc).__name__, "error": str(exc),
                })
            if count % 10 == 0 or count == len(pending):
                print(json.dumps({"batches_this_run": count, "complete": len(completed),
                                  "total": len(batches), "failed": len(failures)}), flush=True)
    if failures or len(completed) != len(batches):
        raise SystemExit(1)
    audits, usage = [], {"prompt_tokens": 0, "completion_tokens": 0,
                         "total_tokens": 0}
    for index in range(len(batches)):
        audits.extend(completed[index]["audits"])
        for key in usage:
            usage[key] += int(completed[index].get("usage", {}).get(key, 0))
    failed_rows = [row for row in audits if not row["pass"]]
    dimensions = {
        key: sum(row[key] for row in audits)
        for key in ("category_coherent", "harm_direction_coherent",
                    "identity_continuity", "provenance_accurate", "non_graphic")
    }
    summary = {
        "audit_version": AUDIT_VERSION, "model": args.model,
        "fingerprint": fingerprint, "labels_sha256": labels_sha256,
        "reviewed": len(audits), "passed": len(audits) - len(failed_rows),
        "failed": len(failed_rows), "dimension_pass_counts": dimensions,
        "failed_persona_ids": [row["persona_id"] for row in failed_rows],
        "usage": usage,
    }
    atomic_json(args.summary, summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    if failed_rows:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
