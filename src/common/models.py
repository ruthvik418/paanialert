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
ReportStatus = Literal["new", "reviewing", "resolved", "false_report"]   # set by officials; false_report is left out of clusters
AdvisoryKind = Literal["boil", "do_not_use"]


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
    text: str | None = None          # the resident's original message, up to 1000 characters
    profile_name: str | None = None  # WhatsApp profile name (Twilio ProfileName)
    phone_masked: str | None = None  # e.g. "+91 98•••••210"; the full number is only in Contacts
    extracted_by: str | None = None  # "agent:<model id>" or "keywords"; None on reports from before Oct 10
    channel: Literal["whatsapp", "app"] = "whatsapp"   # how it arrived: WhatsApp or the web report page
    status: ReportStatus = "new"
    status_note: str | None = None   # the official's note with the status, up to 200 characters
    status_at: str | None = None


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
    report_ids: list[str] = field(default_factory=list)   # the reports in it at the last check


@dataclass
class Advisory:
    """A warning officials issued for a circle on the map, until they lift it."""

    advisory_id: str
    lat: float
    lon: float
    radius_m: int                    # 500, 1000 or 2000
    kind: AdvisoryKind
    created_at: str
    status: Literal["active", "lifted"] = "active"
    note: str | None = None          # cleaned: no links, at most 200 characters
    cells: list[str] = field(default_factory=list)          # geohash-6 cells overlapping the circle
    whatsapp_to: list[str] = field(default_factory=list)    # phone hashes warned, so lifting reaches the same people
    app_to: list[str] = field(default_factory=list)         # app push subscription ids warned
    cluster_id: str | None = None    # what it was issued from, if anything
    report_id: str | None = None
    lifted_at: str | None = None


T = TypeVar("T", Report, Cluster, Advisory)


def to_item(record: Report | Cluster | Advisory) -> dict[str, Any]:
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
