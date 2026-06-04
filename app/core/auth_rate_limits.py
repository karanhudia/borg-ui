from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
import math

from fastapi import HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database.models import AuthRateLimitBucket


@dataclass(frozen=True)
class AuthRateLimitPolicy:
    max_failures: int
    window: timedelta
    lockout: timedelta


def get_password_login_policy() -> AuthRateLimitPolicy:
    return AuthRateLimitPolicy(
        max_failures=settings.auth_rate_limit_max_attempts,
        window=timedelta(seconds=settings.auth_rate_limit_window_seconds),
        lockout=timedelta(seconds=settings.auth_rate_limit_lockout_seconds),
    )


def get_totp_login_policy() -> AuthRateLimitPolicy:
    return AuthRateLimitPolicy(
        max_failures=settings.auth_rate_limit_max_attempts,
        window=timedelta(seconds=settings.auth_rate_limit_window_seconds),
        lockout=timedelta(seconds=settings.auth_rate_limit_lockout_seconds),
    )


def get_passkey_login_policy() -> AuthRateLimitPolicy:
    return AuthRateLimitPolicy(
        max_failures=max(settings.auth_rate_limit_max_attempts, 8),
        window=timedelta(seconds=settings.auth_rate_limit_window_seconds),
        lockout=timedelta(seconds=settings.auth_rate_limit_lockout_seconds),
    )


def get_request_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    client_host = request.client.host if request.client and request.client.host else ""
    if forwarded_for and client_host in settings.trusted_proxies:
        client_ip = forwarded_for.split(",")[0].strip()
        if client_ip:
            return client_ip
    if client_host:
        return client_host
    return "unknown"


def build_rate_limit_key(scope: str, subject: str, client_ip: str) -> str:
    normalized_subject = (subject or "unknown").strip().lower() or "unknown"
    normalized_ip = client_ip.strip() or "unknown"
    return f"{scope}|{normalized_subject}|{normalized_ip}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _get_bucket(
    db: Session, *, scope: str, subject: str, client_ip: str
) -> Optional[AuthRateLimitBucket]:
    bucket_key = build_rate_limit_key(scope, subject, client_ip)
    return (
        db.query(AuthRateLimitBucket)
        .filter(AuthRateLimitBucket.bucket_key == bucket_key)
        .first()
    )


def _build_rate_limit_exception(locked_until: datetime) -> HTTPException:
    retry_after_seconds = max(
        1,
        math.ceil((locked_until - _utcnow()).total_seconds()),
    )
    return HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "key": "backend.errors.auth.tooManyRequests",
            "params": {"retryAfterSeconds": retry_after_seconds},
        },
        headers={"Retry-After": str(retry_after_seconds)},
    )


def enforce_auth_rate_limit(
    db: Session,
    *,
    scope: str,
    subject: str,
    client_ip: str,
    policy: AuthRateLimitPolicy,
) -> None:
    if not settings.auth_rate_limit_enabled:
        return
    for bucket_subject in (subject, "__ip_only__"):
        bucket = _get_bucket(
            db, scope=scope, subject=bucket_subject, client_ip=client_ip
        )
        if bucket is None:
            continue

        now = _utcnow()
        locked_until = _coerce_utc(bucket.locked_until)
        if locked_until and locked_until > now:
            raise _build_rate_limit_exception(locked_until)

        window_started_at = _coerce_utc(bucket.window_started_at)
        if window_started_at and window_started_at + policy.window <= now:
            db.delete(bucket)
            db.commit()


def record_auth_failure(
    db: Session,
    *,
    scope: str,
    subject: str,
    client_ip: str,
    policy: AuthRateLimitPolicy,
) -> Optional[HTTPException]:
    if not settings.auth_rate_limit_enabled:
        return None
    now = _utcnow()
    locked_until_values: list[datetime] = []
    for bucket_subject in (subject, "__ip_only__"):
        bucket = _get_bucket(
            db, scope=scope, subject=bucket_subject, client_ip=client_ip
        )
        if bucket is None:
            bucket = AuthRateLimitBucket(
                bucket_key=build_rate_limit_key(scope, bucket_subject, client_ip),
                scope=scope,
                subject=(bucket_subject or "unknown").strip().lower() or "unknown",
                client_ip=client_ip,
                failure_count=0,
                window_started_at=now,
                last_attempt_at=now,
            )
            db.add(bucket)

        window_started_at = _coerce_utc(bucket.window_started_at) or now
        if window_started_at + policy.window <= now:
            bucket.failure_count = 0
            bucket.window_started_at = now
            bucket.locked_until = None

        bucket.failure_count += 1
        bucket.last_attempt_at = now

        if bucket.failure_count >= policy.max_failures:
            bucket.locked_until = now + policy.lockout
            locked_until_values.append(bucket.locked_until)

    db.commit()

    locked_until = max(
        (_coerce_utc(value) for value in locked_until_values), default=None
    )
    if locked_until and locked_until > now:
        return _build_rate_limit_exception(locked_until)
    return None


def clear_auth_rate_limit(
    db: Session,
    *,
    scope: str,
    subject: str,
    client_ip: str,
) -> None:
    if not settings.auth_rate_limit_enabled:
        return
    deleted_any = False
    for bucket_subject in (subject, "__ip_only__"):
        bucket = _get_bucket(
            db, scope=scope, subject=bucket_subject, client_ip=client_ip
        )
        if bucket is None:
            continue
        db.delete(bucket)
        deleted_any = True
    if deleted_any:
        db.commit()
