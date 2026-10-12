"""Load named API credentials without printing or persisting their values."""
from __future__ import annotations

import os
from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parents[2]
PERSONA_ROOT = PACKAGE_ROOT.parent


def credential(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    for path in (PERSONA_ROOT.parent / ".env", PERSONA_ROOT / ".env"):
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(name + "="):
                value = line.split("=", 1)[1].strip().strip('"').strip("'")
                if value:
                    return value
    raise RuntimeError(f"{name} is not configured")
