import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from starlette.concurrency import run_in_threadpool

hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
# Used for unknown accounts so login still performs an expensive password verification.
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


async def hash_password(password: str) -> str:
    return await run_in_threadpool(hasher.hash, password)


async def verify_password(password: str, encoded: str) -> bool:
    try:
        return await run_in_threadpool(hasher.verify, encoded, password)
    except VerificationError, InvalidHashError:
        return False
