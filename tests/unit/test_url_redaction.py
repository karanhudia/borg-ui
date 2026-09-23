import pytest

from app.utils.url_redaction import safe_url


@pytest.mark.unit
@pytest.mark.parametrize(
    "url, expected",
    [
        ("redis://:secret@cache:6379/0", "redis://:***@cache:6379/0"),
        ("rediss://user:secret@cache:6379/0", "rediss://user:***@cache:6379/0"),
        ("redis://:p@ss:w@cache:6379/0", "redis://:***@cache:6379/0"),
        ("redis://cache:6379/0", "redis://cache:6379/0"),
        (None, None),
        ("", ""),
    ],
)
def test_safe_url_redacts_redis_urls(url, expected):
    assert safe_url(url) == expected
