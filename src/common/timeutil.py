from datetime import datetime, timedelta, timezone


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    """ISO 8601 in UTC with a Z, so string comparison matches time order."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_iso() -> str:
    return iso(now())


def hours_ago_iso(hours: float) -> str:
    return iso(now() - timedelta(hours=hours))
