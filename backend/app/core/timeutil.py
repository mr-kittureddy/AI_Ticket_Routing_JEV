from datetime import datetime, timezone


def ensure_utc(value: datetime) -> datetime:
    """Returns a timezone-aware UTC datetime; naive values (as returned by SQLite) are treated as UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
