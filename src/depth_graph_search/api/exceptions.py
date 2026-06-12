"""Exception handlers that map domain exceptions to HTTP responses.

No stack traces or internal details are ever leaked to API consumers.
The ``register_exception_handlers`` function is called once at app startup
via ``create_app()`` in ``api/__init__.py``.

Domain → HTTP mapping:
    ValidationError  → 422 Unprocessable Entity
    IngestionError   → 500 Internal Server Error
    LLMError         → 502 Bad Gateway
    StorageError     → 503 Service Unavailable
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from depth_graph_search.core.domain.exceptions import (
    IngestionError,
    LLMError,
    StorageError,
    ValidationError,
)


def register_exception_handlers(app: FastAPI) -> None:
    """Register all domain-exception-to-HTTP handlers on *app*.

    Call this exactly once, inside ``create_app()``, before any routes
    are added so that handlers are in place for every router.

    Args:
        app: The ``FastAPI`` application instance to register handlers on.
    """

    @app.exception_handler(ValidationError)
    async def handle_validation(req: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.exception_handler(IngestionError)
    async def handle_ingestion(req: Request, exc: IngestionError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": "Ingestion failed"})

    @app.exception_handler(LLMError)
    async def handle_llm(req: Request, exc: LLMError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": "LLM service error"})

    @app.exception_handler(StorageError)
    async def handle_storage(req: Request, exc: StorageError) -> JSONResponse:
        return JSONResponse(
            status_code=503, content={"detail": "Storage service unavailable"}
        )
