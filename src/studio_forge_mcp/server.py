"""FastMCP entry point for studio-forge-mcp."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

from studio_forge_mcp import __version__
from studio_forge_mcp.config import settings
from studio_forge_mcp.memory import ForgeVectorMemory
from studio_forge_mcp.schemas import DesignSuiteRequest, MediaForgeRequest

mcp = FastMCP("studio-forge-mcp", host=settings.host, port=settings.port)
memory_store = ForgeVectorMemory(settings.memory_db)


def _safe_sandbox_path(rel_path: str) -> Path:
    root = Path(settings.sandbox_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    candidate = (root / rel_path.lstrip("/")).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Path escapes sandbox root")
    return candidate


@mcp.custom_route("/health", methods=["GET"])
async def health_route(_request: Any) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "version": __version__,
            "sqlite_vec": memory_store.vec_version(),
        }
    )


@mcp.tool()
def media_forge_ffmpeg(
    action: str,
    input_path: str,
    output_path: str | None = None,
    width: int | None = None,
    height: int | None = None,
    format: str | None = None,
) -> dict[str, Any]:
    """Validate and dispatch an FFmpeg media transformation inside the sandbox."""
    req = MediaForgeRequest(
        action=action,  # type: ignore[arg-type]
        input_path=input_path,
        output_path=output_path,
        width=width,
        height=height,
        format=format,
    )
    resolved_in = _safe_sandbox_path(req.input_path)
    memory_store.index("media_job", req.input_path, f"ffmpeg {req.action} on {req.input_path}")
    return {"status": "ready", "action": req.action, "input": str(resolved_in)}


@mcp.tool()
def design_suite_forge(
    action: str,
    input_path: str,
    output_path: str | None = None,
) -> dict[str, Any]:
    """Validate and dispatch a vector/document design transformation inside the sandbox."""
    req = DesignSuiteRequest(
        action=action,  # type: ignore[arg-type]
        input_path=input_path,
        output_path=output_path,
    )
    resolved_in = _safe_sandbox_path(req.input_path)
    memory_store.index("design_job", req.input_path, f"suite {req.action} on {req.input_path}")
    return {"status": "ready", "action": req.action, "input": str(resolved_in)}


@mcp.tool()
def forge_memory_search(
    query: str,
    kind: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Search semantic sqlite-vec memory of prior media and design transformations."""
    hits = memory_store.search(query, kind=kind, limit=limit)
    return {"status": "ok", "hits": [h.model_dump() for h in hits]}


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
