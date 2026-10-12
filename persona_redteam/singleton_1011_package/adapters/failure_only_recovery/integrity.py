"""Integrity checks for the preserved recovery implementation."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ADAPTER_ROOT = Path(__file__).resolve().parent


def verify_preserved_sources() -> list[str]:
    provenance = json.loads(
        (ADAPTER_ROOT / "PROVENANCE.json").read_text(encoding="utf-8")
    )
    failures = []
    for relative, metadata in provenance["preserved_sources"].items():
        path = ADAPTER_ROOT / relative
        if not path.is_file():
            failures.append(f"missing preserved source: {relative}")
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != metadata["sha256"]:
            failures.append(f"preserved source hash mismatch: {relative}")
    return failures


def require_preserved_sources() -> None:
    failures = verify_preserved_sources()
    if failures:
        raise RuntimeError("; ".join(failures))
