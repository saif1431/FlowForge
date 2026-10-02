"""Explicit local-only token issuance for testing before email delivery ships in M12."""

import argparse
import asyncio
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.core.config import load_settings
from app.db.connection import create_engine
from app.db.models import User
from app.modules.auth.service import issue_token


async def main(email: str, purpose: str) -> None:
    settings = load_settings()
    if settings.app_env != "local":
        raise SystemExit("This command is available only with APP_ENV=local.")
    engine = create_engine(settings)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            user = await db.scalar(
                select(User).where(User.email == email.lower()).with_for_update()
            )
            if user is None:
                raise SystemExit("Local account not found.")
            token = await issue_token(db, user.id, purpose, str(uuid4()))
            await db.commit()
        route = "verify-email" if purpose == "verify_email" else "reset-password"
        # Fragment tokens are not sent in HTTP URLs or Referer headers.
        print("Local testing link (treat as a secret; do not share):")
        print(f"{settings.trusted_origins[0]}/{route}#token={token}")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--purpose", choices=["verify_email", "reset_password"], required=True)
    args = parser.parse_args()
    asyncio.run(main(args.email, args.purpose))
