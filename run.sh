#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON:-python}"
exec "$PYTHON_BIN" "$SCRIPT_DIR/run_sg_endtoend.py" "$@"
