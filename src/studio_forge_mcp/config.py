"""Environment configuration for studio-forge-mcp."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FORGE_", env_file=".env", extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8895
    sandbox_root: str = "/tmp/studio-forge-sandbox"
    memory_db: str = "/tmp/studio-forge-sandbox/forge_memory.db"


settings = Settings()
