from functools import lru_cache
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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
    def _normalise_provider_url(cls, v: object) -> object:
        """Make a managed provider's connection string usable as-is.

        Two things go wrong when you paste a provider's URL straight in, and
        both fail at connect time rather than at startup:

        1. Render, Neon, Supabase, Railway and Heroku hand out `postgres://…`
           or `postgresql://…`. Both are valid DSNs and both are rejected by
           `create_async_engine`, which needs an explicit async driver.
        2. Supabase's *pooled* URL carries `?supa=base-pooler.x`. libpq has no
           such connection option and psycopg refuses the whole connection with
           `invalid connection option "supa"`. Its session URL has no such
           marker, so migrations succeed and only the pooled app breaks —
           which makes it look like an application bug.

        Anything already correct passes through untouched.
        """
        if not isinstance(v, str):
            return v

        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                v = "postgresql+psycopg://" + v[len(prefix) :]
                break

        # Drop vendor markers libpq does not understand, keeping real options
        # such as sslmode.
        if "supa=" in v:
            parsed = urlsplit(v)
            kept = [(k, val) for k, val in parse_qsl(parsed.query) if k != "supa"]
            v = urlunsplit(parsed._replace(query=urlencode(kept)))

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
