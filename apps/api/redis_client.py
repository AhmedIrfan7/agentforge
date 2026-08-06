"""Async Redis client — a single connection pool for the process, same
pattern as db.py's SQLAlchemy engine (one client, opened once, reused).
"""

import redis.asyncio as redis

from config import settings

redis_client: redis.Redis = redis.from_url(settings.redis_url, decode_responses=True)
