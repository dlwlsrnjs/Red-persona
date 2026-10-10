#!/usr/bin/env bash
set -euo pipefail

BASELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${PYRIT_VENV:-$BASELINE_DIR/.venv}"
PYTHON_BIN="${PYRIT_PYTHON:-python3.12}"
export UV_CACHE_DIR="${UV_CACHE_DIR:-$BASELINE_DIR/.uv-cache}"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required: https://docs.astral.sh/uv/" >&2
  exit 1
fi
if [[ ! -f "$BASELINE_DIR/vendor/pyrit/pyproject.toml" ]]; then
  echo "PyRIT submodule is missing. Run: git submodule update --init --recursive" >&2
  exit 1
fi

uv venv --python "$PYTHON_BIN" --allow-existing "$VENV_DIR"
uv pip install --python "$VENV_DIR/bin/python" --editable "$BASELINE_DIR/vendor/pyrit"
uv pip install --python "$VENV_DIR/bin/python" "tiktoken==0.14.0"
"$VENV_DIR/bin/python" -c 'from importlib.metadata import version; value = version("pyrit"); assert value == "1.1.0", value; print(f"PyRIT {value} environment ready")'
"$VENV_DIR/bin/python" -c 'from importlib.metadata import version; value = version("tiktoken"); assert value == "0.14.0", value; print(f"tiktoken {value} evaluator dependency ready")'
