"""Environment configuration for studio-forge-mcp."""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FORGE_", env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8895
    transport: Literal["streamable-http", "stdio"] = "streamable-http"
    timeout_sec: float = 30.0
    sandbox_root: str = "/tmp/studio-forge-sandbox"
    memory_db: str = "/tmp/studio-forge-sandbox/forge_memory.db"


settings = Settings()
