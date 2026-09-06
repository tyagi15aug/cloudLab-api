"""App settings, pulled from environment variables (see .env.example).

Don't add real secrets here. If you're pointing this at real AWS
(CLOUD_PROVIDER=aws), leave the access-key fields unset and let boto3's
own credential chain figure it out.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Which CloudProvider implementation to construct.
    cloud_provider: Literal["localstack", "aws"] = "localstack"

    aws_region: str = "us-east-1"
    aws_access_key_id: str | None = "test"
    aws_secret_access_key: str | None = "test"

    # Only meaningful for CLOUD_PROVIDER=localstack.
    aws_endpoint_url: str = "http://localhost:4566"

    api_port: int = 8000
    log_level: str = "INFO"

    # How many times to retry the initial LocalStack connectivity check on
    # startup before giving up, and how long to wait between attempts.
    startup_retry_attempts: int = 10
    startup_retry_delay_seconds: float = 2.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
