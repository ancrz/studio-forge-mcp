"""Schema-Driven Development (SDD) Pydantic v2 contracts for studio-forge-mcp."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MediaForgeRequest(BaseModel):
    action: Literal[
        "probe",
        "resize",
        "crop",
        "convert",
        "extract_frame",
        "extract_audio",
        "waveform",
    ]
    input_path: str = Field(..., min_length=1)
    output_path: str | None = None
    width: int | None = Field(default=None, ge=1, le=16384)
    height: int | None = Field(default=None, ge=1, le=16384)
    format: str | None = None


class DesignSuiteRequest(BaseModel):
    action: Literal[
        "svg_optimize",
        "raster_to_svg",
        "extract_palette",
        "wcag_contrast",
        "remove_background",
        "doc_extract",
        "pdf_render_pages",
        "data_sandbox_query",
        "parse_attachment",
    ]
    input_path: str = Field(default="", min_length=0)
    output_path: str | None = None


class ForgeMemoryHit(BaseModel):
    kind: str
    ref_id: str
    summary: str
    distance: float
    engine: Literal["sqlite-vec"] = "sqlite-vec"
