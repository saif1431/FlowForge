from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import AuditEvent, AuthSession, AuthToken, User
from app.modules.auth.errors import AuthError, unauthenticated
from app.modules.auth.security import DUMMY_HASH, digest, hash_password, new_token, verify_password


def now() -> datetime:
    return datetime.now(UTC)


def audit(db: AsyncSession, action: str, request_id: str, user_id: UUID | None = None) -> None:
    db.add(AuditEvent(actor_user_id=user_id, action=action, request_id=request_id))


async def register(db: AsyncSession, email: str, password: str, request_id: str) -> None:
    encoded = await hash_password(password)
    user_id = await db.scalar(
        insert(User)
        .values(email=email, password_hash=encoded)
        .on_conflict_do_nothing(index_elements=[User.email])
        .returning(User.id)
    )
    if user_id is not None:
        audit(db, "auth.register", request_id, user_id)
        await issue_token(db, user_id, "verify_email", request_id)
    else:
        audit(db, "auth.registration_declined", request_id)
        await db.commit()
        raise AuthError(
            409,
            "EMAIL_ALREADY_REGISTERED",
            "An account with this email already exists. Sign in with your original password "
            "or reset it. Registering again does not change your password.",
        )
    await db.commit()


async def login(
    db: AsyncSession, email: str, password: str, settings: Settings, request_id: str
) -> tuple[User, str]:
    user = await db.scalar(select(User).where(User.email == email).with_for_update())
    valid = await verify_password(password, user.password_hash if user else DUMMY_HASH)
    if user is None or not valid:
        audit(db, "auth.login_failed", request_id, user.id if user else None)
        await db.commit()
        raise AuthError(401, "INVALID_CREDENTIALS", "Email or password is incorrect.")
    raw = new_token()
    timestamp = now()
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=digest(raw),
            created_at=timestamp,
            last_seen_at=timestamp,
            expires_at=timestamp + timedelta(seconds=settings.session_absolute_seconds),
        )
    )
    audit(db, "auth.login", request_id, user.id)
    await db.commit()
    return user, raw


async def authenticate(
    db: AsyncSession, raw: str | None, settings: Settings
) -> tuple[User, AuthSession]:
    if raw is None or len(raw) != 43:
        raise unauthenticated()
    session = await db.scalar(select(AuthSession).where(AuthSession.token_hash == digest(raw)))
    if session is None:
        raise unauthenticated()
    # All auth mutations lock the user first. Re-read the session after acquiring that lock.
    user = await db.scalar(select(User).where(User.id == session.user_id).with_for_update())
    session = await db.scalar(
        select(AuthSession)
        .where(AuthSession.id == session.id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    timestamp = now()
    if (
        user is None
        or session is None
        or session.revoked_at is not None
        or session.expires_at <= timestamp
        or session.last_seen_at <= timestamp - timedelta(seconds=settings.session_idle_seconds)
    ):
        raise unauthenticated()
    session.last_seen_at = timestamp
    return user, session


async def revoke_all(db: AsyncSession, user_id: UUID) -> None:
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=now())
    )


async def issue_token(db: AsyncSession, user_id: UUID, purpose: str, request_id: str) -> str:
    # Caller must hold the user lock (or have just inserted this user).
    timestamp = now()
    await db.execute(
        update(AuthToken)
        .where(
            AuthToken.user_id == user_id, AuthToken.purpose == purpose, AuthToken.used_at.is_(None)
        )
        .values(used_at=timestamp)
    )
    raw = new_token()
    db.add(
        AuthToken(
            user_id=user_id,
            purpose=purpose,
            token_hash=digest(raw),
            created_at=timestamp,
            expires_at=timestamp + timedelta(hours=24 if purpose == "verify_email" else 1),
        )
    )
    audit(db, f"auth.{purpose}_requested", request_id, user_id)
    return raw


async def request_reset(db: AsyncSession, email: str, request_id: str) -> None:
    user = await db.scalar(select(User).where(User.email == email).with_for_update())
    if user:
        # M12 will deliver the raw token through an email adapter. Never return it over the API.
        await issue_token(db, user.id, "reset_password", request_id)
    await db.commit()


async def consume_token(
    db: AsyncSession, raw: str, purpose: str, request_id: str, password: str | None = None
) -> None:
    invalid = AuthError(400, "INVALID_TOKEN", "This link is invalid or expired. Request a new one.")
    token = await db.scalar(
        select(AuthToken).where(AuthToken.token_hash == digest(raw), AuthToken.purpose == purpose)
    )
    if token is None:
        raise invalid
    user = await db.scalar(select(User).where(User.id == token.user_id).with_for_update())
    token = await db.scalar(
        select(AuthToken)
        .where(AuthToken.id == token.id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if user is None or token is None or token.used_at is not None or token.expires_at <= now():
        raise invalid
    token.used_at = now()
    if purpose == "verify_email":
        user.email_verified_at = now()
    else:
        assert password is not None
        user.password_hash = await hash_password(password)
        await revoke_all(db, user.id)
    audit(db, f"auth.{purpose}_completed", request_id, user.id)
    await db.commit()
