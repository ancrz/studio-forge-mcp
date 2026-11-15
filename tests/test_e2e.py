"""End-to-end MCP protocol tests over stdio and Streamable HTTP."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import httpx
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER = PROJECT_ROOT / "scripts" / "forge-mcp-launch.sh"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@contextmanager
def _running_http_server(tmp_path: Path) -> Iterator[str]:
    port = _free_port()
    env = {
        **os.environ,
        "FORGE_HOST": "127.0.0.1",
        "FORGE_PORT": str(port),
        "FORGE_TRANSPORT": "streamable-http",
        "FORGE_SANDBOX_ROOT": str(tmp_path / "sandbox"),
        "FORGE_MEMORY_DB": str(tmp_path / "sandbox" / "forge_memory.db"),
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "studio_forge_mcp.server"],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    base_url = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"Server exited early: {proc.stderr.read().decode() if proc.stderr else ''}")
            try:
                r = httpx.get(f"{base_url}/health", timeout=0.5)
                if r.status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:
            raise TimeoutError("Timed out waiting for /health")
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def _extract_json(res: Any) -> dict[str, Any]:
    assert not res.isError, f"Unexpected MCP tool error: {res.content}"
    text = res.content[0].text
    return dict(json.loads(text))


async def test_e2e_stdio_launcher_roundtrip(tmp_path: Path) -> None:
    sandbox = tmp_path / "stdio_sb"
    (sandbox / "docs").mkdir(parents=True, exist_ok=True)
    (sandbox / "docs" / "notes.csv").write_text(
        "service,status\napi,healthy\nworker,degraded\n", encoding="utf-8"
    )
    server_params = StdioServerParameters(
        command=str(LAUNCHER),
        env={
            **os.environ,
            "FORGE_SANDBOX_ROOT": str(sandbox),
            "FORGE_MEMORY_DB": str(sandbox / "forge_memory.db"),
        },
    )
    async with (
        stdio_client(server_params) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        tools = await session.list_tools()
        assert {t.name for t in tools.tools} == {
            "media_forge_ffmpeg",
            "design_suite_forge",
            "forge_memory_search",
        }

        res = await session.call_tool(
            "design_suite_forge",
            {
                "action": "data_sandbox_query",
                "input_path": "docs/notes.csv",
                "params": {"filter_col": "status", "filter_contains": "degraded"},
            },
        )
        payload = _extract_json(res)
        assert payload["status"] == "OK"
        assert payload["total_matching"] == 1
        assert payload["rows"][0]["service"] == "worker"

        bad = await session.call_tool(
            "media_forge_ffmpeg",
            {"action": "probe", "input_path": "../../etc/passwd"},
        )
        assert bad.isError

        mem = await session.call_tool("forge_memory_search", {"query": "docs/notes.csv", "limit": 3})
        mem_payload = _extract_json(mem)
        assert mem_payload["status"] == "ok"
        assert any(h["ref_id"] == "docs/notes.csv" for h in mem_payload["hits"])


async def test_e2e_streamable_http_and_health(tmp_path: Path) -> None:
    (tmp_path / "sandbox" / "assets").mkdir(parents=True, exist_ok=True)
    (tmp_path / "sandbox" / "assets" / "icon.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><g/><circle cx="5" cy="5" r="4"/></svg>',
        encoding="utf-8",
    )
    with _running_http_server(tmp_path) as base_url:
        async with httpx.AsyncClient() as client:
            health = await client.get(f"{base_url}/health", timeout=2.0)
        assert health.status_code == 200
        h_json = health.json()
        assert h_json["status"] == "ok"
        assert h_json["code_mode"] is True
        assert h_json["sqlite_vec"].startswith("v")

        async with (
            streamable_http_client(f"{base_url}/mcp") as (read, write, _get_sid),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
            res = await session.call_tool(
                "design_suite_forge",
                {
                    "action": "svg_optimize",
                    "input_path": "assets/icon.svg",
                    "output_path": "out/icon.min.svg",
                },
            )
            payload = _extract_json(res)
            assert payload["status"] == "OK"
            assert payload["output_path"] == "out/icon.min.svg"
            assert (tmp_path / "sandbox" / "out" / "icon.min.svg").exists()
