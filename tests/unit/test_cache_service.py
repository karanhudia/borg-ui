from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.cache_service import (
    ArchiveCacheService,
    InMemoryBackend,
    MARKER_COMPRESSED,
    MARKER_RAW,
    RedisBackend,
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_in_memory_backend_tracks_hits_misses_and_deletes():
    backend = InMemoryBackend(max_size_bytes=1024)

    assert await backend.set("archive:1:a", b"abc", ttl_seconds=60) is True
    assert await backend.get("archive:1:a") == b"abc"
    assert await backend.delete("archive:1:a") is True
    assert await backend.get("archive:1:a") is None

    stats = await backend.get_stats()
    assert stats["backend"] == "in-memory"
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["entry_count"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_in_memory_backend_evicts_oldest_when_full():
    backend = InMemoryBackend(max_size_bytes=5)

    assert await backend.set("k1", b"aa", ttl_seconds=60) is True
    assert await backend.set("k2", b"bb", ttl_seconds=60) is True
    assert await backend.set("k3", b"cc", ttl_seconds=60) is True

    assert await backend.get("k1") is None
    assert await backend.get("k2") == b"bb"
    assert await backend.get("k3") == b"cc"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_in_memory_backend_expires_entries():
    backend = InMemoryBackend(max_size_bytes=1024)

    with patch(
        "app.services.cache_service.time.time", side_effect=[100.0, 102.0, 102.0, 102.0]
    ):
        assert await backend.set("expired", b"value", ttl_seconds=1) is True
        assert await backend.get("expired") is None


@pytest.mark.unit
def test_archive_cache_service_serializes_raw_and_compressed_payloads():
    service = ArchiveCacheService()

    raw = service._serialize([{"path": "a", "type": "-", "size": 1}])
    assert raw.startswith(MARKER_RAW)
    assert service._deserialize(raw) == [{"path": "a", "type": "-", "size": 1}]

    large_items = [{"path": "x", "blob": "y" * 150_000}]
    compressed = service._serialize(large_items)
    assert compressed.startswith(MARKER_COMPRESSED)
    assert service._deserialize(compressed) == large_items


@pytest.mark.unit
def test_archive_cache_service_returns_empty_for_unknown_marker():
    service = ArchiveCacheService()
    assert service._deserialize(b"\x09garbage") == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_archive_cache_service_set_get_and_clear_repository():
    service = ArchiveCacheService()
    service._current_backend = InMemoryBackend(max_size_bytes=1024 * 1024)

    items = [{"path": "docs/a.txt", "type": "-", "size": 10}]
    assert await service.set(1, "archive-a", items) is True
    assert await service.set(1, "archive-b", items) is True
    assert await service.set(2, "archive-c", items) is True

    assert await service.get(1, "archive-a") == items
    assert await service.clear_repository(1) == 2
    assert await service.get(1, "archive-a") is None
    assert await service.get(2, "archive-c") == items


@pytest.mark.unit
def test_archive_cache_service_switches_to_memory_after_repeated_redis_failures():
    service = ArchiveCacheService()
    fake_redis = MagicMock(spec=RedisBackend)
    service._redis_backend = fake_redis
    service._current_backend = fake_redis

    service._handle_redis_failure()
    service._handle_redis_failure()
    assert service.get_backend_type() == "redis"

    service._handle_redis_failure()
    assert service.get_backend_type() == "in-memory"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_archive_cache_service_get_stats_redacts_redis_password():
    service = ArchiveCacheService()
    fake_redis = MagicMock(spec=RedisBackend)
    fake_redis.url = "redis://:secret@cache.internal:6379/0"
    fake_redis.host = "cache.internal"
    fake_redis.port = 6379
    fake_redis.db = 0
    fake_redis.get_stats = AsyncMock(
        return_value={
            "backend": "redis",
            "available": True,
            "hits": 1,
            "misses": 0,
            "hit_rate": 100.0,
            "size_bytes": 12,
            "entry_count": 1,
        }
    )

    service._redis_backend = fake_redis
    service._current_backend = fake_redis

    stats = await service.get_stats()
    assert stats["connection_type"] == "external_url"
    assert stats["connection_info"] == "redis://:***@cache.internal:6379/0"


@pytest.mark.unit
def test_archive_cache_service_reconfigure_falls_back_to_memory_when_redis_unavailable():
    service = ArchiveCacheService()

    with (
        patch(
            "app.services.cache_service.ConnectionPool.from_url",
            side_effect=RuntimeError("no redis"),
        ),
        patch("app.services.cache_service.settings.redis_host", "disabled"),
    ):
        result = service.reconfigure(
            redis_url="redis://:secret@cache.internal:6379/0", cache_max_size_mb=32
        )

    assert result["success"] is True
    assert result["backend"] == "in-memory"
    assert service.get_backend_type() == "in-memory"
