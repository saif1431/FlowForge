"""Generate matching local-only credentials without overwriting existing configuration."""

from pathlib import Path
from secrets import token_urlsafe


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    targets = (root / ".env", root / "backend/.env", root / "frontend/.env.local")
    if any(path.exists() for path in targets):
        raise SystemExit("Configuration already exists; no files changed. Edit it manually.")

    postgres, redis, rabbit, minio = (token_urlsafe(32) for _ in range(4))
    contents = (
        f"POSTGRES_USER=flowforge\nPOSTGRES_DB=flowforge\nPOSTGRES_PORT=15432\n"
        f"POSTGRES_PASSWORD={postgres}\n"
        f"REDIS_PASSWORD={redis}\nRABBITMQ_DEFAULT_USER=flowforge\n"
        f"RABBITMQ_DEFAULT_PASS={rabbit}\nMINIO_ROOT_USER=flowforge\n"
        f"MINIO_ROOT_PASSWORD={minio}\n",
        "APP_ENV=local\n"
        f"DATABASE_URL=postgresql+asyncpg://flowforge:{postgres}@127.0.0.1:15432/flowforge\n"
        f"REDIS_URL=redis://:{redis}@127.0.0.1:6379/0\n"
        f"RABBITMQ_URL=amqp://flowforge:{rabbit}@127.0.0.1:5672//\n"
        "MINIO_ENDPOINT=http://127.0.0.1:9000\nDEPENDENCY_TIMEOUT_SECONDS=3\n",
        "# No browser-visible environment variables are needed in Milestone 0.\n",
    )
    for path, content in zip(targets, contents, strict=True):
        path.write_text(content, encoding="utf-8")
    print("Created local environment files with generated credentials. No secrets printed.")


if __name__ == "__main__":
    main()
