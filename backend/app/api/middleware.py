import logging
from uuid import uuid4

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings
from app.modules.auth.errors import AuthError


def error_response(request_id: str, status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "error": {"code": code, "message": message, "details": {}, "request_id": request_id}
        },
        headers={"Cache-Control": "no-store", "X-Request-ID": request_id},
    )


async def auth_error(request: Request, exc: AuthError) -> JSONResponse:
    return error_response(request.state.request_id, exc.status, exc.code, exc.message)


async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Pydantic's default error body can contain the supplied password or reset token.
    return error_response(
        request.state.request_id, 422, "VALIDATION_ERROR", "Check the submitted fields."
    )


class AuthBoundary:
    """Bound API bodies, redact failures, and set cookie-auth CORS from loaded settings."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        if not scope["path"].startswith("/api/v1/"):
            await self.app(scope, receive, send)
            return
        settings: Settings = scope["app"].state.settings
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > 16384:
                await error_response(
                    request_id, 413, "REQUEST_TOO_LARGE", "Request body is too large."
                )(scope, receive, send)
                return
            if not message.get("more_body", False):
                break

        async def replay() -> Message:
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        started = False

        async def secured_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
                message["headers"] = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() not in {b"cache-control", b"x-request-id"}
                ]
                message.setdefault("headers", []).extend(
                    [
                        (b"cache-control", b"no-store"),
                        (b"x-request-id", request_id.encode()),
                        (b"x-content-type-options", b"nosniff"),
                    ]
                )
            await send(message)

        async def guarded(scope: Scope, receive: Receive, send: Send) -> None:
            try:
                await self.app(scope, receive, send)
            except Exception:
                # Do not log exceptions/SQL arguments containing authentication material.
                logging.getLogger("flowforge.auth").error(
                    "Authentication request failed: %s", request_id
                )
                if not started:
                    await error_response(
                        request_id,
                        503,
                        "AUTH_UNAVAILABLE",
                        "Authentication is temporarily unavailable.",
                    )(scope, receive, send)

        cors = CORSMiddleware(
            guarded,
            allow_origins=settings.trusted_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Content-Type", "X-CSRF-Protection"],
        )
        await cors(scope, replay, secured_send)
