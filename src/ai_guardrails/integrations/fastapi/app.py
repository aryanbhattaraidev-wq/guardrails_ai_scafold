"""Thin HTTP transport around ``GuardrailsService``.

This validates text; it is not an OpenAI-compatible proxy. All policy logic lives
in the service. Policy outcomes (including ``blocked`` and ``error``) are
returned as HTTP 200 with ``is_allowed`` so every transport reports the same
result; HTTP errors are reserved for malformed requests, auth, and size limits.
"""

from __future__ import annotations

import hmac
import logging
import os
from collections.abc import Awaitable, Callable, Mapping

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from ai_guardrails.core.exceptions import ConfigurationError, UnknownProfileError
from ai_guardrails.core.service import GuardrailsService
from ai_guardrails.core.types import ValidationStage
from ai_guardrails.integrations.fastapi.schemas import (
    HealthResponse,
    ValidateRequest,
    ValidateResponse,
)
from ai_guardrails.observability.logging import log_event

# A UTF-8 character is at most 4 bytes; JSON escaping can add more, so allow slack.
_BODY_OVERHEAD_BYTES = 8192
_BYTES_PER_CHAR = 6


def create_app(
    service: GuardrailsService,
    *,
    env: Mapping[str, str] | None = None,
) -> FastAPI:
    """Build the FastAPI app around an already-constructed service.

    Raises ``ConfigurationError`` if auth is enabled but the API key variable is
    not set, so a misconfigured deployment never starts unauthenticated.
    """
    api = service.settings.api
    environment = os.environ if env is None else env
    api_key = environment.get(api.api_key_env, "") if api.auth_enabled else ""
    if api.auth_enabled and not api_key:
        raise ConfigurationError(
            f"api.auth_enabled is true but environment variable '{api.api_key_env}' is not set"
        )
    max_body = api.max_text_chars * _BYTES_PER_CHAR + _BODY_OVERHEAD_BYTES

    app = FastAPI(title="ai-guardrails", version="0.1.0", docs_url=None, redoc_url=None)
    app.state.service = service

    @app.middleware("http")
    async def limit_body_size(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        declared = request.headers.get("content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > max_body):
            return JSONResponse({"detail": "request body too large"}, status_code=413)
        return await call_next(request)

    async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
        if not api.auth_enabled:
            return
        if x_api_key is None or not hmac.compare_digest(x_api_key.encode(), api_key.encode()):
            raise HTTPException(status_code=401, detail="invalid or missing API key")

    @app.exception_handler(RequestValidationError)
    async def on_invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI's default body echoes the offending input, which may be PII.
        problems = [{"loc": [str(p) for p in e["loc"]], "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse({"detail": problems}, status_code=422)

    @app.exception_handler(Exception)
    async def on_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        log_event("unhandled_error", logging.ERROR, error_type=type(exc).__name__)
        return JSONResponse({"detail": "internal error"}, status_code=500)

    async def handle(stage: ValidationStage, body: ValidateRequest) -> ValidateResponse:
        if len(body.text) > api.max_text_chars:
            raise HTTPException(status_code=413, detail="text too long")
        try:
            result = await service.validate(
                stage,
                body.text,
                profile=body.profile,
                request_id=body.request_id,
                metadata=body.metadata,
            )
        except UnknownProfileError:
            raise HTTPException(status_code=404, detail="unknown profile") from None
        return ValidateResponse.from_result(result)

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", profiles=service.profile_names)

    @app.post("/v1/validate/input", response_model=ValidateResponse)
    async def validate_input(
        body: ValidateRequest, _: None = Depends(require_api_key)
    ) -> ValidateResponse:
        return await handle(ValidationStage.INPUT, body)

    @app.post("/v1/validate/output", response_model=ValidateResponse)
    async def validate_output(
        body: ValidateRequest, _: None = Depends(require_api_key)
    ) -> ValidateResponse:
        return await handle(ValidationStage.OUTPUT, body)

    return app
