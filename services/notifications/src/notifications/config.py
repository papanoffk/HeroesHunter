from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    rabbitmq_url: SecretStr = SecretStr("amqp://admin:password@localhost:5672/")
    events_exchange: str = "heroes_hunter.events"
    events_routing_keys: list[str] = ["mission.responded", "resume.invited"]
    events_prefetch_count: int = Field(default=100, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()
