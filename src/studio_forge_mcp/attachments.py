"""Safe attachment & archive parser for studio-forge-mcp.

Parses uploaded files (`.zip`, `.penpot`, `.svg`, `.json`, `.md`, `.txt`, `.csv`,
`.yaml`, `.pdf`, `.docx`, `.xlsx`, and reference images) into compact
token-budgeted context blocks with Zip-slip and Zip-bomb protections.
"""

from __future__ import annotations

import base64
import io
import os
import uuid
import zipfile
from typing import Any

MAX_UPLOAD_BYTES = 16 * 1024 * 1024  # 16 MB
MAX_ZIP_ENTRIES = 250
MAX_ZIP_UNCOMPRESSED_BYTES = 24 * 1024 * 1024  # 24 MB
MAX_CONTEXT_CHARS = 8000

_IMAGE_EXTS = frozenset({".png", ".jpg", ".jpeg", ".webp"})
_TEXT_EXTS = frozenset({".svg", ".json", ".md", ".txt", ".css", ".html", ".csv", ".yaml", ".yml"})
_OFFICE_EXTS = frozenset({".pdf", ".docx", ".xlsx"})


def safe_zip_member_name(name: str) -> bool:
    """Reject absolute paths, backslashes, or '..' traversal inside ZIP archives."""
    if not name or name.startswith("/") or "\\" in name:
        return False
    return ".." not in name.split("/")


def parse_zip_archive(filename: str, raw: bytes) -> dict[str, Any]:
    """Validate and summarize a ZIP/.penpot archive with Zip-slip and Zip-bomb guards."""
    buf = io.BytesIO(raw)
    if not zipfile.is_zipfile(buf):
        raise ValueError(f"{filename} is not a valid ZIP archive.")

    buf.seek(0)
    entries: list[str] = []
    total_uncompressed = 0

    with zipfile.ZipFile(buf, "r") as zf:
        infos = zf.infolist()
        if len(infos) > MAX_ZIP_ENTRIES:
            raise ValueError(f"{filename} exceeds max {MAX_ZIP_ENTRIES} ZIP entries.")

        for info in infos:
            if not safe_zip_member_name(info.filename):
                raise ValueError(f"Unsafe ZIP member path blocked: {info.filename!r}")
            total_uncompressed += info.file_size
            if total_uncompressed > MAX_ZIP_UNCOMPRESSED_BYTES:
                raise ValueError(f"{filename} exceeds 24 MB uncompressed limit.")
            entries.append(info.filename)

    summary_lines = [
        f"ZIP archive: {filename} ({len(raw)} bytes, {len(entries)} entries, {total_uncompressed} bytes uncompressed)",
        f"- Entries (sample): {', '.join(entries[:15]) or 'empty'}",
    ]
    return {
        "kind": "zip_archive",
        "summary": f"ZIP archive ({len(entries)} entries, {total_uncompressed} bytes)",
        "context_text": "\n".join(summary_lines)[:MAX_CONTEXT_CHARS],
        "meta": {
            "entry_count": len(entries),
            "total_uncompressed_bytes": total_uncompressed,
            "entries": entries[:30],
        },
    }


def parse_uploaded_attachment(
    *,
    filename: str,
    content_bytes: bytes,
    content_type: str = "",
) -> dict[str, Any]:
    """Validate and parse an uploaded file into a compact context attachment."""
    clean_name = os.path.basename(filename or "attachment").strip() or "attachment"
    if len(content_bytes) > MAX_UPLOAD_BYTES:
        raise ValueError(f"{clean_name} exceeds maximum allowed size of 16 MB.")

    ext = os.path.splitext(clean_name)[1].lower()
    att_id = f"att_{uuid.uuid4().hex[:12]}"

    if ext in {".zip", ".penpot"}:
        parsed = parse_zip_archive(clean_name, content_bytes)
        return {
            "id": att_id,
            "filename": clean_name,
            "size_bytes": len(content_bytes),
            "content_type": content_type or "application/zip",
            **parsed,
        }

    if ext in _IMAGE_EXTS:
        mime = content_type or f"image/{ext.lstrip('.').replace('jpg', 'jpeg')}"
        b64_preview = (
            base64.b64encode(content_bytes).decode("ascii")
            if len(content_bytes) <= 2_000_000
            else ""
        )
        return {
            "id": att_id,
            "filename": clean_name,
            "size_bytes": len(content_bytes),
            "content_type": mime,
            "kind": "image",
            "summary": f"Image {clean_name} ({round(len(content_bytes) / 1024, 1)} KB)",
            "context_text": f"Attached image: {clean_name} ({mime}, {len(content_bytes)} bytes).",
            "image_base64": b64_preview,
        }

    if ext in _TEXT_EXTS or (content_type and content_type.startswith("text/")):
        text = content_bytes.decode("utf-8", errors="replace")
        truncated = len(text) > MAX_CONTEXT_CHARS
        snippet = text[:MAX_CONTEXT_CHARS]
        kind = "svg" if ext == ".svg" else ("json" if ext == ".json" else "text")
        return {
            "id": att_id,
            "filename": clean_name,
            "size_bytes": len(content_bytes),
            "content_type": content_type or "text/plain",
            "kind": kind,
            "summary": f"{kind.upper()} file {clean_name} ({round(len(content_bytes) / 1024, 1)} KB)",
            "context_text": f"--- {clean_name} ({kind}) ---\n{snippet}"
            + ("\n...[truncated]" if truncated else ""),
        }

    if ext in _OFFICE_EXTS:
        fmt_label = ext.lstrip(".").upper()
        return {
            "id": att_id,
            "filename": clean_name,
            "size_bytes": len(content_bytes),
            "content_type": content_type or "application/octet-stream",
            "kind": ext.lstrip("."),
            "summary": f"{fmt_label} document {clean_name} ({round(len(content_bytes) / 1024, 1)} KB)",
            "context_text": (
                f"Attached {fmt_label} document: {clean_name} ({len(content_bytes)} bytes). "
                "Use `design_suite_forge` (`doc_extract` or `pdf_render_pages`) to extract text/tables or render pages."
            ),
        }

    raise ValueError(
        f"Unsupported format ({ext or 'no extension'}). "
        "Supported: .zip, .penpot, .svg, .json, .md, .txt, .csv, .yaml, .pdf, .docx, .xlsx, or image."
    )
