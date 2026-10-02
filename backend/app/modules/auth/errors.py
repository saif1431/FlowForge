class AuthError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status = status
        self.code = code
        self.message = message


def unauthenticated() -> AuthError:
    return AuthError(401, "UNAUTHENTICATED", "Sign in to continue.")
