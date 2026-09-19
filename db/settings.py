"""Process configuration, read from the environment and .env."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="SPEEDMAP_", extra="ignore")

    dsn: str = "postgresql:///speedmap"
    user_agent: str = "speedmap.gr/0.1 (+https://speedmap.gr/about)"

    # Outbound politeness, applied per upstream host.
    register_concurrency: int = 3
    register_delay_s: float = 0.35


settings = Settings()
