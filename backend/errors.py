"""JSON error responses ``{error_code, message}`` (HLD 10.2)."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class APIError(Exception):
    def __init__(self, status: int, error_code: str, message: str) -> None:
        self.status, self.error_code, self.message = status, error_code, message


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def _api_error(_: Request, exc: APIError) -> JSONResponse:
        return JSONResponse({"error_code": exc.error_code, "message": exc.message}, exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        parts = [f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in exc.errors()]
        return JSONResponse(
            {"error_code": "VALIDATION_ERROR", "message": "; ".join(parts)}, status_code=422
        )
