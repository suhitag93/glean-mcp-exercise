"""Configuration loaded from environment variables."""

from __future__ import annotations

import os
from functools import lru_cache

from dotenv import find_dotenv, dotenv_values

# Walk up from this file's directory to find and load .env.
# find_dotenv() is more reliable than load_dotenv() with no args because it
# uses the caller's __file__ location rather than cwd, which can differ in
# Streamlit and subprocess contexts.
_dotenv_path = find_dotenv(raise_error_if_not_found=False, usecwd=False)
for _k, _v in dotenv_values(_dotenv_path).items():
    if _v is not None:
        os.environ.setdefault(_k, _v)


@lru_cache(maxsize=1)
def get_config() -> "Config":
    return Config()


class Config:
    def __init__(self) -> None:
        self.instance: str = self._require("GLEAN_INSTANCE")
        self.indexing_token: str = self._require("GLEAN_INDEXING_TOKEN")
        self.user_token: str = self._require("GLEAN_USER_TOKEN")
        # Chat token falls back to user_token if not explicitly set
        self.chat_token: str = os.getenv("GLEAN_CHAT_TOKEN") or self.user_token
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
