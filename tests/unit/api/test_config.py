"""Unit tests for api/config.py — Settings validation.

Tests cover all spec scenarios:
  - Valid required vars → instance created, defaults correct
  - Missing DATABASE_URL → ValidationError
  - Missing OPENAI_API_KEY → ValidationError
  - Invalid DSN scheme → ValidationError with PostgreSQL message
  - Valid postgresql+psycopg:// DSN → accepted
  - Invalid LLM_PROVIDER → ValidationError
  - Missing OPENROUTER_API_KEY when provider=openrouter → ValidationError
  - Valid openrouter config (key present) → instance created

No real DB connections are made; all tests use monkeypatch to set env vars.
pydantic-settings reads env vars from the process environment, so any
real .env file is bypassed by constructing Settings with explicit values.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from depth_graph_search.api.config import Settings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED = {
    "DATABASE_URL": "postgresql://depth:depth@localhost:5432/depth_graph",
    "OPENAI_API_KEY": "sk-test-key",
}


def _make_settings(**overrides: str) -> Settings:
    """Construct Settings with required vars + optional overrides.

    Passes values via model_validate to avoid reading real .env or env vars.
    """
    data = {**_REQUIRED, **overrides}
    # Use model_validate to bypass env-reading for pure unit tests.
    # Field names are lower-cased as per the Settings class definition.
    normalised = {k.lower(): v for k, v in data.items()}
    return Settings.model_validate(normalised)


# ---------------------------------------------------------------------------
# Scenario: Valid required vars present
# ---------------------------------------------------------------------------


class TestValidConfig:
    def test_valid_required_vars_creates_instance(self) -> None:
        """Given both required vars, Settings instantiates without error."""
        settings = _make_settings()
        assert settings.database_url == "postgresql://depth:depth@localhost:5432/depth_graph"
        assert settings.openai_api_key == "sk-test-key"

    def test_default_llm_provider_is_openai(self) -> None:
        settings = _make_settings()
        assert settings.llm_provider == "openai"

    def test_default_llm_model(self) -> None:
        settings = _make_settings()
        assert settings.llm_model == "gpt-4o"

    def test_default_embedding_model(self) -> None:
        settings = _make_settings()
        assert settings.embedding_model == "text-embedding-3-large"

    def test_default_graph_name(self) -> None:
        settings = _make_settings()
        assert settings.graph_name == "knowledge_graph"

    def test_default_embedding_dimensions(self) -> None:
        settings = _make_settings()
        assert settings.embedding_dimensions == 3072

    def test_default_api_host(self) -> None:
        settings = _make_settings()
        assert settings.api_host == "0.0.0.0"

    def test_default_api_port(self) -> None:
        settings = _make_settings()
        assert settings.api_port == 8000

    def test_default_log_level(self) -> None:
        settings = _make_settings()
        assert settings.log_level == "info"

    def test_default_openrouter_api_key_is_none(self) -> None:
        settings = _make_settings()
        assert settings.openrouter_api_key is None


# ---------------------------------------------------------------------------
# Scenario: Missing required var at startup
# ---------------------------------------------------------------------------


class TestMissingRequiredVars:
    def test_missing_database_url_raises(self) -> None:
        """Missing DATABASE_URL raises ValidationError identifying the field."""
        with pytest.raises(PydanticValidationError) as exc_info:
            Settings.model_validate({"openai_api_key": "sk-key"})
        error_text = str(exc_info.value)
        assert "database_url" in error_text.lower()

    def test_missing_openai_api_key_raises(self) -> None:
        """Missing OPENAI_API_KEY raises ValidationError."""
        with pytest.raises(PydanticValidationError) as exc_info:
            Settings.model_validate(
                {"database_url": "postgresql://depth:depth@localhost:5432/depth_graph"}
            )
        error_text = str(exc_info.value)
        assert "openai_api_key" in error_text.lower()


# ---------------------------------------------------------------------------
# Scenario: DATABASE_URL validation
# ---------------------------------------------------------------------------


class TestDatabaseUrlValidation:
    def test_invalid_dsn_scheme_raises(self) -> None:
        """mysql:// DSN raises ValidationError with PostgreSQL message."""
        with pytest.raises(PydanticValidationError) as exc_info:
            _make_settings(DATABASE_URL="mysql://user:pass@host/db")
        assert "postgresql" in str(exc_info.value).lower()

    def test_sqlite_scheme_raises(self) -> None:
        """sqlite:// DSN is also rejected."""
        with pytest.raises(PydanticValidationError):
            _make_settings(DATABASE_URL="sqlite:///local.db")

    def test_postgresql_scheme_accepted(self) -> None:
        """postgresql:// is a valid DSN scheme."""
        settings = _make_settings(DATABASE_URL="postgresql://depth:depth@localhost:5432/depth_graph")
        assert settings.database_url.startswith("postgresql://")

    def test_postgresql_psycopg_scheme_accepted(self) -> None:
        """postgresql+psycopg:// is also a valid DSN scheme."""
        settings = _make_settings(
            DATABASE_URL="postgresql+psycopg://depth:depth@localhost:5432/depth_graph"
        )
        assert settings.database_url.startswith("postgresql+psycopg://")


# ---------------------------------------------------------------------------
# Scenario: Invalid LLM_PROVIDER value
# ---------------------------------------------------------------------------


class TestLlmProviderValidation:
    def test_invalid_llm_provider_raises(self) -> None:
        """LLM_PROVIDER=gpt raises ValidationError indicating accepted values."""
        with pytest.raises(PydanticValidationError) as exc_info:
            _make_settings(LLM_PROVIDER="gpt")
        error_text = str(exc_info.value)
        # pydantic Literal error mentions the accepted values
        assert "openai" in error_text or "openrouter" in error_text

    def test_openai_provider_accepted(self) -> None:
        settings = _make_settings(LLM_PROVIDER="openai")
        assert settings.llm_provider == "openai"

    def test_openrouter_provider_accepted_with_key(self) -> None:
        settings = _make_settings(
            LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="or-test-key"
        )
        assert settings.llm_provider == "openrouter"


# ---------------------------------------------------------------------------
# Scenario: OpenRouter API key conditional requirement
# ---------------------------------------------------------------------------


class TestOpenrouterKeyConditional:
    def test_openrouter_without_key_raises(self) -> None:
        """LLM_PROVIDER=openrouter without OPENROUTER_API_KEY raises ValidationError."""
        with pytest.raises(PydanticValidationError) as exc_info:
            _make_settings(LLM_PROVIDER="openrouter")
        assert "openrouter" in str(exc_info.value).lower()

    def test_openrouter_with_key_succeeds(self) -> None:
        """LLM_PROVIDER=openrouter with OPENROUTER_API_KEY creates instance."""
        settings = _make_settings(
            LLM_PROVIDER="openrouter", OPENROUTER_API_KEY="or-test-key"
        )
        assert settings.openrouter_api_key == "or-test-key"

    def test_openai_provider_does_not_require_openrouter_key(self) -> None:
        """Default LLM_PROVIDER=openai does not require OPENROUTER_API_KEY."""
        settings = _make_settings()  # no OPENROUTER_API_KEY
        assert settings.llm_provider == "openai"
        assert settings.openrouter_api_key is None
