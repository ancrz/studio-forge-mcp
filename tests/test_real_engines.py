"""Tests for real absorbed engines: Code Mode, attachments, docs, data, and media."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from docx import Document
from openpyxl import Workbook
from PIL import Image

from studio_forge_mcp import media_engine, server
from studio_forge_mcp.attachments import parse_uploaded_attachment, safe_zip_member_name
from studio_forge_mcp.memory import ForgeVectorMemory


def _make_zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


class TestAttachmentsSecurityAndParsing:
    def test_blocks_zip_slip_and_too_many_entries(self) -> None:
        assert not safe_zip_member_name("../secret.txt")
        assert not safe_zip_member_name("/abs/secret.txt")
        assert not safe_zip_member_name("a\\b.txt")
        assert safe_zip_member_name("docs/readme.md")

        evil_zip = _make_zip({"../../evil.txt": b"pwn"})
        with pytest.raises(ValueError, match="Unsafe ZIP member"):
            parse_uploaded_attachment(filename="evil.zip", content_bytes=evil_zip)

        bomb_entries = {f"f_{i}.txt": b"x" for i in range(251)}
        bomb_zip = _make_zip(bomb_entries)
        with pytest.raises(ValueError, match="250 ZIP entries"):
            parse_uploaded_attachment(filename="bomb.zip", content_bytes=bomb_zip)

    def test_parses_valid_zip_and_office_hint(self) -> None:
        ok_zip = _make_zip({"manifest.json": b'{"ok":true}', "notes.md": b"# Hi"})
        res = parse_uploaded_attachment(filename="bundle.zip", content_bytes=ok_zip)
        assert res["kind"] == "zip_archive"
        assert res["meta"]["entry_count"] == 2

        pdf_res = parse_uploaded_attachment(filename="arch.pdf", content_bytes=b"%PDF-1.4")
        assert pdf_res["kind"] == "pdf"
        assert "doc_extract" in pdf_res["context_text"]


class TestSuiteRealEngines:
    async def test_doc_extract_docx_xlsx_and_data_query(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(server.settings, "sandbox_root", str(tmp_path))
        monkeypatch.setattr(server, "memory_store", ForgeVectorMemory(tmp_path / "m.db"))

        doc = Document()
        doc.add_paragraph("Runbook de despliegue")
        tbl = doc.add_table(rows=2, cols=2)
        tbl.cell(0, 0).text = "Env"
        tbl.cell(0, 1).text = "Port"
        tbl.cell(1, 0).text = "prod"
        tbl.cell(1, 1).text = "8895"
        doc.save(str(tmp_path / "runbook.docx"))

        docx_res = await server.design_suite_forge(action="doc_extract", input_path="runbook.docx")
        assert docx_res["status"] == "OK"
        assert "Runbook de despliegue" in docx_res["content"]
        assert "prod | 8895" in docx_res["content"]

        wb = Workbook()
        ws = wb.active
        assert ws is not None
        ws.title = "Nodes"
        ws.append(["host", "role"])
        ws.append(["node-1", "gateway"])
        wb.save(str(tmp_path / "inv.xlsx"))

        xlsx_res = await server.design_suite_forge(action="doc_extract", input_path="inv.xlsx")
        assert xlsx_res["status"] == "OK"
        assert "node-1 | gateway" in xlsx_res["content"]

        (tmp_path / "data.json").write_text(
            json.dumps([{"svc": "auth", "tier": "core"}, {"svc": "ui", "tier": "edge"}]),
            encoding="utf-8",
        )
        q_res = await server.design_suite_forge(
            action="data_sandbox_query",
            input_path="data.json",
            params={"filter_col": "tier", "filter_contains": "core"},
        )
        assert q_res["total_matching"] == 1
        assert q_res["rows"][0]["svc"] == "auth"

    async def test_code_mode_pipeline_piping_and_compaction(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(server.settings, "sandbox_root", str(tmp_path))
        monkeypatch.setattr(server, "memory_store", ForgeVectorMemory(tmp_path / "p.db"))

        im = Image.new("RGB", (24, 24), color=(255, 255, 255))
        for x in range(6, 18):
            for y in range(6, 18):
                im.putpixel((x, y), (30, 144, 255))
        im.save(tmp_path / "icon.png")

        disc = await server.design_suite_forge(mode="discover")
        assert disc["code_mode"] is True
        assert "doc_extract" in disc["actions"]

        pipe = await server.design_suite_forge(
            mode="pipeline",
            steps=[
                {
                    "id": "nobg",
                    "action": "remove_background",
                    "params": {"input_path": "icon.png", "output_path": "out/icon_nobg.png"},
                },
                {
                    "id": "vec",
                    "action": "raster_to_svg",
                    "params": {
                        "input_path": "$steps.nobg.output_path",
                        "output_path": "out/icon.svg",
                    },
                },
            ],
            verbosity="minimal",
        )
        assert pipe["status"] == "OK"
        assert pipe["steps_run"] == 2
        assert pipe["output_path"] == "out/icon.svg"
        assert "steps" not in pipe
        assert (tmp_path / "out" / "icon.svg").exists()

        wcag = await server.design_suite_forge(
            action="wcag_contrast",
            params={"fg_hex": "#FFFFFF", "bg_hex": "#0F172A"},
            select_fields=["ratio", "aa_normal"],
        )
        assert wcag["status"] == "OK"
        assert wcag["aa_normal"] is True
        assert "fg" not in wcag


class TestMediaCodeMode:
    async def test_media_discover_and_pipeline_with_mock_exec(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(server.settings, "sandbox_root", str(tmp_path))
        monkeypatch.setattr(server, "memory_store", ForgeVectorMemory(tmp_path / "med.db"))

        (tmp_path / "clip.mp4").write_bytes(b"fake-mp4")

        async def _fake_exec(cmd: list[str]) -> tuple[int, str, str]:
            out_file = Path(cmd[-1])
            if out_file.suffix in {".png", ".webp", ".mp4"}:
                out_file.parent.mkdir(parents=True, exist_ok=True)
                out_file.write_bytes(b"processed")
            return 0, json.dumps({"streams": [{"codec_type": "video", "width": 640, "height": 360}]}), ""

        monkeypatch.setattr(media_engine, "_run_exec", _fake_exec)

        disc = await server.media_forge_ffmpeg(mode="discover")
        assert disc["code_mode"] is True
        assert "extract_frame" in disc["actions"]

        pipe = await server.media_forge_ffmpeg(
            mode="pipeline",
            steps=[
                {
                    "id": "frame",
                    "action": "extract_frame",
                    "params": {"input_path": "clip.mp4", "output_path": "out/frame.png"},
                },
                {
                    "id": "webp",
                    "action": "convert",
                    "params": {
                        "input_path": "$steps.frame.output_path",
                        "output_path": "out/frame.webp",
                        "format": "webp",
                    },
                },
            ],
        )
        assert pipe["status"] == "OK"
        assert pipe["steps_run"] == 2
        assert pipe["output_path"] == "out/frame.webp"
        assert (tmp_path / "out" / "frame.webp").exists()
