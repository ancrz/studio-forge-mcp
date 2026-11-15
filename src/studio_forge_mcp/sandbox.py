"""Sandbox path resolution and security guards for studio-forge-mcp."""

from __future__ import annotations

from pathlib import Path

from studio_forge_mcp.config import settings


def safe_sandbox_path(rel_path: str) -> Path:
    """Resolve a path strictly inside FORGE_SANDBOX_ROOT, blocking traversal and symlinks."""
    cleaned = (rel_path or "").strip().lstrip("/")
    if not cleaned or "\\" in cleaned:
        raise ValueError(f"Invalid sandbox path: {rel_path!r}")
    root = Path(settings.sandbox_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    candidate = (root / cleaned).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"Path escapes sandbox root: {rel_path!r}")
    return candidate
