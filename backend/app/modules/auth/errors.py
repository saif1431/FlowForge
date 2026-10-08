from pydantic import JsonValue


class AuthError(Exception):
    def __init__(
        self, status: int, code: str, message: str, details: dict[str, JsonValue] | None = None
    ) -> None:
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


def unauthenticated() -> AuthError:
    return AuthError(401, "UNAUTHENTICATED", "Sign in to continue.")
