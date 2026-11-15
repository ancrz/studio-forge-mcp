"""FastMCP entry point for studio-forge-mcp."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Literal, cast

from mcp.server.fastmcp import FastMCP
from starlette.responses import JSONResponse

from studio_forge_mcp import __version__
from studio_forge_mcp.code_mode import compact_payload, execute_code_pipeline
from studio_forge_mcp.config import settings
from studio_forge_mcp.media_engine import dispatch_media_action
from studio_forge_mcp.memory import ForgeVectorMemory
from studio_forge_mcp.sandbox import safe_sandbox_path
from studio_forge_mcp.schemas import DesignSuiteRequest, MediaForgeRequest
from studio_forge_mcp.suite_engine import dispatch_suite_action

mcp = FastMCP("studio-forge-mcp", host=settings.host, port=settings.port)
memory_store = ForgeVectorMemory(settings.memory_db)


def _safe_sandbox_path(rel_path: str) -> Path:
    return safe_sandbox_path(rel_path)


@mcp.custom_route("/health", methods=["GET"])
async def health_route(_request: Any) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "version": __version__,
            "code_mode": True,
            "sqlite_vec": memory_store.vec_version(),
        }
    )


@mcp.tool()
async def media_forge_ffmpeg(
    action: str = "probe",
    input_path: str = "",
    output_path: str | None = None,
    width: int | None = None,
    height: int | None = None,
    format: str | None = None,
    mode: str = "call",
    params: dict[str, Any] | None = None,
    steps: list[dict[str, Any]] | None = None,
    vars: dict[str, Any] | None = None,
    verbosity: str = "summary",
    return_only: str = "summary",
    select_fields: list[str] | None = None,
) -> dict[str, Any]:
    """Execute sandboxed FFmpeg media actions or Code Mode multi-step pipelines."""
    m = (mode or "call").strip().lower()
    if m == "discover":
        return {
            "status": "OK",
            "service": "studio-forge-mcp",
            "code_mode": True,
            "actions": [
                "probe",
                "resize",
                "crop",
                "convert",
                "extract_frame",
                "extract_audio",
                "waveform",
            ],
            "piping": "$steps.<step_id>.output_path",
            "verbosity_levels": ["minimal", "summary", "full"],
        }
    if m == "pipeline":
        res = await execute_code_pipeline(
            steps or [],
            dispatch_media_action,
            vars_dict=vars,
            return_only=return_only,
            select_fields=select_fields,
            verbosity=verbosity,
        )
        memory_store.index("media_job", "pipeline", f"ffmpeg pipeline ({len(steps or [])} steps)")
        return res

    merged: dict[str, Any] = dict(params or {})
    if input_path and "input_path" not in merged:
        merged["input_path"] = input_path
    if output_path is not None and "output_path" not in merged:
        merged["output_path"] = output_path
    if width is not None and "width" not in merged:
        merged["width"] = width
    if height is not None and "height" not in merged:
        merged["height"] = height
    if format is not None and "format" not in merged:
        merged["format"] = format

    req = MediaForgeRequest(
        action=action,  # type: ignore[arg-type]
        input_path=str(merged.get("input_path") or ""),
        output_path=merged.get("output_path"),
        width=merged.get("width"),
        height=merged.get("height"),
        format=merged.get("format"),
    )
    if req.output_path is not None:
        _safe_sandbox_path(req.output_path)
    res = await dispatch_media_action(req.action, merged)
    memory_store.index("media_job", req.input_path, f"ffmpeg {req.action} on {req.input_path}")
    return compact_payload(
        res,
        verbosity=verbosity,
        return_only=return_only,
        select_fields=select_fields,
    )


@mcp.tool()
async def design_suite_forge(
    action: str = "doc_extract",
    input_path: str = "",
    output_path: str | None = None,
    mode: str = "call",
    params: dict[str, Any] | None = None,
    steps: list[dict[str, Any]] | None = None,
    vars: dict[str, Any] | None = None,
    verbosity: str = "summary",
    return_only: str = "summary",
    select_fields: list[str] | None = None,
) -> dict[str, Any]:
    """Execute sandboxed document, data, vector, attachment, or Code Mode pipelines."""
    m = (mode or "call").strip().lower()
    if m == "discover":
        return {
            "status": "OK",
            "service": "studio-forge-mcp",
            "code_mode": True,
            "actions": [
                "svg_optimize",
                "raster_to_svg",
                "extract_palette",
                "wcag_contrast",
                "remove_background",
                "doc_extract",
                "pdf_render_pages",
                "data_sandbox_query",
                "parse_attachment",
            ],
            "piping": "$steps.<step_id>.output_path",
            "verbosity_levels": ["minimal", "summary", "full"],
        }
    if m == "pipeline":
        res = await execute_code_pipeline(
            steps or [],
            dispatch_suite_action,
            vars_dict=vars,
            return_only=return_only,
            select_fields=select_fields,
            verbosity=verbosity,
        )
        memory_store.index("design_job", "pipeline", f"suite pipeline ({len(steps or [])} steps)")
        return res

    merged: dict[str, Any] = dict(params or {})
    if input_path and "input_path" not in merged:
        merged["input_path"] = input_path
    if output_path is not None and "output_path" not in merged:
        merged["output_path"] = output_path

    req = DesignSuiteRequest(
        action=action,  # type: ignore[arg-type]
        input_path=str(merged.get("input_path") or ""),
        output_path=merged.get("output_path"),
    )
    if req.action != "wcag_contrast" and not req.input_path:
        raise ValueError("input_path is required for this action")
    if req.output_path is not None:
        _safe_sandbox_path(req.output_path)

    res = await dispatch_suite_action(req.action, merged)
    ref = req.input_path or f"wcag:{merged.get('fg_hex', '')}:{merged.get('bg_hex', '')}"
    memory_store.index("design_job", ref, f"suite {req.action} on {ref}")
    return compact_payload(
        res,
        verbosity=verbosity,
        return_only=return_only,
        select_fields=select_fields,
    )


@mcp.tool()
def forge_memory_search(
    query: str,
    kind: str | None = None,
    limit: int = 5,
) -> dict[str, Any]:
    """Search semantic sqlite-vec memory of prior media and design transformations."""
    hits = memory_store.search(query, kind=kind, limit=limit)
    return {"status": "ok", "hits": [h.model_dump() for h in hits]}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="studio-forge-mcp FastMCP server")
    parser.add_argument(
        "--transport",
        choices=["streamable-http", "stdio"],
        default=settings.transport,
        help="MCP transport mode (default: FORGE_TRANSPORT or streamable-http)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    transport = cast(Literal["streamable-http", "stdio"], args.transport)
    mcp.run(transport=transport)


if __name__ == "__main__":
    main()
