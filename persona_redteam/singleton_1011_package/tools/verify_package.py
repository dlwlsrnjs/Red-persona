"""Verify copied source hashes, excluded features, and optional input hashes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WORKSPACE_ROOT = PACKAGE_ROOT.parent


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(workspace_root: Path, check_inputs: bool = True) -> dict:
    manifest = json.loads((PACKAGE_ROOT / "PACKAGE_MANIFEST.json").read_text(encoding="utf-8"))
    errors = []
    expected_snapshot_paths = set(manifest["snapshot_files"])
    actual_snapshot_paths = {
        str(path.relative_to(PACKAGE_ROOT))
        for path in (PACKAGE_ROOT / "src").rglob("*")
        if path.is_file() and path.suffix != ".pyc"
    }
    for relative in sorted(actual_snapshot_paths - expected_snapshot_paths):
        errors.append(f"unexpected snapshot file: {relative}")
    for relative in sorted(expected_snapshot_paths - actual_snapshot_paths):
        errors.append(f"missing snapshot file: {relative}")
    for relative, expected in manifest["snapshot_files"].items():
        path = PACKAGE_ROOT / relative
        if path.is_file() and sha256(path) != expected:
            errors.append(f"snapshot hash mismatch: {relative}")
    for relative in manifest["excluded_paths"]:
        if (PACKAGE_ROOT / relative).exists():
            errors.append(f"excluded path is present: {relative}")
    input_checks = []
    if check_inputs:
        for item in manifest["external_inputs"]:
            path = workspace_root / item["path"]
            actual = sha256(path) if path.is_file() else None
            passed = actual == item["sha256"]
            input_checks.append({"path": str(path), "passed": passed})
            if not passed:
                errors.append(f"external input mismatch: {path}")
    return {
        "package": str(PACKAGE_ROOT),
        "snapshot_files_checked": len(manifest["snapshot_files"]),
        "external_inputs": input_checks,
        "passed": not errors,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, default=DEFAULT_WORKSPACE_ROOT)
    parser.add_argument("--skip-inputs", action="store_true")
    args = parser.parse_args()
    result = verify(args.workspace_root.resolve(), not args.skip_inputs)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
