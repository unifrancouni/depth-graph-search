"""Unit tests for cli/config.py — CLISettings validation.

Tests cover all spec scenarios:
  - All values from env → instance created
  - Missing DATABASE_URL → ValidationError with field name
  - Missing OPENAI_API_KEY → ValidationError
  - Invalid DSN scheme → ValidationError
  - validate_openrouter_key fires when provider=openrouter but key is None
  - Valid openrouter config (key present) → instance created
  - CLISettings does NOT have API-specific fields (api_host, api_port, log_level)

No real DB connections. Uses model_validate to bypass env reading for pure unit tests.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from depth_graph_search.cli.config import CLISettings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED = {
    "database_url": "postgresql://depth:depth@localhost:5432/depth_graph",
    "openai_api_key": "sk-test-key",
}


def _make_settings(**overrides: object) -> CLISettings:
    """Construct CLISettings with required fields + optional overrides.

    Passes values via model_validate to bypass env-reading for pure unit tests.
    """
    data = {**_REQUIRED, **overrides}
    return CLISettings.model_validate(data)


# ---------------------------------------------------------------------------
# Scenario: All values from env
# ---------------------------------------------------------------------------


class TestValidConfig:
    def test_valid_required_vars_creates_instance(self) -> None:
        """Given both required vars, CLISettings instantiates without error."""
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

    def test_default_openrouter_api_key_is_none(self) -> None:
        settings = _make_settings()
        assert settings.openrouter_api_key is None

    def test_cli_settings_has_no_api_host(self) -> None:
        """CLISettings must NOT expose api_host (API-only field)."""
        settings = _make_settings()
        assert not hasattr(settings, "api_host")

    def test_cli_settings_has_no_api_port(self) -> None:
        """CLISettings must NOT expose api_port (API-only field)."""
        settings = _make_settings()
        assert not hasattr(settings, "api_port")

    def test_cli_settings_has_no_log_level(self) -> None:
        """CLISettings must NOT expose log_level (API-only field)."""
        settings = _make_settings()
        assert not hasattr(settings, "log_level")


# ---------------------------------------------------------------------------
# Scenario: Missing required field
# ---------------------------------------------------------------------------


class TestMissingRequiredVars:
    def test_missing_database_url_raises(self) -> None:
        """Missing DATABASE_URL raises ValidationError identifying the field."""
        with pytest.raises(PydanticValidationError) as exc_info:
            CLISettings.model_validate({"openai_api_key": "sk-key"})
        assert "database_url" in str(exc_info.value).lower()

    def test_missing_openai_api_key_raises(self) -> None:
        """Missing OPENAI_API_KEY raises ValidationError."""
        with pytest.raises(PydanticValidationError) as exc_info:
            CLISettings.model_validate(
                {"database_url": "postgresql://depth:depth@localhost:5432/depth_graph"}
            )
        assert "openai_api_key" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Scenario: DATABASE_URL validation
# ---------------------------------------------------------------------------


class TestDatabaseUrlValidation:
    def test_invalid_dsn_scheme_raises(self) -> None:
        """mysql:// DSN raises ValidationError with PostgreSQL message."""
        with pytest.raises(PydanticValidationError) as exc_info:
            _make_settings(database_url="mysql://user:pass@host/db")
        assert "postgresql" in str(exc_info.value).lower()

    def test_postgresql_scheme_accepted(self) -> None:
        """postgresql:// is a valid DSN scheme."""
        settings = _make_settings(
            database_url="postgresql://depth:depth@localhost:5432/depth_graph"
        )
        assert settings.database_url.startswith("postgresql://")

    def test_postgresql_psycopg_scheme_accepted(self) -> None:
        """postgresql+psycopg:// is also valid."""
        settings = _make_settings(
            database_url="postgresql+psycopg://depth:depth@localhost:5432/depth_graph"
        )
        assert settings.database_url.startswith("postgresql+psycopg://")


# ---------------------------------------------------------------------------
# Scenario: validate_openrouter_key validator
# ---------------------------------------------------------------------------


class TestOpenrouterKeyConditional:
    def test_openrouter_without_key_raises(self) -> None:
        """LLM_PROVIDER=openrouter without OPENROUTER_API_KEY raises ValidationError."""
        with pytest.raises(PydanticValidationError) as exc_info:
            _make_settings(llm_provider="openrouter")
        assert "openrouter" in str(exc_info.value).lower()

    def test_openrouter_with_key_succeeds(self) -> None:
        """LLM_PROVIDER=openrouter with OPENROUTER_API_KEY creates instance."""
        settings = _make_settings(
            llm_provider="openrouter", openrouter_api_key="or-test-key"
        )
        assert settings.openrouter_api_key == "or-test-key"

    def test_openai_provider_does_not_require_openrouter_key(self) -> None:
        """Default LLM_PROVIDER=openai does not require OPENROUTER_API_KEY."""
        settings = _make_settings()
        assert settings.llm_provider == "openai"
        assert settings.openrouter_api_key is None
