from __future__ import annotations

from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


def error_body(
    *,
    code: str,
    message: str,
    correlation_id: Optional[str] = None,
    details: Any = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    if correlation_id:
        body["error"]["correlation_id"] = correlation_id
    if details is not None:
        body["error"]["details"] = details
    return body


def _correlation(request: Request) -> Optional[str]:
    return getattr(request.state, "correlation_id", None) or request.headers.get("X-Correlation-Id")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exc(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "http_error"
        if exc.status_code == 401:
            code = "unauthorized"
        elif exc.status_code == 409:
            code = "conflict"
        elif exc.status_code == 422:
            code = "validation_error"
        elif exc.status_code >= 500:
            code = "upstream_error"
        detail = exc.detail
        message = detail if isinstance(detail, str) else "request failed"
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(code=code, message=message, correlation_id=_correlation(request), details=detail if not isinstance(detail, str) else None),
            headers={"X-Correlation-Id": _correlation(request) or ""},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exc(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_body(
                code="validation_error",
                message="request validation failed",
                correlation_id=_correlation(request),
                details=exc.errors(),
            ),
            headers={"X-Correlation-Id": _correlation(request) or ""},
        )
