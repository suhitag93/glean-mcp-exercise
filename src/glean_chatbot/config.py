"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@lru_cache(maxsize=1)
def get_config() -> "Config":
    return Config()


class Config:
    def __init__(self) -> None:
        self.instance: str = self._require("GLEAN_INSTANCE")
        self.indexing_token: str = self._require("GLEAN_INDEXING_TOKEN")
        self.user_token: str = self._require("GLEAN_USER_TOKEN")
        self.datasource: str = os.getenv("GLEAN_DATASOURCE", "glean-mcp-exercise")
        self.act_as_email: str | None = os.getenv("GLEAN_ACT_AS")
        self._base_url: str | None = os.getenv("GLEAN_BASE_URL")

    @property
    def base_url(self) -> str:
        if self._base_url:
            return self._base_url.rstrip("/")
        return f"https://{self.instance}-be.glean.com"

    @staticmethod
    def _require(key: str) -> str:
        value = os.getenv(key)
        if not value:
            raise EnvironmentError(
                f"Required environment variable '{key}' is not set. "
                "Copy .env.example to .env and fill in your values."
            )
        return value
