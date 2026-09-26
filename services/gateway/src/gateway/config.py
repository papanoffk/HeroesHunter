from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    auth_url: str = "http://localhost:8000"
    heroes_url: str = "http://localhost:8001"
    corporations_url: str = "http://localhost:8002"
    missions_url: str = "http://localhost:8003"
    resumes_url: str = "http://localhost:8004"
    notifications_url: str = "http://localhost:8005"

    upstream_timeout_seconds: float = Field(default=30.0, gt=0)
    max_body_size_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    cors_origins: list[str] = []


@lru_cache
def get_settings() -> Settings:
    return Settings()
