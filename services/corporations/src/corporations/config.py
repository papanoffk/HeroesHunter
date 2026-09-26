from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "admin"
    db_password: SecretStr = SecretStr("password")
    db_name: str = "hh-db"
    db_schema: str = Field(default="corporations", pattern=r"^[a-z_][a-z0-9_]*$")
    db_pool_min_size: int = 1
    db_pool_max_size: int = 10

    max_image_size_bytes: int = Field(default=5 * 1024 * 1024, gt=0)

    def dsn(self, scheme: str = "postgresql") -> str:
        return (
            f"{scheme}://{self.db_user}:{self.db_password.get_secret_value()}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
