"""Detect and optionally quarantine truncated baseline conversations.

OpenAI outputs are checked against their persisted ``finish_reason``.  Local
Qwen outputs are tokenized with the exact target tokenizer and compared with
the max-completion limit recorded by each method's run manifest.  Quarantined
checkpoints are moved, never deleted, so the resumable matrix runner regenerates
only affected cases.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any


TARGETS = ("qwen7b_instruct", "gpt4o")
METHODS = (
    "direct",
    "skeleton_key",
    "many_shot",
    "red_teaming",
    "pair",
    "tap",
    "crescendo",
    "therapist_crescendo",
    "pcsa_phase2",
)


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def incomplete_openai_contents(input_dir: Path) -> dict[str, list[dict[str, str]]]:
    values: dict[str, list[dict[str, str]]] = {}
    for output in input_dir.glob("gpt4o/*/_openai_batches/target/**/output.jsonl"):
        for line in output.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            body = (record.get("response") or {}).get("body") or {}
            for choice in body.get("choices") or []:
                reason = str(choice.get("finish_reason") or "missing")
                if reason in {"stop", "tool_calls"}:
                    continue
                content = str((choice.get("message") or {}).get("content") or "")
                if content:
                    values.setdefault(content, []).append({
                        "finish_reason": reason,
                        "batch_output": str(output),
                        "custom_id": str(record.get("custom_id") or ""),
                    })
    return values


def qwen_limit(method_dir: Path) -> int:
    manifest = method_dir / "run_manifest.json"
    if not manifest.exists():
        return 4096
    try:
        value = json.loads(manifest.read_text(encoding="utf-8"))
        return int(value.get("target", {}).get("max_completion_tokens") or 4096)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 4096


def conversation_assistant_texts(record: dict[str, Any]) -> list[str]:
    return [
        str(item.get("content") or "")
        for item in record.get("target_conversation") or []
        if item.get("role") == "assistant"
    ]


def audit(input_dir: Path, tokenizer: Any) -> list[dict[str, Any]]:
    openai_incomplete = incomplete_openai_contents(input_dir)
    findings: list[dict[str, Any]] = []
    for target in TARGETS:
        for method in METHODS:
            method_dir = input_dir / target / method
            limit = qwen_limit(method_dir) if target == "qwen7b_instruct" else None
            for path in sorted(method_dir.glob("jmir-full-*.json")):
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                assistant_texts = conversation_assistant_texts(record)
                reasons: list[dict[str, Any]] = []
                if target == "qwen7b_instruct":
                    for turn, text in enumerate(assistant_texts, start=1):
                        tokens = len(tokenizer.encode(text, add_special_tokens=False))
                        # Older checkpoints may have been produced with the former
                        # 2,048-token cap before a resume rewrote run_manifest.json
                        # with the new 4,096-token setting.  Preserve that historical
                        # boundary in the audit so those files cannot be hidden by a
                        # later manifest update.
                        hit_limit = tokens >= int(limit) - 1
                        hit_legacy_limit = tokens in {2047, 2048}
                        if hit_limit or hit_legacy_limit:
                            reasons.append({
                                "kind": "qwen_token_limit",
                                "turn": turn,
                                "tokens": tokens,
                                "configured_limit": limit,
                                "legacy_2048_boundary": hit_legacy_limit,
                            })
                else:
                    for turn, text in enumerate(assistant_texts, start=1):
                        for detail in openai_incomplete.get(text, []):
                            reasons.append({
                                "kind": "openai_incomplete_finish_reason",
                                "turn": turn,
                                **detail,
                            })
                if reasons:
                    findings.append({
                        "target": target,
                        "method": method,
                        "case_id": record.get("case", {}).get("case_id"),
                        "path": str(path),
                        "reasons": reasons,
                    })
    return findings


def quarantine(input_dir: Path, findings: list[dict[str, Any]]) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = input_dir / "_truncated_backups" / stamp
    for finding in findings:
        source = Path(finding["path"])
        relative = source.relative_to(input_dir)
        destination = backup_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        failure = source.with_suffix(".failed.json")
        if failure.exists():
            failure_destination = destination.with_suffix(".failed.json")
            shutil.move(str(failure), str(failure_destination))
        finding["quarantined_to"] = str(destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--qwen-model", default="Qwen/Qwen2.5-7B-Instruct")
    parser.add_argument("--quarantine", action="store_true")
    parser.add_argument("--fail-on-truncated", action="store_true")
    args = parser.parse_args()

    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.qwen_model, local_files_only=True)
    findings = audit(args.input_dir, tokenizer)
    if args.quarantine and findings:
        quarantine(args.input_dir, findings)
    report = {
        "schema_version": "red-persona-truncation-audit-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "input_dir": str(args.input_dir.resolve()),
        "finding_count": len(findings),
        "quarantined": bool(args.quarantine and findings),
        "findings": findings,
    }
    atomic_json(args.input_dir / "truncation_audit.json", report)
    print(json.dumps({"finding_count": len(findings), "quarantined": report["quarantined"]}))
    return 1 if args.fail_on_truncated and findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
