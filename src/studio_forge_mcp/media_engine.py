"""Sandboxed FFmpeg & Media Manipulation engine for studio-forge-mcp."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from studio_forge_mcp.config import settings
from studio_forge_mcp.sandbox import safe_sandbox_path

ALLOWED_IMAGE_FORMATS = frozenset({"png", "jpg", "jpeg", "webp", "avif", "gif", "bmp"})
ALLOWED_MEDIA_FORMATS = ALLOWED_IMAGE_FORMATS | frozenset({"mp4", "webm", "mov", "mp3", "wav", "ogg", "m4a"})


async def _run_exec(cmd: list[str]) -> tuple[int, str, str]:
    """Execute ffmpeg/ffprobe without shell interpolation."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(
            proc.communicate(), timeout=settings.timeout_sec
        )
    except TimeoutError:
        proc.kill()
        await proc.communicate()
        raise RuntimeError(f"FFmpeg timeout after {settings.timeout_sec}s")
    return (
        proc.returncode or 0,
        stdout_b.decode("utf-8", errors="replace"),
        stderr_b.decode("utf-8", errors="replace"),
    )


def _sandbox_rel(path: Path) -> str:
    root = Path(settings.sandbox_root).resolve()
    return str(path.relative_to(root))


def _resolve_output(output_path: str | None, default_rel: str) -> Path:
    target = output_path if output_path else default_rel
    dst = safe_sandbox_path(target)
    dst.parent.mkdir(parents=True, exist_ok=True)
    return dst


async def probe_media(input_path: str) -> dict[str, Any]:
    """Inspect image/video/audio dimensions, format, and streams via ffprobe."""
    src = safe_sandbox_path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"File not found in sandbox: {input_path}")
    code, out, err = await _run_exec(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(src),
        ]
    )
    if code != 0:
        raise RuntimeError(f"ffprobe error ({code}): {err[:300]}")
    data = json.loads(out or "{}")
    streams: list[dict[str, Any]] = data.get("streams") or []
    vstream: dict[str, Any] = next((s for s in streams if s.get("codec_type") == "video"), {})
    fmt = data.get("format") or {}
    return {
        "status": "OK",
        "path": _sandbox_rel(src),
        "width": vstream.get("width"),
        "height": vstream.get("height"),
        "codec": vstream.get("codec_name"),
        "format": fmt.get("format_name"),
        "duration_sec": fmt.get("duration"),
        "size_bytes": src.stat().st_size,
    }


async def resize_media(
    input_path: str,
    output_path: str | None = None,
    width: int = 1024,
    height: int = -1,
) -> dict[str, Any]:
    """Resize an image or video inside the sandbox."""
    src = safe_sandbox_path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"File not found in sandbox: {input_path}")
    dst = _resolve_output(output_path, f"outputs/resized_{src.name}")
    w = max(1, min(int(width), 16384))
    h = -1 if int(height) <= 0 else max(1, min(int(height), 16384))
    code, _, err = await _run_exec(
        ["ffmpeg", "-y", "-i", str(src), "-vf", f"scale={w}:{h}", str(dst)]
    )
    if code != 0:
        raise RuntimeError(f"ffmpeg resize error ({code}): {err[:300]}")
    return {
        "status": "OK",
        "output_path": _sandbox_rel(dst),
        "size_bytes": dst.stat().st_size,
        "width": w,
        "height": h,
    }


async def crop_media(
    input_path: str,
    output_path: str | None = None,
    x: int = 0,
    y: int = 0,
    width: int = 512,
    height: int = 512,
) -> dict[str, Any]:
    """Crop an image or video region (w:h:x:y) inside the sandbox."""
    src = safe_sandbox_path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"File not found in sandbox: {input_path}")
    dst = _resolve_output(output_path, f"outputs/cropped_{src.name}")
    w = max(1, min(int(width), 16384))
    h = max(1, min(int(height), 16384))
    cx = max(0, int(x))
    cy = max(0, int(y))
    code, _, err = await _run_exec(
        ["ffmpeg", "-y", "-i", str(src), "-vf", f"crop={w}:{h}:{cx}:{cy}", str(dst)]
    )
    if code != 0:
        raise RuntimeError(f"ffmpeg crop error ({code}): {err[:300]}")
    return {
        "status": "OK",
        "output_path": _sandbox_rel(dst),
        "size_bytes": dst.stat().st_size,
    }


async def convert_media(
    input_path: str,
    output_path: str | None = None,
    target_format: str = "webp",
    quality: int = 85,
) -> dict[str, Any]:
    """Convert an image/audio/video asset inside the sandbox."""
    fmt = target_format.strip().lower().lstrip(".")
    if fmt not in ALLOWED_MEDIA_FORMATS:
        raise ValueError(f"Unsupported media format: {target_format}")
    src = safe_sandbox_path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"File not found in sandbox: {input_path}")
    dst = _resolve_output(output_path, f"outputs/{src.stem}.{fmt}")
    q = max(1, min(int(quality), 100))
    cmd = ["ffmpeg", "-y", "-i", str(src)]
    if fmt in {"webp", "avif"}:
        cmd.extend(["-quality", str(q)])
    elif fmt in {"jpg", "jpeg"}:
        qscale = max(1, min(31, round((100 - q) * 30 / 100) + 1))
        cmd.extend(["-q:v", str(qscale)])
    cmd.append(str(dst))
    code, _, err = await _run_exec(cmd)
    if code != 0:
        raise RuntimeError(f"ffmpeg convert error ({code}): {err[:300]}")
    return {
        "status": "OK",
        "output_path": _sandbox_rel(dst),
        "format": fmt,
        "size_bytes": dst.stat().st_size,
    }


async def extract_video_frame(
    input_path: str,
    output_path: str | None = None,
    timestamp: str = "00:00:01",
) -> dict[str, Any]:
    """Extract a single PNG frame from a video/GIF."""
    src = safe_sandbox_path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"File not found in sandbox: {input_path}")
    dst = _resolve_output(output_path, f"outputs/{src.stem}_frame.png")
    code, _, err = await _run_exec(
        ["ffmpeg", "-y", "-ss", timestamp, "-i", str(src), "-frames:v", "1", str(dst)]
    )
    if code != 0:
        raise RuntimeError(f"ffmpeg extract_frame error ({code}): {err[:300]}")
    return {
        "status": "OK",
        "output_path": _sandbox_rel(dst),
        "size_bytes": dst.stat().st_size,
    }


async def extract_audio(
    input_path: str,
    output_path: str | None = None,
    audio_format: str = "wav",
) -> dict[str, Any]:
    """Extract audio track from a media file inside the sandbox."""
    fmt = audio_format.strip().lower().lstrip(".")
    if fmt not in {"wav", "mp3", "ogg", "m4a"}:
        raise ValueError(f"Unsupported audio format: {audio_format}")
    src = safe_sandbox_path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"File not found in sandbox: {input_path}")
    dst = _resolve_output(output_path, f"outputs/{src.stem}.{fmt}")
    code, _, err = await _run_exec(["ffmpeg", "-y", "-i", str(src), "-vn", str(dst)])
    if code != 0:
        raise RuntimeError(f"ffmpeg extract_audio error ({code}): {err[:300]}")
    return {
        "status": "OK",
        "output_path": _sandbox_rel(dst),
        "format": fmt,
        "size_bytes": dst.stat().st_size,
    }


async def render_waveform(
    input_path: str,
    output_path: str | None = None,
    width: int = 1200,
    height: int = 240,
) -> dict[str, Any]:
    """Render a PNG audio waveform preview inside the sandbox."""
    src = safe_sandbox_path(input_path)
    if not src.exists():
        raise FileNotFoundError(f"File not found in sandbox: {input_path}")
    dst = _resolve_output(output_path, f"outputs/{src.stem}_waveform.png")
    w = max(128, min(int(width), 4096))
    h = max(64, min(int(height), 1024))
    code, _, err = await _run_exec(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-filter_complex",
            f"showwavespic=s={w}x{h}",
            "-frames:v",
            "1",
            str(dst),
        ]
    )
    if code != 0:
        raise RuntimeError(f"ffmpeg waveform error ({code}): {err[:300]}")
    return {
        "status": "OK",
        "output_path": _sandbox_rel(dst),
        "size_bytes": dst.stat().st_size,
    }


async def dispatch_media_action(action: str, params: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a single FFmpeg action inside the sandbox."""
    act = (action or "").strip().lower()
    in_path = str(params.get("input_path") or "")
    out_path = params.get("output_path")
    if act == "probe":
        return await probe_media(input_path=in_path)
    if act == "resize":
        return await resize_media(
            input_path=in_path,
            output_path=str(out_path) if out_path else None,
            width=int(params.get("width") or 1024),
            height=int(params.get("height") or -1),
        )
    if act == "crop":
        return await crop_media(
            input_path=in_path,
            output_path=str(out_path) if out_path else None,
            x=int(params.get("x") or 0),
            y=int(params.get("y") or 0),
            width=int(params.get("width") or 512),
            height=int(params.get("height") or 512),
        )
    if act == "convert":
        return await convert_media(
            input_path=in_path,
            output_path=str(out_path) if out_path else None,
            target_format=str(params.get("format") or "webp"),
            quality=int(params.get("quality") or 85),
        )
    if act == "extract_frame":
        return await extract_video_frame(
            input_path=in_path,
            output_path=str(out_path) if out_path else None,
            timestamp=str(params.get("timestamp") or "00:00:01"),
        )
    if act == "extract_audio":
        return await extract_audio(
            input_path=in_path,
            output_path=str(out_path) if out_path else None,
            audio_format=str(params.get("format") or "wav"),
        )
    if act == "waveform":
        return await render_waveform(
            input_path=in_path,
            output_path=str(out_path) if out_path else None,
            width=int(params.get("width") or 1200),
            height=int(params.get("height") or 240),
        )
    raise ValueError(f"Unsupported FFmpeg action: {action}")
