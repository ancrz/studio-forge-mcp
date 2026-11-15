"""Omission-gap test battery for studio-forge-mcp (SDD, sandbox, memory, MCP tools)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from studio_forge_mcp import __version__, server
from studio_forge_mcp.memory import EMBEDDING_DIM, ForgeVectorMemory, compute_embedding
from studio_forge_mcp.schemas import DesignSuiteRequest, MediaForgeRequest


class TestSDDBoundaries:
    @pytest.mark.parametrize("bad_width", [0, -1, 16385])
    def test_media_width_out_of_bounds(self, bad_width: int) -> None:
        with pytest.raises(ValidationError):
            MediaForgeRequest(action="resize", input_path="a.mp4", width=bad_width)

    @pytest.mark.parametrize("bad_height", [0, -10, 16385])
    def test_media_height_out_of_bounds(self, bad_height: int) -> None:
        with pytest.raises(ValidationError):
            MediaForgeRequest(action="crop", input_path="a.mp4", height=bad_height)

    def test_media_valid_extreme_dimensions(self) -> None:
        req = MediaForgeRequest(action="resize", input_path="a.mp4", width=1, height=16384)
        assert req.width == 1
        assert req.height == 16384

    def test_rejects_empty_input_path_and_invalid_actions(self) -> None:
        with pytest.raises(ValidationError):
            MediaForgeRequest(action="probe", input_path="")
        with pytest.raises(ValidationError):
            MediaForgeRequest(action="rm_rf", input_path="a.mp4")  # type: ignore[arg-type]
        with pytest.raises(ValidationError):
            DesignSuiteRequest(action="unknown", input_path="a.svg")  # type: ignore[arg-type]


class TestSandboxGuards:
    def test_leading_slash_stays_inside_sandbox(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(server.settings, "sandbox_root", str(tmp_path))
        resolved = server._safe_sandbox_path("/clips/intro.mp4")
        assert resolved == (tmp_path / "clips/intro.mp4").resolve()

    def test_symlink_escape_is_blocked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        outside = tmp_path / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        (sandbox / "escape.txt").symlink_to(outside)

        monkeypatch.setattr(server.settings, "sandbox_root", str(sandbox))
        with pytest.raises(ValueError, match="escapes sandbox"):
            server._safe_sandbox_path("escape.txt")

    async def test_output_path_traversal_blocked_in_tools(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(server.settings, "sandbox_root", str(tmp_path))
        monkeypatch.setattr(server, "memory_store", ForgeVectorMemory(tmp_path / "mem.db"))
        (tmp_path / "in.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")

        with pytest.raises(ValueError, match="escapes sandbox"):
            await server.media_forge_ffmpeg(
                action="resize",
                input_path="in.mp4",
                output_path="../../outside.mp4",
                width=640,
                height=360,
            )

        with pytest.raises(ValueError, match="escapes sandbox"):
            await server.design_suite_forge(
                action="svg_optimize",
                input_path="in.svg",
                output_path="../../outside.svg",
            )


class TestMemoryEdgeCases:
    def test_empty_embedding_is_zero_vector_and_deterministic(self) -> None:
        empty = compute_embedding("   ")
        assert len(empty) == EMBEDDING_DIM
        assert all(v == 0.0 for v in empty)
        assert compute_embedding("FFmpeg  Resize") == compute_embedding("ffmpeg resize")

    def test_empty_db_search_returns_empty_list(self, tmp_path: Path) -> None:
        mem = ForgeVectorMemory(tmp_path / "empty.db")
        assert mem.search("anything") == []

    def test_upsert_overwrites_summary_and_unfiltered_search(self, tmp_path: Path) -> None:
        mem = ForgeVectorMemory(tmp_path / "upsert.db")
        id1 = mem.index("media_job", "clips/a.mp4", "initial probe")
        id2 = mem.index("media_job", "clips/a.mp4", "updated resize 1080p")
        assert id1 == id2

        mem.index("design_job", "assets/b.svg", "svg_optimize 1080p banner")
        hits = mem.search("1080p", kind=None, limit=2)
        assert len(hits) == 2
        summaries = {h.ref_id: h.summary for h in hits}
        assert summaries["clips/a.mp4"] == "updated resize 1080p"


class TestMCPServerIntegration:
    async def test_mcp_lists_expected_polymorphic_tools(self) -> None:
        tools = await server.mcp.list_tools()
        names = {t.name for t in tools}
        assert names == {"media_forge_ffmpeg", "design_suite_forge", "forge_memory_search"}

    async def test_health_route_returns_version_and_sqlite_vec(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(server, "memory_store", ForgeVectorMemory(tmp_path / "health.db"))
        resp = await server.health_route(None)
        payload = json.loads(bytes(resp.body).decode("utf-8"))
        assert resp.status_code == 200
        assert payload["status"] == "ok"
        assert payload["version"] == __version__
        assert payload["sqlite_vec"].startswith("v")

    async def test_tools_roundtrip_with_output_and_memory_recall(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sandbox = tmp_path / "sb"
        sandbox.mkdir(parents=True, exist_ok=True)
        (sandbox / "assets").mkdir()
        (sandbox / "docs").mkdir()
        (sandbox / "assets" / "logo.svg").write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><g/><rect width="10" height="10"/></svg>',
            encoding="utf-8",
        )
        (sandbox / "docs" / "spec.txt").write_text("Topos integrity spec v1", encoding="utf-8")

        monkeypatch.setattr(server.settings, "sandbox_root", str(sandbox))
        monkeypatch.setattr(server, "memory_store", ForgeVectorMemory(tmp_path / "rt.db"))

        svg_res = await server.design_suite_forge(
            action="svg_optimize",
            input_path="assets/logo.svg",
            output_path="out/logo.min.svg",
        )
        assert svg_res["status"] == "OK"
        assert (sandbox / "out" / "logo.min.svg").exists()

        doc_res = await server.design_suite_forge(
            action="doc_extract",
            input_path="docs/spec.txt",
        )
        assert doc_res["status"] == "OK"
        assert "Topos integrity spec v1" in doc_res["content"]

        recall = server.forge_memory_search(query="doc_extract docs/spec.txt", limit=5)
        assert recall["status"] == "ok"
        assert len(recall["hits"]) >= 1
