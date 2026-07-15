from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, sourced from the environment.

    Nothing here has a usable production default: the app refuses to boot
    without an explicitly provided database URL and JWT secret.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="AIRPORT_",
        extra="ignore",
    )

    environment: Literal["local", "test", "staging", "production"] = "local"
    debug: bool = False

    database_url: PostgresDsn
    db_pool_size: int = Field(default=10, ge=1, le=100)
    db_max_overflow: int = Field(default=5, ge=0, le=100)
    db_echo: bool = False
    # Serverless platforms (Vercel, Lambda) freeze the process between requests,
    # so a connection pool held in memory is worse than useless: the far end has
    # long since dropped the sockets. Pool through the provider instead and open
    # a fresh connection per invocation. See docs/DEPLOY.md.
    db_serverless: bool = False

    jwt_secret: str = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = Field(default=30, ge=1, le=1440)
    refresh_token_ttl_days: int = Field(default=7, ge=1, le=90)

    cors_origins: list[str] = Field(default_factory=list)

    @field_validator("database_url", mode="before")
    @classmethod
    def _require_async_driver(cls, v: object) -> object:
        """Normalise a managed provider's URL to the async driver.

        Render, Neon, Supabase, Railway and Heroku all hand out
        `postgres://…` or `postgresql://…`. Both are valid DSNs, and both fail
        at connect time under `create_async_engine`, which needs an explicit
        async driver. Rewriting here turns a confusing runtime error into a
        deploy that simply works.
        """
        if isinstance(v, str):
            for prefix in ("postgres://", "postgresql://"):
                if v.startswith(prefix):
                    return "postgresql+psycopg://" + v[len(prefix) :]
        return v

    @field_validator("jwt_secret")
    @classmethod
    def _reject_placeholder_secret(cls, v: str) -> str:
        if v.lower() in {"changeme", "secret", "please-change-me", "your-secret-here"}:
            raise ValueError("AIRPORT_JWT_SECRET is a placeholder value; set a real secret")
        return v

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
