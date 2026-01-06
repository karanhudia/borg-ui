"""
Archive caching service with Redis and in-memory fallback backends.

This module provides a unified caching interface for archive browsing with:
- Redis backend for distributed caching (primary)
- In-memory LRU backend for fallback when Redis unavailable
- Automatic compression for large archives (>100KB)
- Configurable TTL and size limits
- Repository-level and global cache clearing
"""

import asyncio
import json
import logging
import time
import zlib
from abc import ABC, abstractmethod
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

import redis
from redis.connection import ConnectionPool
from redis.exceptions import ConnectionError, RedisError, TimeoutError

from app.config import settings

logger = logging.getLogger(__name__)

# Compression settings
COMPRESSION_THRESHOLD_BYTES = 100 * 1024  # 100KB
COMPRESSION_LEVEL = 6  # zlib compression level (balanced)
MARKER_RAW = b"\x00"
MARKER_COMPRESSED = b"\x01"


class CacheBackend(ABC):
    """Abstract base class for cache backends."""

    @abstractmethod
    async def get(self, key: str) -> Optional[bytes]:
        """
        Get a value from the cache.

        Args:
            key: Cache key

        Returns:
            Cached bytes value or None if not found/expired
        """
        pass

    @abstractmethod
    async def set(self, key: str, value: bytes, ttl_seconds: int) -> bool:
        """
        Set a value in the cache with TTL.

        Args:
            key: Cache key
            value: Bytes value to cache
            ttl_seconds: Time to live in seconds

        Returns:
            True if successfully cached, False otherwise
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """
        Delete a key from the cache.

        Args:
            key: Cache key

        Returns:
            True if key was deleted, False if not found
        """
        pass

    @abstractmethod
    async def keys(self, pattern: str) -> List[str]:
        """
        Get all keys matching a pattern.

        Args:
            pattern: Pattern to match (e.g., "archive:1:*")

        Returns:
            List of matching keys
        """
        pass

    @abstractmethod
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with stats (hits, misses, size, etc.)
        """
        pass

    @abstractmethod
    async def clear(self) -> int:
        """
        Clear all cache entries.

        Returns:
            Number of entries cleared
        """
        pass

    @abstractmethod
    async def get_size_bytes(self) -> int:
        """
        Get total size of cached data in bytes.

        Returns:
            Total size in bytes
        """
        pass


class RedisBackend(CacheBackend):
    """Redis-based cache backend with connection pooling and health checks."""

    def __init__(
        self,
        url: Optional[str] = None,
        host: str = "localhost",
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        max_connections: int = 10,
    ):
        """
        Initialize Redis backend.

        Args:
            url: Redis URL (e.g., redis://hostname:6379/0) - takes precedence if provided
            host: Redis host (used if url not provided)
            port: Redis port (used if url not provided)
            db: Redis database number (used if url not provided)
            password: Optional Redis password (used if url not provided)
            max_connections: Max connections in pool
        """
        self.url = url
        self.host = host
        self.port = port
        self.db = db
        self.password = password

        # Connection pool - use URL if provided, otherwise use host/port
        if url:
            self.pool = ConnectionPool.from_url(
                url,
                max_connections=max_connections,
                decode_responses=False,  # We handle bytes
                socket_timeout=5,
                socket_connect_timeout=5,
            )
        else:
            self.pool = ConnectionPool(
                host=host,
                port=port,
                db=db,
                password=password,
                max_connections=max_connections,
                decode_responses=False,  # We handle bytes
                socket_timeout=5,
                socket_connect_timeout=5,
            )

        self._client: Optional[redis.Redis] = None
        self._is_available = False
        self._last_health_check = 0
        self._health_check_interval = 30  # seconds

        # Stats
        self._hits = 0
        self._misses = 0

    def _get_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._client is None:
            self._client = redis.Redis(connection_pool=self.pool)
        return self._client

    async def _health_check(self) -> bool:
        """
        Perform Redis health check.

        Returns:
            True if Redis is available, False otherwise
        """
        now = time.time()
        if now - self._last_health_check < self._health_check_interval:
            return self._is_available

        try:
            client = self._get_client()
            client.ping()
            self._is_available = True
            self._last_health_check = now
            return True
        except (ConnectionError, TimeoutError, RedisError) as e:
            logger.warning(f"Redis health check failed: {e}")
            self._is_available = False
            self._last_health_check = now
            return False

    async def get(self, key: str) -> Optional[bytes]:
        """Get a value from Redis."""
        if not await self._health_check():
            return None

        try:
            client = self._get_client()
            value = client.get(key)
            if value:
                self._hits += 1
                return value
            else:
                self._misses += 1
                return None
        except RedisError as e:
            logger.error(f"Redis get error for key '{key}': {e}")
            self._misses += 1
            return None

    async def set(self, key: str, value: bytes, ttl_seconds: int) -> bool:
        """Set a value in Redis with TTL."""
        if not await self._health_check():
            return False

        try:
            client = self._get_client()
            client.setex(key, ttl_seconds, value)
            return True
        except RedisError as e:
            logger.error(f"Redis set error for key '{key}': {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete a key from Redis."""
        if not await self._health_check():
            return False

        try:
            client = self._get_client()
            result = client.delete(key)
            return result > 0
        except RedisError as e:
            logger.error(f"Redis delete error for key '{key}': {e}")
            return False

    async def keys(self, pattern: str) -> List[str]:
        """Get all keys matching a pattern."""
        if not await self._health_check():
            return []

        try:
            client = self._get_client()
            keys = client.keys(pattern)
            return [k.decode("utf-8") if isinstance(k, bytes) else k for k in keys]
        except RedisError as e:
            logger.error(f"Redis keys error for pattern '{pattern}': {e}")
            return []

    async def get_stats(self) -> Dict[str, Any]:
        """Get Redis cache statistics."""
        if not await self._health_check():
            return {
                "backend": "redis",
                "available": False,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": 0.0,
                "size_bytes": 0,
                "entry_count": 0,
            }

        try:
            client = self._get_client()
            info = client.info("memory")
            dbsize = client.dbsize()

            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0.0

            return {
                "backend": "redis",
                "available": True,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "size_bytes": info.get("used_memory", 0),
                "entry_count": dbsize,
            }
        except RedisError as e:
            logger.error(f"Redis stats error: {e}")
            return {
                "backend": "redis",
                "available": False,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": 0.0,
                "size_bytes": 0,
                "entry_count": 0,
            }

    async def clear(self) -> int:
        """Clear all entries in the current Redis database."""
        if not await self._health_check():
            return 0

        try:
            client = self._get_client()
            dbsize = client.dbsize()
            client.flushdb()
            return dbsize
        except RedisError as e:
            logger.error(f"Redis clear error: {e}")
            return 0

    async def get_size_bytes(self) -> int:
        """Get total memory used by Redis."""
        if not await self._health_check():
            return 0

        try:
            client = self._get_client()
            info = client.info("memory")
            return info.get("used_memory", 0)
        except RedisError as e:
            logger.error(f"Redis size error: {e}")
            return 0


class InMemoryBackend(CacheBackend):
    """In-memory LRU cache with size limits and automatic eviction."""

    def __init__(self, max_size_bytes: int = 2 * 1024 * 1024 * 1024):
        """
        Initialize in-memory backend.

        Args:
            max_size_bytes: Maximum cache size in bytes (default 2GB)
        """
        self.max_size_bytes = max_size_bytes
        self._cache: OrderedDict[str, Tuple[bytes, float]] = OrderedDict()  # key -> (value, expiry_time)
        self._size_bytes = 0

        # Stats
        self._hits = 0
        self._misses = 0

    async def get(self, key: str) -> Optional[bytes]:
        """Get a value from in-memory cache."""
        # Clean expired entries periodically
        await self._cleanup_expired()

        if key not in self._cache:
            self._misses += 1
            return None

        value, expiry = self._cache[key]

        # Check if expired
        if time.time() > expiry:
            await self.delete(key)
            self._misses += 1
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        self._hits += 1
        return value

    async def set(self, key: str, value: bytes, ttl_seconds: int) -> bool:
        """Set a value in in-memory cache with TTL."""
        value_size = len(value)
        expiry_time = time.time() + ttl_seconds

        # If key exists, remove old size
        if key in self._cache:
            old_value, _ = self._cache[key]
            self._size_bytes -= len(old_value)

        # Evict entries if we're approaching the limit
        while self._size_bytes + value_size > self.max_size_bytes and len(self._cache) > 0:
            await self._evict_oldest()

        # Check if we still can't fit after eviction
        if value_size > self.max_size_bytes:
            logger.warning(f"Cache value too large ({value_size} bytes), skipping")
            return False

        # Add new entry
        self._cache[key] = (value, expiry_time)
        self._cache.move_to_end(key)
        self._size_bytes += value_size

        return True

    async def delete(self, key: str) -> bool:
        """Delete a key from in-memory cache."""
        if key not in self._cache:
            return False

        value, _ = self._cache[key]
        self._size_bytes -= len(value)
        del self._cache[key]
        return True

    async def keys(self, pattern: str) -> List[str]:
        """Get all keys matching a pattern (simple glob-style)."""
        await self._cleanup_expired()

        # Convert glob pattern to simple matching
        # Support: archive:* or archive:1:* patterns
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return [k for k in self._cache.keys() if k.startswith(prefix)]
        else:
            return [k for k in self._cache.keys() if k == pattern]

    async def get_stats(self) -> Dict[str, Any]:
        """Get in-memory cache statistics."""
        await self._cleanup_expired()

        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0.0

        return {
            "backend": "in-memory",
            "available": True,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "size_bytes": self._size_bytes,
            "entry_count": len(self._cache),
            "max_size_bytes": self.max_size_bytes,
        }

    async def clear(self) -> int:
        """Clear all entries in the in-memory cache."""
        count = len(self._cache)
        self._cache.clear()
        self._size_bytes = 0
        return count

    async def get_size_bytes(self) -> int:
        """Get total size of in-memory cache."""
        return self._size_bytes

    async def _evict_oldest(self):
        """Evict the oldest (least recently used) entry."""
        if not self._cache:
            return

        # OrderedDict: first item is oldest
        key, (value, _) = self._cache.popitem(last=False)
        self._size_bytes -= len(value)
        logger.debug(f"Evicted cache entry: {key}")

    async def _cleanup_expired(self):
        """Remove expired entries from cache."""
        now = time.time()
        expired_keys = [key for key, (_, expiry) in self._cache.items() if now > expiry]

        for key in expired_keys:
            await self.delete(key)

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")


class ArchiveCacheService:
    """
    Unified archive caching service with compression and dual backend support.

    Features:
    - Automatic compression for large archives (>100KB)
    - Cache key format: archive:{repo_id}:{archive_name}
    - Graceful degradation from Redis to in-memory
    - Repository-level and global cache clearing
    """

    def __init__(self):
        """Initialize the cache service with Redis and in-memory backends."""
        self._redis_backend: Optional[RedisBackend] = None
        self._memory_backend: InMemoryBackend = InMemoryBackend(
            max_size_bytes=settings.cache_max_size_mb * 1024 * 1024
        )
        self._current_backend: CacheBackend = self._memory_backend

        # Precedence: redis_url > redis_host/port > in-memory fallback

        # Option 1: Try external Redis URL (highest priority)
        if settings.redis_url and settings.redis_url.lower() != "disabled":
            try:
                self._redis_backend = RedisBackend(url=settings.redis_url)
                self._current_backend = self._redis_backend
                logger.info(f"Archive cache initialized with external Redis backend (URL: {settings.redis_url})")
            except Exception as e:
                logger.warning(f"Failed to initialize external Redis from URL, trying local: {e}")
                # Fall through to try local Redis

        # Option 2: Try local Redis (if external URL not configured or failed)
        if self._current_backend == self._memory_backend and settings.redis_host and settings.redis_host.lower() != "disabled":
            try:
                self._redis_backend = RedisBackend(
                    host=settings.redis_host,
                    port=settings.redis_port,
                    db=settings.redis_db,
                    password=settings.redis_password,
                )
                self._current_backend = self._redis_backend
                logger.info(f"Archive cache initialized with local Redis backend ({settings.redis_host}:{settings.redis_port})")
            except Exception as e:
                logger.warning(f"Failed to initialize local Redis, using in-memory cache: {e}")
                self._current_backend = self._memory_backend

        # Option 3: In-memory fallback (if no Redis configured or both failed)
        if self._current_backend == self._memory_backend and not self._redis_backend:
            logger.info("Archive cache initialized with in-memory backend (no Redis configured)")

    def _make_key(self, repo_id: int, archive_name: str) -> str:
        """
        Generate cache key for an archive.

        Args:
            repo_id: Repository ID
            archive_name: Archive name

        Returns:
            Cache key in format: archive:{repo_id}:{archive_name}
        """
        return f"archive:{repo_id}:{archive_name}"

    def _serialize(self, items: List[Dict]) -> bytes:
        """
        Serialize archive items to bytes with optional compression.

        Args:
            items: List of archive items

        Returns:
            Serialized bytes with marker (0x00=raw, 0x01=compressed)
        """
        # Convert to JSON
        json_str = json.dumps(items)
        json_bytes = json_str.encode("utf-8")

        # Compress if over threshold
        if len(json_bytes) > COMPRESSION_THRESHOLD_BYTES:
            compressed = zlib.compress(json_bytes, level=COMPRESSION_LEVEL)
            logger.debug(
                f"Compressed {len(json_bytes)} bytes to {len(compressed)} bytes "
                f"({len(compressed) / len(json_bytes) * 100:.1f}%)"
            )
            return MARKER_COMPRESSED + compressed
        else:
            return MARKER_RAW + json_bytes

    def _deserialize(self, data: bytes) -> List[Dict]:
        """
        Deserialize archive items from bytes.

        Args:
            data: Serialized bytes with marker

        Returns:
            List of archive items
        """
        if not data or len(data) < 1:
            return []

        marker = data[0:1]
        payload = data[1:]

        if marker == MARKER_COMPRESSED:
            # Decompress
            decompressed = zlib.decompress(payload)
            json_str = decompressed.decode("utf-8")
        elif marker == MARKER_RAW:
            # Raw JSON
            json_str = payload.decode("utf-8")
        else:
            logger.error(f"Unknown cache marker: {marker!r}")
            return []

        return json.loads(json_str)

    async def get(self, repo_id: int, archive_name: str) -> Optional[List[Dict]]:
        """
        Get cached archive items.

        Args:
            repo_id: Repository ID
            archive_name: Archive name

        Returns:
            List of archive items or None if not cached
        """
        key = self._make_key(repo_id, archive_name)

        try:
            data = await self._current_backend.get(key)
            if data is None:
                return None

            items = self._deserialize(data)
            logger.debug(f"Cache hit for {key} ({len(items)} items)")
            return items
        except Exception as e:
            logger.error(f"Cache get error for {key}: {e}")
            return None

    async def set(self, repo_id: int, archive_name: str, items: List[Dict]) -> bool:
        """
        Cache archive items.

        Args:
            repo_id: Repository ID
            archive_name: Archive name
            items: List of archive items to cache

        Returns:
            True if successfully cached, False otherwise
        """
        key = self._make_key(repo_id, archive_name)

        try:
            data = self._serialize(items)

            # Skip caching if too large (>500MB uncompressed is suspicious)
            if len(data) > 500 * 1024 * 1024:
                logger.warning(f"Archive {key} too large to cache ({len(data)} bytes), skipping")
                return False

            success = await self._current_backend.set(key, data, settings.cache_ttl_seconds)
            if success:
                logger.debug(f"Cached {key} ({len(items)} items, {len(data)} bytes)")
            return success
        except Exception as e:
            logger.error(f"Cache set error for {key}: {e}")
            return False

    async def clear_repository(self, repo_id: int) -> int:
        """
        Clear all cached archives for a repository.

        Args:
            repo_id: Repository ID

        Returns:
            Number of entries cleared
        """
        pattern = f"archive:{repo_id}:*"

        try:
            keys = await self._current_backend.keys(pattern)
            count = 0
            for key in keys:
                if await self._current_backend.delete(key):
                    count += 1

            logger.info(f"Cleared {count} cache entries for repository {repo_id}")
            return count
        except Exception as e:
            logger.error(f"Cache clear error for repository {repo_id}: {e}")
            return 0

    async def clear_all(self) -> int:
        """
        Clear all cached archives.

        Returns:
            Number of entries cleared
        """
        try:
            count = await self._current_backend.clear()
            logger.info(f"Cleared all cache ({count} entries)")
            return count
        except Exception as e:
            logger.error(f"Cache clear all error: {e}")
            return 0

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats including backend type, size, hit rate, etc.
        """
        try:
            stats = await self._current_backend.get_stats()

            # Add service-level info
            stats["ttl_seconds"] = settings.cache_ttl_seconds
            stats["max_size_mb"] = settings.cache_max_size_mb

            # Add connection information
            if isinstance(self._current_backend, RedisBackend):
                if self._redis_backend and self._redis_backend.url:
                    stats["connection_type"] = "external_url"
                    # Redact password from URL for security
                    safe_url = self._redis_backend.url
                    if "@" in safe_url:
                        # URL format: redis://:password@host:port/db
                        # Redact password: redis://:***@host:port/db
                        parts = safe_url.split("@", 1)
                        if ":" in parts[0]:
                            protocol = parts[0].split("://", 1)[0]
                            stats["connection_info"] = f"{protocol}://:***@{parts[1]}"
                        else:
                            stats["connection_info"] = safe_url
                    else:
                        stats["connection_info"] = safe_url
                else:
                    stats["connection_type"] = "local"
                    stats["connection_info"] = f"{self._redis_backend.host}:{self._redis_backend.port}/{self._redis_backend.db}"
            else:
                stats["connection_type"] = "in-memory"
                stats["connection_info"] = "Python process memory"

            # Add Redis fallback status if applicable
            if self._redis_backend and self._current_backend == self._memory_backend:
                stats["redis_fallback"] = True

            return stats
        except Exception as e:
            logger.error(f"Cache stats error: {e}")
            return {
                "backend": "unknown",
                "available": False,
                "error": str(e),
            }

    def get_backend_type(self) -> str:
        """
        Get the current active backend type.

        Returns:
            'redis' or 'in-memory'
        """
        if isinstance(self._current_backend, RedisBackend):
            return "redis"
        else:
            return "in-memory"

    def reconfigure(self, redis_url: Optional[str] = None, cache_max_size_mb: Optional[int] = None):
        """
        Reconfigure the cache service with new settings.

        This method allows changing Redis connection or cache size at runtime.
        Useful when user updates settings via UI.

        Args:
            redis_url: New Redis URL (or None to clear)
            cache_max_size_mb: New maximum cache size in MB

        Returns:
            Dict with status and connection info
        """
        try:
            # Update in-memory backend size if provided
            if cache_max_size_mb is not None:
                self._memory_backend = InMemoryBackend(
                    max_size_bytes=cache_max_size_mb * 1024 * 1024
                )
                logger.info(f"Updated in-memory cache max size to {cache_max_size_mb}MB")

            # Reconfigure Redis connection
            old_backend_type = self.get_backend_type()

            # Reset to in-memory first
            self._current_backend = self._memory_backend
            self._redis_backend = None

            # Try new Redis URL if provided
            if redis_url and redis_url.lower() not in ("disabled", "none", ""):
                try:
                    self._redis_backend = RedisBackend(url=redis_url)
                    # Test connection
                    client = self._redis_backend._get_client()
                    client.ping()
                    self._current_backend = self._redis_backend
                    logger.info(f"Reconfigured to external Redis backend (URL: {redis_url})")
                    return {
                        "success": True,
                        "backend": "redis",
                        "connection_type": "external_url",
                        "message": f"Successfully connected to external Redis"
                    }
                except Exception as e:
                    logger.warning(f"Failed to connect to new Redis URL, falling back to local: {e}")
                    # Fall through to try local Redis

            # Try local Redis (if external URL not provided or failed)
            if self._current_backend == self._memory_backend and settings.redis_host and settings.redis_host.lower() != "disabled":
                try:
                    self._redis_backend = RedisBackend(
                        host=settings.redis_host,
                        port=settings.redis_port,
                        db=settings.redis_db,
                        password=settings.redis_password,
                    )
                    # Test connection
                    client = self._redis_backend._get_client()
                    client.ping()
                    self._current_backend = self._redis_backend
                    logger.info(f"Reconfigured to local Redis backend ({settings.redis_host}:{settings.redis_port})")
                    return {
                        "success": True,
                        "backend": "redis",
                        "connection_type": "local",
                        "message": f"Connected to local Redis at {settings.redis_host}:{settings.redis_port}"
                    }
                except Exception as e:
                    logger.warning(f"Failed to connect to local Redis, using in-memory: {e}")

            # Fallback to in-memory
            logger.info("Reconfigured to in-memory backend")
            return {
                "success": True,
                "backend": "in-memory",
                "connection_type": "in-memory",
                "message": "Using in-memory cache (Redis not configured or unavailable)"
            }

        except Exception as e:
            logger.error(f"Cache reconfiguration error: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to reconfigure cache: {str(e)}"
            }


# Global singleton instance
archive_cache = ArchiveCacheService()
