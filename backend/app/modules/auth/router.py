from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import select

from app.db.models import AuthSession
from app.modules.auth import service
from app.modules.auth.dependencies import Database, config, limit, protect
from app.modules.auth.errors import AuthError
from app.modules.auth.schemas import (
    EmailInput,
    ErrorEnvelope,
    LoginInput,
    Message,
    RegisterInput,
    ResetInput,
    SessionList,
    SessionOutput,
    TokenInput,
    UserOutput,
)

router = APIRouter(
    prefix="/api/v1/auth",
    tags=["auth"],
    dependencies=[Depends(protect)],
    responses={code: {"model": ErrorEnvelope} for code in (400, 401, 403, 404, 413, 422, 429, 503)},
)


def clear_cookie(response: Response, request: Request) -> None:
    settings = config(request)
    response.delete_cookie(
        settings.session_cookie,
        path="/",
        secure=settings.secure_cookies,
        httponly=True,
        samesite="lax",
    )


@router.post("/register", status_code=202, responses={409: {"model": ErrorEnvelope}})
async def register(body: RegisterInput, request: Request, db: Database) -> Message:
    await service.register(
        db, body.email, body.password.get_secret_value(), request.state.request_id
    )
    return Message(message="Account created. Sign in with the email and password you just entered.")


@router.post("/login")
async def login(body: LoginInput, request: Request, response: Response, db: Database) -> UserOutput:
    await limit(request, "login:email", body.email, 10, 900)
    settings = config(request)
    user, raw = await service.login(
        db, body.email, body.password.get_secret_value(), settings, request.state.request_id
    )
    response.set_cookie(
        settings.session_cookie,
        raw,
        max_age=settings.session_absolute_seconds,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        path="/",
    )
    return UserOutput.model_validate(user).model_copy(
        update={"email_verification_required": settings.require_email_verification}
    )


@router.get("/me")
async def me(request: Request, db: Database) -> UserOutput:
    settings = config(request)
    user, _ = await service.authenticate(db, request.cookies.get(settings.session_cookie), settings)
    await db.commit()
    return UserOutput.model_validate(user).model_copy(
        update={"email_verification_required": settings.require_email_verification}
    )


@router.get("/sessions")
async def sessions(request: Request, db: Database) -> SessionList:
    settings = config(request)
    user, current = await service.authenticate(
        db, request.cookies.get(settings.session_cookie), settings
    )
    timestamp = service.now()
    rows = await db.scalars(
        select(AuthSession)
        .where(
            AuthSession.user_id == user.id,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > timestamp,
            AuthSession.last_seen_at > timestamp - timedelta(seconds=settings.session_idle_seconds),
        )
        .order_by(AuthSession.created_at.desc())
    )
    result = SessionList(
        items=[
            SessionOutput(
                id=row.id,
                created_at=row.created_at,
                last_seen_at=row.last_seen_at,
                expires_at=row.expires_at,
                current=row.id == current.id,
            )
            for row in rows
        ]
    )
    await db.commit()
    return result


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: Database) -> None:
    settings = config(request)
    try:
        user, current = await service.authenticate(
            db, request.cookies.get(settings.session_cookie), settings
        )
    except AuthError as exc:
        if exc.status != 401:
            raise
        await db.rollback()
    else:
        current.revoked_at = service.now()
        service.audit(db, "auth.logout", request.state.request_id, user.id)
        await db.commit()
    clear_cookie(response, request)


@router.post("/logout-all", status_code=204)
async def logout_all(request: Request, response: Response, db: Database) -> None:
    settings = config(request)
    user, _ = await service.authenticate(db, request.cookies.get(settings.session_cookie), settings)
    await service.revoke_all(db, user.id)
    service.audit(db, "auth.logout_all", request.state.request_id, user.id)
    await db.commit()
    clear_cookie(response, request)


@router.delete("/sessions/{session_id}", status_code=204)
async def revoke(session_id: UUID, request: Request, response: Response, db: Database) -> None:
    settings = config(request)
    user, current = await service.authenticate(
        db, request.cookies.get(settings.session_cookie), settings
    )
    target = await db.scalar(
        select(AuthSession).where(AuthSession.id == session_id, AuthSession.user_id == user.id)
    )
    if target is None:
        raise AuthError(404, "NOT_FOUND", "Session not found.")
    target.revoked_at = service.now()
    service.audit(db, "auth.session_revoked", request.state.request_id, user.id)
    await db.commit()
    if target.id == current.id:
        clear_cookie(response, request)


@router.post("/forgot-password", status_code=202)
async def forgot_password(body: EmailInput, request: Request, db: Database) -> Message:
    await limit(request, "reset:email", body.email, 3, 3600)
    await service.request_reset(db, body.email, request.state.request_id)
    return Message(message="Request received. Password-reset email delivery is not available yet.")


@router.post("/request-verification", status_code=202)
async def request_verification(request: Request, db: Database) -> Message:
    settings = config(request)
    user, _ = await service.authenticate(db, request.cookies.get(settings.session_cookie), settings)
    await limit(request, "verification:user", str(user.id), 3, 3600)
    if user.email_verified_at is None:
        await service.issue_token(db, user.id, "verify_email", request.state.request_id)
    await db.commit()
    return Message(message="Request received. Verification email delivery is not available yet.")


@router.post("/verify-email")
async def verify_email(body: TokenInput, request: Request, db: Database) -> Message:
    await service.consume_token(
        db, body.token.get_secret_value(), "verify_email", request.state.request_id
    )
    return Message(message="Email verified. You can return to your account.")


@router.post("/reset-password")
async def reset_password(
    body: ResetInput, request: Request, response: Response, db: Database
) -> Message:
    await service.consume_token(
        db,
        body.token.get_secret_value(),
        "reset_password",
        request.state.request_id,
        password=body.password.get_secret_value(),
    )
    clear_cookie(response, request)
    return Message(message="Password updated. Sign in with your new password.")
