"""CLISettings — pydantic-settings BaseSettings for the dgs CLI.

This is the configuration layer for the CLI adapter. It loads the same
environment variables as the API Settings, but EXCLUDES API-specific fields
(API_HOST, API_PORT, LOG_LEVEL) that are irrelevant for a CLI process.

Usage::

    from depth_graph_search.cli.config import CLISettings

    settings = CLISettings()  # reads from environment or .env file

CLI flags take precedence over env vars by constructing the settings with
explicit keyword arguments::

    settings = CLISettings(database_url=cli_dsn_value, **other_overrides)
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class CLISettings(BaseSettings):
    """Validated, environment-driven configuration for the dgs CLI.

    Reads from environment variables or a ``.env`` file (in that priority order).
    Raises ``ValidationError`` if any required var is missing or invalid.

    Compared to ``api/config.py Settings``, this class omits:
    - ``API_HOST`` — not relevant for CLI
    - ``API_PORT`` — not relevant for CLI
    - ``LOG_LEVEL`` — not relevant for CLI

    Required vars:
        DATABASE_URL: PostgreSQL DSN. Must start with ``postgresql://`` or
            ``postgresql+psycopg://``.

    Optional vars (all have documented defaults):
        OPENAI_API_KEY: OpenAI API key. Required when ``LLM_PROVIDER=openai``.
            When ``LLM_PROVIDER=openrouter``, this is optional — if set, OpenAI
            handles embeddings (mixed mode); if absent, OpenRouter handles both
            LLM and embeddings (OpenRouter-only mode).
        OPENROUTER_API_KEY: Required only when ``LLM_PROVIDER=openrouter``.
        LLM_PROVIDER: Which LLM backend to use. One of ``openai``, ``openrouter``.
        LLM_MODEL: Chat completion model identifier.
        EMBEDDING_MODEL: Embedding model identifier.
        GRAPH_NAME: Apache AGE graph name.
        EMBEDDING_DIMENSIONS: Vector dimension for pgvector.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # ------------------------------------------------------------------
    # Required
    # ------------------------------------------------------------------

    database_url: str

    # ------------------------------------------------------------------
    # Optional with defaults
    # ------------------------------------------------------------------

    openai_api_key: str = ""
    openrouter_api_key: str | None = None
    llm_provider: Literal["openai", "openrouter"] = "openai"
    llm_model: str = "gpt-4o"
    embedding_model: str = "text-embedding-3-large"
    graph_name: str = "knowledge_graph"
    embedding_dimensions: int = 3072

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("database_url")
    @classmethod
    def validate_dsn(cls, v: str) -> str:
        """Ensure DATABASE_URL is a PostgreSQL DSN."""
        if not v.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError(
                "DATABASE_URL must start with postgresql:// or postgresql+psycopg://"
            )
        return v

    @model_validator(mode="after")
    def validate_api_keys(self) -> Self:
        """Enforce provider-specific key requirements.

        Rules:
        - ``LLM_PROVIDER=openrouter`` requires ``OPENROUTER_API_KEY``.
        - ``LLM_PROVIDER=openai`` requires ``OPENAI_API_KEY``.
        - ``LLM_PROVIDER=openrouter`` without ``OPENAI_API_KEY`` is valid
          (OpenRouter-only mode: single provider for both LLM and embeddings).
        """
        if self.llm_provider == "openrouter" and not self.openrouter_api_key:
            raise ValueError(
                "OPENROUTER_API_KEY required when LLM_PROVIDER=openrouter"
            )
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY required when LLM_PROVIDER=openai"
            )
        return self
