"""Pydantic-settings-based configuration.

Reads from ``.env`` and environment variables.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Required for hash / surrogate strategies.
    phi_hash_key: str | None = None

    # Optional LLM pass.
    llm_model: str = "anthropic/claude-haiku-4-5"
    phi_use_llm: bool = False

    # Phone regions and NER threshold defaults.
    phi_regions: str = "NZ,AU"
    phi_ner_threshold: float = Field(default=0.40, ge=0.0, le=1.0)

    @property
    def regions_list(self) -> list[str]:
        return [r.strip().upper() for r in self.phi_regions.split(",") if r.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
