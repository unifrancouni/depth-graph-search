"""Unit tests for api/exceptions.py — domain exception → HTTP handler mapping.

Tests call each handler function directly with a minimal mock Request and a
domain exception instance. No real server is started.

Verified mappings:
    ValidationError  → 422
    IngestionError   → 500  (body: "Ingestion failed")
    LLMError         → 502  (body: "LLM service error")
    StorageError     → 503  (body: "Storage service unavailable")

Also verifies that no Python traceback is exposed in any response body.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from depth_graph_search.api.exceptions import register_exception_handlers
from depth_graph_search.core.domain.exceptions import (
    IngestionError,
    LLMError,
    StorageError,
    ValidationError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_request() -> MagicMock:
    """Return a minimal MagicMock that stands in for a FastAPI Request."""
    return MagicMock()


def _get_handlers(app: FastAPI) -> dict:
    """Extract exception handler callables from a FastAPI app's exception_handlers."""
    return dict(app.exception_handlers)


# ---------------------------------------------------------------------------
# Fixture: app with exception handlers registered
# ---------------------------------------------------------------------------


@pytest.fixture()
def app_with_handlers() -> FastAPI:
    """Minimal FastAPI app with all domain exception handlers registered."""
    app = FastAPI()
    register_exception_handlers(app)
    return app


# ---------------------------------------------------------------------------
# TestHandlerStatusCodes
# ---------------------------------------------------------------------------


class TestHandlerStatusCodes:
    """Each domain exception maps to the correct HTTP status code."""

    async def test_validation_error_maps_to_422(self, app_with_handlers: FastAPI) -> None:
        handlers = _get_handlers(app_with_handlers)
        handler = handlers[ValidationError]
        req = _make_mock_request()
        exc = ValidationError("content must not be empty")

        response: JSONResponse = await handler(req, exc)

        assert response.status_code == 422

    async def test_ingestion_error_maps_to_500(self, app_with_handlers: FastAPI) -> None:
        handlers = _get_handlers(app_with_handlers)
        handler = handlers[IngestionError]
        req = _make_mock_request()
        exc = IngestionError("pipeline failure")

        response: JSONResponse = await handler(req, exc)

        assert response.status_code == 500

    async def test_llm_error_maps_to_502(self, app_with_handlers: FastAPI) -> None:
        handlers = _get_handlers(app_with_handlers)
        handler = handlers[LLMError]
        req = _make_mock_request()
        exc = LLMError("upstream LLM timed out")

        response: JSONResponse = await handler(req, exc)

        assert response.status_code == 502

    async def test_storage_error_maps_to_503(self, app_with_handlers: FastAPI) -> None:
        handlers = _get_handlers(app_with_handlers)
        handler = handlers[StorageError]
        req = _make_mock_request()
        exc = StorageError("DB connection refused")

        response: JSONResponse = await handler(req, exc)

        assert response.status_code == 503


# ---------------------------------------------------------------------------
# TestHandlerResponseBody
# ---------------------------------------------------------------------------


class TestHandlerResponseBody:
    """Each handler returns the expected body without exposing tracebacks."""

    def _parse_body(self, response: JSONResponse) -> dict:
        """Decode the JSONResponse body bytes to a Python dict."""
        return json.loads(response.body)

    async def test_validation_error_body_contains_message(self, app_with_handlers: FastAPI) -> None:
        handlers = _get_handlers(app_with_handlers)
        handler = handlers[ValidationError]
        exc = ValidationError("content must not be empty")

        response = await handler(_make_mock_request(), exc)
        body = self._parse_body(response)

        assert "detail" in body
        assert "content must not be empty" in body["detail"]

    async def test_ingestion_error_body_is_generic(self, app_with_handlers: FastAPI) -> None:
        """IngestionError body must be generic — no internal detail leaked."""
        handlers = _get_handlers(app_with_handlers)
        handler = handlers[IngestionError]
        exc = IngestionError("internal pipeline crash with secret info")

        response = await handler(_make_mock_request(), exc)
        body = self._parse_body(response)

        assert body == {"detail": "Ingestion failed"}

    async def test_llm_error_body_is_generic(self, app_with_handlers: FastAPI) -> None:
        handlers = _get_handlers(app_with_handlers)
        handler = handlers[LLMError]
        exc = LLMError("secret API key exposed in traceback")

        response = await handler(_make_mock_request(), exc)
        body = self._parse_body(response)

        assert body == {"detail": "LLM service error"}

    async def test_storage_error_body_is_generic(self, app_with_handlers: FastAPI) -> None:
        handlers = _get_handlers(app_with_handlers)
        handler = handlers[StorageError]
        exc = StorageError("DB internal error with schema details")

        response = await handler(_make_mock_request(), exc)
        body = self._parse_body(response)

        assert body == {"detail": "Storage service unavailable"}


# ---------------------------------------------------------------------------
# TestNoTracebackLeaked
# ---------------------------------------------------------------------------


class TestNoTracebackLeaked:
    """Verify that no Python traceback text appears in any handler response body."""

    _TRACEBACK_MARKERS = ["Traceback", "File ", "line ", "raise ", "Error\n"]

    def _response_body_str(self, response: JSONResponse) -> str:
        return response.body.decode("utf-8")

    def _assert_no_traceback(self, body: str) -> None:
        for marker in self._TRACEBACK_MARKERS:
            assert marker not in body, f"Traceback marker found in response: {marker!r}"

    async def test_ingestion_handler_no_traceback(self, app_with_handlers: FastAPI) -> None:
        handlers = _get_handlers(app_with_handlers)
        handler = handlers[IngestionError]
        response = await handler(_make_mock_request(), IngestionError("boom"))
        self._assert_no_traceback(self._response_body_str(response))

    async def test_llm_handler_no_traceback(self, app_with_handlers: FastAPI) -> None:
        handlers = _get_handlers(app_with_handlers)
        handler = handlers[LLMError]
        response = await handler(_make_mock_request(), LLMError("boom"))
        self._assert_no_traceback(self._response_body_str(response))

    async def test_storage_handler_no_traceback(self, app_with_handlers: FastAPI) -> None:
        handlers = _get_handlers(app_with_handlers)
        handler = handlers[StorageError]
        response = await handler(_make_mock_request(), StorageError("boom"))
        self._assert_no_traceback(self._response_body_str(response))

    async def test_validation_handler_no_traceback(self, app_with_handlers: FastAPI) -> None:
        handlers = _get_handlers(app_with_handlers)
        handler = handlers[ValidationError]
        response = await handler(_make_mock_request(), ValidationError("bad input"))
        self._assert_no_traceback(self._response_body_str(response))


# ---------------------------------------------------------------------------
# TestHandlerRegistration
# ---------------------------------------------------------------------------


class TestHandlerRegistration:
    """Verify all four domain exceptions are registered on the app."""

    def test_all_handlers_registered(self) -> None:
        app = FastAPI()
        register_exception_handlers(app)
        handlers = _get_handlers(app)

        assert ValidationError in handlers
        assert IngestionError in handlers
        assert LLMError in handlers
        assert StorageError in handlers
