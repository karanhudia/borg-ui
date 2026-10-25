"""Validate Borg operands without changing their spelling or authorization."""

from urllib.parse import urlsplit


def validate_operand(value: str, field: str, *, archive_path: bool = False) -> str:
    """Reject option-like values, including after archived-path normalization."""
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise ValueError(f"Invalid {field}")
    candidate = value.strip()
    if archive_path:
        candidate = candidate.strip("/").lstrip()
    if candidate.startswith("-"):
        raise ValueError(f"{field} must not start with a hyphen")
    return value


def validate_source(value: str) -> str:
    """Accept local paths and the supported SSH URL syntax."""
    validate_operand(value, "backup source")
    candidate = value.strip()
    if candidate.startswith("ssh://"):
        try:
            parsed = urlsplit(candidate)
            if not parsed.hostname or not parsed.path or parsed.password is not None:
                raise ValueError("Invalid SSH backup source")
            # Accessing port also validates its syntax and range.
            parsed.port
        except ValueError as exc:
            raise ValueError("Invalid SSH backup source") from exc
    return value
