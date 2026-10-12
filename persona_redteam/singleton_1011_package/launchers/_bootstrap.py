"""Shared path bootstrap for the copied singleton snapshot."""
from __future__ import annotations

import os
from pathlib import Path
import sys

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = PACKAGE_ROOT / "src"
DEFAULT_WORKSPACE_ROOT = PACKAGE_ROOT.parent


def activate_source() -> Path:
    """Import copied modules before any modules from the original workspace."""
    source = str(SOURCE_ROOT)
    if not sys.path or sys.path[0] != source:
        sys.path.insert(0, source)
    return SOURCE_ROOT


def subprocess_env(api_key_name: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    prior = env.get("PYTHONPATH", "").strip()
    env["PYTHONPATH"] = str(SOURCE_ROOT) + (os.pathsep + prior if prior else "")
    if api_key_name:
        value = env.get(api_key_name, "").strip()
        if not value:
            raise RuntimeError(f"{api_key_name} is not configured")
        env["OPENAI_API_KEY"] = value
    return env

