<a id="top"></a>

# studio-forge-mcp

> **Unified MCP Creative, Media & Document Editing Forge** — isolated **FFmpeg** multimedia pipelines, **SVG / raster / document** transformations, **Code Mode** polymorphic dispatch, **Schema-Driven Development (SDD)**, and **`sqlite-vec` semantic memory**.

**Contents:** [What Is This?](#what-is-this) · [Architecture](#architecture) · [Code Mode & Token Efficiency](#code-mode--token-efficiency) · [Technology Stack](#technology-stack) · [Toolset & Credits](#toolset--credits) · [Quick Start](#quick-start) · [Installing in an MCP Ecosystem](#installing-in-an-mcp-ecosystem) · [Configuration](#configuration) · [Testing & Verification](#testing--verification) · [Development & Branching](#development--branching) · [License](#license)

---

## What Is This?

`studio-forge-mcp` is a standalone **Model Context Protocol (MCP)** server designed for AI coding and design agents that need reliable, sandboxed **media, vector, and document editing** without bloating LLM context windows.

Instead of exposing dozens of single-action tools, `studio-forge-mcp` groups domain capabilities behind **3 polymorphic tools** (`media_forge_ffmpeg`, `design_suite_forge`, `forge_memory_search`), strict **Pydantic v2** SDD contracts, path-traversal-guarded sandboxes, and local **`sqlite-vec` (`vec0`, `float[64]`)** vector recall.

> **Current Status (v0.1.0 Scaffold):** SDD schemas, sandbox path guards (`input_path` + `output_path` + symlink escape protection), `sqlite-vec` memory, `/health` endpoint, FastMCP `stdio` & `streamable-http` transports, stable launcher (`scripts/forge-mcp-launch.sh`), E2E protocol tests, and Docker runtime are operational. `media_forge_ffmpeg` and `design_suite_forge` currently validate, guard paths, and index jobs (`status: "ready"`), with full subprocess execution next on the roadmap.

[↑ Back to top](#top)

---

## Architecture

```mermaid
flowchart LR
    CLIENT["AI Agent / MCP Client"] -->|"stdio (forge-mcp-launch.sh)"| MCP["FastMCP Server (Python 3.14 + SDD)"]
    CLIENT -->|"Streamable HTTP :8895 (/mcp)"| MCP
    CLIENT -->|"GET /health"| HEALTH["Health JSON + vec_version()"]
    MCP -->|"media_forge_ffmpeg"| FFMPEG["FFmpeg Engine (probe, resize, crop, convert, audio)"]
    MCP -->|"design_suite_forge"| SUITE["Design & Doc Suite (SVG, Raster, PDF, WCAG, Office)"]
    MCP -->|"forge_memory_search"| VEC["SQLite + sqlite-vec (vec0 float[64])"]
    FFMPEG --> SB["Isolated Sandbox (FORGE_SANDBOX_ROOT)"]
    SUITE --> SB
```

[↑ Back to top](#top)

---

## Code Mode & Token Efficiency

`studio-forge-mcp` adopts **Code Mode** principles to minimize tool-catalog bloat and LLM round-trips:

| Capability | Status | Details |
|---|---|---|
| **Polymorphic Domain Dispatch** | Implemented | 3 cohesive tools (`media_forge_ffmpeg`, `design_suite_forge`, `forge_memory_search`) replace 13+ single-purpose tools, keeping MCP tool schemas compact. |
| **Schema-Driven Development (SDD)** | Implemented | Pydantic v2 contracts (`src/studio_forge_mcp/schemas.py`) validate inputs at the boundary before any handler or subprocess runs. |
| **Sandboxed Path Normalization** | Implemented | `_safe_sandbox_path()` resolves both `input_path` and `output_path` inside `FORGE_SANDBOX_ROOT`, blocking `..` traversal and escaping symlinks. |
| **Semantic Auto-Indexing** | Implemented | Executed jobs are auto-indexed into `sqlite-vec` (`vec0` `float[64]`) for low-token recall via `forge_memory_search`. |
| **Batch DAG & Field Projection** | Planned | Multi-step single-turn batching (`$prev.*` piping), `select_fields` projection, and `verbosity` tiers (`terse` / `summary` / `detail`). |

```mermaid
flowchart TD
    REQ["Agent Tool Call (Polymorphic Dispatch)"] --> SDD["Pydantic v2 SDD Validation"]
    SDD --> GUARD["Sandbox Guard (_safe_sandbox_path on input + output)"]
    GUARD --> EXEC["Media / Design Handler"]
    EXEC --> IDX["Auto-Index Summary in sqlite-vec (vec0)"]
    IDX --> COMPACT["Return Compact JSON Result"]
```

[↑ Back to top](#top)

---

## Technology Stack

| Layer | Technology | Role | License |
|---|---|---|---|
| **Runtime** | Python `>=3.14` (`python:3.14-slim`) | Core language & container base | PSF-2.0 |
| **MCP Framework** | `mcp[cli]` (`FastMCP`) + `uvicorn` | `stdio` and `streamable-http` MCP transports | MIT / BSD-3-Clause |
| **SDD & Config** | `pydantic` v2 + `pydantic-settings` | Boundary schema validation & `FORGE_*` env config | MIT |
| **Vector Memory** | `sqlite-vec` (`v0.1.9`, `vec0` `float[64]`) | Local 64-d character-trigram semantic recall | MIT OR Apache-2.0 |
| **Media & Docs (Container)** | `ffmpeg` + `poppler-utils` | External CLI engines for audio/video/PDF pipelines | LGPL/GPL (external CLI) |
| **Tooling & QA** | `uv`, `pytest`, `pytest-asyncio`, `httpx`, `ruff`, `mypy` | Dependency lock, E2E/unit testing, lint, strict typing | MIT / Apache-2.0 / BSD |

[↑ Back to top](#top)

---

## Toolset & Credits

### Multimedia Engine — Powered by [FFmpeg](https://ffmpeg.org/)
Full credit to the **[FFmpeg](https://ffmpeg.org/)** project for the underlying audio, video, and frame-processing engine exposed through `media_forge_ffmpeg`:
- `probe`: inspect streams, codecs, resolution, duration, and container metadata.
- `resize` / `crop`: deterministic dimension transforms with bounded SDD constraints (`1..16384`).
- `convert`: transcode across container/image formats.
- `extract_audio` / `waveform`: isolate audio tracks and generate visual waveform previews.

### Design, Vector & Document Suite (`design_suite_forge`)
- `svg_optimize` / `raster_to_svg`: clean and vectorize artwork for web and design tools.
- `extract_palette` / `wcag_contrast`: extract color palettes and verify WCAG accessibility ratios.
- `doc_extract` / `pdf_render_pages`: extract structured text/tables and render PDF pages (powered by Poppler and Python tooling).

### Semantic Artifact Memory (`forge_memory_search`)
- Powered by **`sqlite-vec` (`v0.1.9`, `vec0` `float[64]`)** with deterministic 64-dimensional character-trigram embeddings (`src/studio_forge_mcp/memory.py`) for instant, zero-external-API recall over past `media_job` and `design_job` runs.

[↑ Back to top](#top)

---

## Quick Start

```bash
uv sync --group dev
uv run pytest -v
uv run studio-forge-mcp
```

### Docker (`python:3.14-slim`)

```bash
docker build -t studio-forge-mcp:0.1.0 .
docker run --rm -p 8895:8895 -v /tmp/studio-forge-sandbox:/sandbox studio-forge-mcp:0.1.0
```

Health endpoint: `GET http://127.0.0.1:8895/health`

[↑ Back to top](#top)

---

## Installing in an MCP Ecosystem

`studio-forge-mcp` supports both **`stdio`** (for local desktop/IDE MCP clients such as Antigravity `~/.gemini/config/mcp_config.json`) and **Streamable HTTP** (for Docker or remote deployments on `FORGE_HOST:FORGE_PORT`, default `http://127.0.0.1:8895/mcp`).

### Option A: Local `stdio` Launcher (Recommended for Desktop/IDE Clients)

Register [`scripts/forge-mcp-launch.sh`](scripts/forge-mcp-launch.sh) in your `mcp_config.json`:

```json
{
  "mcpServers": {
    "studio-forge-mcp": {
      "command": "/home/ancruz/Documents/workspaces/studio-forge-mcp/scripts/forge-mcp-launch.sh",
      "disabled": false
    }
  }
}
```

### Option B: Streamable HTTP (Local or Docker)

1. Start the server (`uv run studio-forge-mcp` or `docker run -d --name studio-forge-mcp -p 8895:8895 -v /path/to/sandbox:/sandbox studio-forge-mcp:0.1.0`).
2. Register the HTTP endpoint in any Streamable HTTP-capable MCP client:

```json
{
  "mcpServers": {
    "studio-forge-mcp": {
      "url": "http://127.0.0.1:8895/mcp"
    }
  }
}
```

[↑ Back to top](#top)

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `FORGE_HOST` | `0.0.0.0` | Server bind host |
| `FORGE_PORT` | `8895` | Streamable HTTP / health port |
| `FORGE_TRANSPORT` | `streamable-http` | MCP transport (`streamable-http` or `stdio`) |
| `FORGE_SANDBOX_ROOT` | `/tmp/studio-forge-sandbox` | Isolated root directory for media/design files (Docker: `/sandbox`) |
| `FORGE_MEMORY_DB` | `/tmp/studio-forge-sandbox/forge_memory.db` | SQLite + `sqlite-vec` database path (Docker: `/sandbox/forge_memory.db`) |

[↑ Back to top](#top)

---

## Testing & Verification

```mermaid
flowchart LR
    UNIT["test_studio_forge.py (Core SDD, Memory, CLI)"] --> PYTEST["uv run pytest -v (23 tests)"]
    GAPS["test_omission_gaps.py (Boundaries, Symlink/Output Guards)"] --> PYTEST
    E2E["test_e2e.py (Real stdio + Streamable HTTP MCP)"] --> PYTEST
    PYTEST --> QA["ruff check . + mypy src tests"]
```

[↑ Back to top](#top)

---

## Development & Branching

- **Branches**: `main` (stable releases) and `dev` (active development).
- **Quality checks**:

```bash
uv run pytest -v
uv run ruff check .
uv run mypy src tests
```

[↑ Back to top](#top)

---

## License

This project is licensed under the **[Apache License 2.0](LICENSE)**.

`studio-forge-mcp` uses permissive dependencies (`MIT`, `BSD-3-Clause`, `MIT OR Apache-2.0`) and invokes external system binaries (`ffmpeg`, `poppler-utils`) in isolated subprocesses rather than linking copyleft libraries directly, keeping **Apache-2.0** clean and conflict-free across the stack.

[↑ Back to top](#top)
