"""Unit tests for studio-forge-mcp SDD schemas, sqlite-vec memory, and sandbox guards."""

from __future__ import annotations

from pathlib import Path

import pytest

from studio_forge_mcp.memory import ForgeVectorMemory
from studio_forge_mcp.schemas import DesignSuiteRequest, MediaForgeRequest
from studio_forge_mcp.server import _safe_sandbox_path


def test_sdd_requests_validate() -> None:
    m = MediaForgeRequest(action="resize", input_path="clips/intro.mp4", width=1280, height=720)
    d = DesignSuiteRequest(action="svg_optimize", input_path="assets/logo.svg")
    assert m.width == 1280
    assert d.action == "svg_optimize"


def test_sqlite_vec_memory_roundtrip(tmp_path: Path) -> None:
    mem = ForgeVectorMemory(tmp_path / "forge.db")
    assert mem.vec_version().startswith("v")

    mem.index("media_job", "clips/intro.mp4", "ffmpeg resize 1280x720 mp4 trailer")
    mem.index("design_job", "assets/logo.svg", "svg_optimize brand vector logo")

    hits = mem.search("resize 1280x720 mp4", kind="media_job", limit=3)
    assert len(hits) == 1
    assert hits[0].ref_id == "clips/intro.mp4"
    assert hits[0].engine == "sqlite-vec"


def test_sandbox_path_blocks_traversal() -> None:
    with pytest.raises(ValueError, match="escapes sandbox"):
        _safe_sandbox_path("../../etc/passwd")
