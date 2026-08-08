"""S3-compatible object storage (MinIO locally, real S3 in production —
config.storage_endpoint_url is the only thing that changes between them,
per AGENTS.md SECTION 12's cloud-agnostic goal).

aioboto3, not plain boto3: every other I/O path in this app is async
(SQLAlchemy's async engine, async routes throughout) — a blocking boto3
call during a file upload would stall the event loop for every other
in-flight request for as long as the upload takes, not just the one
doing it.

The Session is a cheap, stateless factory (safe to hold as a module-level
singleton, same as db.py's engine or redis_client.py's client) — but
unlike those, the actual S3 client it hands out is opened fresh per
operation via `async with`, since aioboto3 clients wrap an aiohttp
session that isn't meant to outlive a single logical unit of work.
"""

from typing import Any

import aioboto3
from botocore.exceptions import ClientError

from config import settings

_session = aioboto3.Session()


def _client_context() -> Any:
    return _session.client(
        "s3",
        endpoint_url=settings.storage_endpoint_url,
        aws_access_key_id=settings.storage_access_key,
        aws_secret_access_key=settings.storage_secret_key,
    )


async def ensure_bucket_exists() -> None:
    """Idempotent — safe to call before every upload rather than once at
    app startup, deliberately: coupling this to app startup would make
    importing main.app (which every test file does) require MinIO to be
    reachable even for tests that never touch storage at all."""
    async with _client_context() as client:
        try:
            await client.head_bucket(Bucket=settings.storage_bucket)
        except ClientError as exc:
            status = exc.response.get("Error", {}).get("Code")
            if status not in ("404", "NoSuchBucket"):
                raise
            await client.create_bucket(Bucket=settings.storage_bucket)


async def upload_file(*, key: str, content: bytes, content_type: str) -> None:
    async with _client_context() as client:
        await client.put_object(
            Bucket=settings.storage_bucket, Key=key, Body=content, ContentType=content_type
        )
