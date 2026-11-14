# studio-forge-mcp

Unified MCP server for isolated **media editing (FFmpeg)**, **vector/document design transformations**, and **semantic artifact memory (`sqlite-vec`)** using Schema-Driven Development (SDD).

## Stack
- **Python 3.14 + FastMCP + Pydantic v2 / pydantic-settings**
- **`sqlite-vec` (`vec0`, `float[64]`)** for local semantic search over transformed assets and recipes
- **Docker `python:3.14-slim`** (`ffmpeg` + `poppler-utils`, non-root `appuser`, `HEALTHCHECK`)
- **QA & Security**: `pytest`, `ruff`, `mypy`

## Quick Start
```bash
uv sync --group dev
uv run pytest -v
uv run studio-forge-mcp
```
