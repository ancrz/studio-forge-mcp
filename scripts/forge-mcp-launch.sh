#!/usr/bin/env bash
# Stable stdio MCP launcher for studio-forge-mcp.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [[ -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
    FORGE_PYTHON="$PROJECT_ROOT/.venv/bin/python"
else
    FORGE_PYTHON="$(command -v python3)"
fi

export PYTHONPATH="$PROJECT_ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
cd "$PROJECT_ROOT"
exec "$FORGE_PYTHON" -m studio_forge_mcp.server --transport stdio "$@"
