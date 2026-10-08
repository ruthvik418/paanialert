"""Turning extracted fields into a saved Report. Shared by the agent and the fallback."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, get_args

from common import db
from common.geo import geohash6
from common.models import Colour, Report, Smell, Source, Taste
from common.timeutil import now_iso

_ALLOWED = {
    "smell": set(get_args(Smell)),
    "colour": set(get_args(Colour)),
    "taste": set(get_args(Taste)),
    "source": set(get_args(Source)),
}


@dataclass
class TurnContext:
    """What the worker knows about the person and this message."""

    phone_hash: str
    lang: str                       # language to reply in (the person's choice, Hindi by default)
    msg_lang: str | None = None     # language the message was written in, stored on the report
    lat: float | None = None
    lon: float | None = None
    photo_key: str | None = None
    audio_key: str | None = None
    saved: Report | None = field(default=None)


def save_extracted(ctx: TurnContext, fields: dict[str, Any]) -> Report:
    """Validate the fields, attach location and media, and store the report."""
    clean: dict[str, Any] = {}
    for name, allowed in _ALLOWED.items():
        value = str(fields.get(name) or "unknown").strip().lower()
        clean[name] = value if value in allowed else "unknown"
    for name in ("since_days", "sick_count"):
        value = fields.get(name)
        clean[name] = int(value) if isinstance(value, (int, float)) and value >= 0 else None
    symptoms = fields.get("symptoms") or []
    clean["symptoms"] = [str(s)[:40] for s in symptoms][:6] if isinstance(symptoms, list) else []
    landmark = fields.get("landmark")
    clean["landmark"] = str(landmark)[:120] if landmark and str(landmark).lower() != "unknown" else None
    clears = fields.get("clears_quickly")
    clean["clears_quickly"] = clears if isinstance(clears, bool) else None

    report = Report(
        report_id=uuid.uuid4().hex,
        phone_hash=ctx.phone_hash,
        created_at=now_iso(),
        lat=ctx.lat,
        lon=ctx.lon,
        geohash6=geohash6(ctx.lat, ctx.lon) if ctx.lat is not None and ctx.lon is not None else None,
        photo_key=ctx.photo_key,
        audio_key=ctx.audio_key,
        lang=ctx.msg_lang or ctx.lang,
        **clean,
    )
    db.put_report(report)
    ctx.saved = report
    return report
