"""The shared records: the contract between the three roles.

B writes Reports, A stores them and writes Clusters, C reads both through the
dashboard API. Change a field only after telling the team.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from decimal import Decimal
from typing import Any, Literal, TypeVar

Smell = Literal["none", "sewage", "chemical", "other", "unknown"]
Colour = Literal["clear", "yellow", "brown", "black", "cloudy", "unknown"]
Taste = Literal["normal", "bad", "salty", "unknown"]
Source = Literal["pipe", "borewell", "tanker", "unknown"]
Level = Literal["none", "watch", "alert"]
ClusterStatus = Literal["open", "acknowledged", "fixed", "false_alarm", "expired"]


@dataclass
class Report:
    """One complaint about the water, as extracted by the agent."""

    report_id: str
    phone_hash: str              # HMAC of the number, never the number itself
    created_at: str              # ISO 8601, UTC
    lat: float | None = None
    lon: float | None = None
    geohash6: str | None = None  # ~1.2 × 0.6 km cell
    landmark: str | None = None
    area: str | None = None          # place name looked up from the pin, e.g. "Rajwada, Indore"
    smell: Smell = "unknown"
    colour: Colour = "unknown"
    taste: Taste = "unknown"
    since_days: int | None = None
    sick_count: int | None = None   # None = not asked yet, 0 = nobody sick
    symptoms: list[str] = field(default_factory=list)
    clears_quickly: bool | None = None  # dirty only for the first minutes of supply
    photo_key: str | None = None
    audio_key: str | None = None
    lang: str = "unknown"            # "hi", "en" or "hinglish"
    source: Source = "unknown"
    tds: int | None = None           # mg/L, only after the user confirms the reading


@dataclass
class Cluster:
    """A group of nearby reports, written by the cluster check."""

    cluster_id: str
    cells: list[str]
    centre_lat: float
    centre_lon: float
    level: Level
    report_count: int
    distinct_phones: int
    sick_households: int
    severity: float
    status: ClusterStatus = "open"
    first_seen: str = ""
    alert_at: str | None = None
    escalated_at: str | None = None
    status_at: str | None = None     # when status last changed (set by the API, or on reopening)
    reopened_at: str | None = None   # last time new complaints reopened it after fixed / false_alarm
    reopen_count: int = 0


T = TypeVar("T", Report, Cluster)


def to_item(record: Report | Cluster) -> dict[str, Any]:
    """Dataclass to DynamoDB item: drops empty values, floats become Decimal."""
    return {k: _to_dynamo(v) for k, v in asdict(record).items() if v is not None and v != []}


def from_item(cls: type[T], item: dict[str, Any]) -> T:
    """DynamoDB item to dataclass: Decimals become numbers, unknown keys are ignored."""
    known = {f.name for f in fields(cls)}
    return cls(**{k: _from_dynamo(v) for k, v in item.items() if k in known})


def _to_dynamo(value: Any) -> Any:
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, list):
        return [_to_dynamo(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_dynamo(v) for k, v in value.items()}
    return value


def _from_dynamo(value: Any) -> Any:
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, list):
        return [_from_dynamo(v) for v in value]
    if isinstance(value, dict):
        return {k: _from_dynamo(v) for k, v in value.items()}
    return value
