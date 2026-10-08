"""The cluster rule, as a pure function: no AWS calls, so tests and the replay reuse it. Owner: A.

Each report gets a severity score; reports in a geohash-6 cell and its 8
neighbours over the last 48 hours are added up:

    Watch: 3+ distinct phones, or total severity 10+
    Alert: 5+ distinct phones, or 2+ households reporting illness
    An active maintenance notice in the area caps it at Watch.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from common.geo import centre, neighbourhood
from common.models import Report

WINDOW_HOURS = 48
WATCH_PHONES, WATCH_SEVERITY = 3, 10
ALERT_PHONES, ALERT_SICK_HOUSEHOLDS = 5, 2


def severity(r: Report) -> float:
    score = 0.0
    if r.smell == "sewage":
        score += 3
    if r.colour not in ("clear", "unknown"):
        score += 2
    if r.taste in ("bad", "salty"):
        score += 1
    if (r.sick_count or 0) > 0:
        score += 4
    if r.photo_key:
        score += 1
    if r.clears_quickly:
        score /= 2  # dirty only for the first minutes of supply is common and less worrying
    return score


@dataclass
class Result:
    cluster_id: str
    cells: list[str]
    centre_lat: float
    centre_lon: float
    level: str
    report_count: int
    distinct_phones: int
    sick_households: int
    severity: float
    first_seen: str
    report_ids: list[str] = field(default_factory=list)


def _parse(iso: str) -> datetime:
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def evaluate(reports: list[Report], now: datetime, notice_cells: set[str] | frozenset = frozenset()) -> list[Result]:
    """Clusters at Watch or Alert, strongest first. One outbreak gives one cluster."""
    since = now - timedelta(hours=WINDOW_HOURS)
    recent = [r for r in reports if r.geohash6 and since <= _parse(r.created_at) <= now]
    by_cell: dict[str, list[Report]] = {}
    for r in recent:
        by_cell.setdefault(r.geohash6, []).append(r)

    candidates = []
    for cell in by_cell:
        area = neighbourhood(cell)
        group = [r for c in area for r in by_cell.get(c, [])]
        phones = {r.phone_hash for r in group}
        sick = {r.phone_hash for r in group if (r.sick_count or 0) > 0}
        total = round(sum(severity(r) for r in group), 1)
        if len(phones) >= ALERT_PHONES or len(sick) >= ALERT_SICK_HOUSEHOLDS:
            level = "alert"
        elif len(phones) >= WATCH_PHONES or total >= WATCH_SEVERITY:
            level = "watch"
        else:
            continue
        if level == "alert" and notice_cells.intersection(area):
            level = "watch"
        lat, lon = centre(cell)
        candidates.append(Result(
            cluster_id=cell, cells=area, centre_lat=round(lat, 5), centre_lon=round(lon, 5),
            level=level, report_count=len(group), distinct_phones=len(phones),
            sick_households=len(sick), severity=total,
            first_seen=min(r.created_at for r in group),
            report_ids=sorted(r.report_id for r in group),
        ))

    rank = {"alert": 0, "watch": 1}
    candidates.sort(key=lambda c: (rank[c.level], -c.severity, -c.distinct_phones, c.cluster_id))
    covered: set[str] = set()
    chosen = []
    for c in candidates:
        if c.cluster_id in covered:
            continue
        chosen.append(c)
        covered.update(c.cells)
    return chosen
