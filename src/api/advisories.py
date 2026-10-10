"""Officials' manual warnings: "boil water" or "don't use tap water" for a circle on the map. Owner: A.

Issuing one sends the warning, in each person's language, to everyone subscribed
in a geohash-6 cell that overlaps the circle: WhatsApp subscribers and web-app
push subscribers. The advisory keeps who it warned, so lifting it sends the
all-clear to exactly those people. Every step is written to the Activity table.
"""
from __future__ import annotations

import logging
import uuid

from agent.messages import clean_note, warning_lifted_text, warning_text
from common import db, push
from common.geo import cells_within
from common.hashing import mask_number
from common.models import Advisory
from common.timeutil import now_iso
from common.twilio_send import send_whatsapp

log = logging.getLogger(__name__)

RADII = (500, 1000, 2000)
KINDS = ("boil", "do_not_use")
INDIA_LAT, INDIA_LON = (6.0, 37.5), (68.0, 97.5)


class Invalid(Exception):
    pass


def area(body: dict) -> tuple[float, float, int]:
    """The circle from a request body, checked: (lat, lon, radius_m)."""
    lat, lon, radius = body.get("lat"), body.get("lon"), body.get("radius_m")
    for name, value in (("lat", lat), ("lon", lon)):
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value != value:
            raise Invalid(f"{name} must be a number")
    if not (INDIA_LAT[0] <= lat <= INDIA_LAT[1] and INDIA_LON[0] <= lon <= INDIA_LON[1]):
        raise Invalid("lat and lon must be a place in India")
    if radius not in RADII or isinstance(radius, bool):
        raise Invalid(f"radius_m must be one of {list(RADII)}")
    return float(lat), float(lon), int(radius)


def recipients(lat: float, lon: float, radius_m: int) -> tuple[list[str], list[dict], list[dict]]:
    """(cells, WhatsApp subscribers, app push subscribers) for a circle."""
    cells = cells_within(lat, lon, radius_m)
    return cells, db.subscribers_in_cells(cells), app_subscribers(cells)


def app_subscribers(cells: list[str]) -> list[dict]:
    """Web-app devices that asked for warnings in these cells ("Warn me about my area")."""
    return db.app_subscribers_in_cells(cells)


def preview(body: dict) -> dict:
    lat, lon, radius = area(body)
    cells, whatsapp, app = recipients(lat, lon, radius)
    return {"cells": len(cells), "whatsapp": len(whatsapp), "app": len(app), "total": len(whatsapp) + len(app)}


def issue(body: dict, ip: str) -> Advisory:
    lat, lon, radius = area(body)
    kind = body.get("kind")
    if kind not in KINDS:
        raise Invalid(f"kind must be one of {list(KINDS)}")
    note = body.get("note")
    if note is not None and not isinstance(note, str):
        raise Invalid("note must be text")
    cluster_id = _optional_id(body.get("cluster_id"), "cluster_id")
    report_id = _optional_id(body.get("report_id"), "report_id")

    cells, whatsapp, app = recipients(lat, lon, radius)
    advisory = Advisory(
        advisory_id=uuid.uuid4().hex, lat=lat, lon=lon, radius_m=radius, kind=kind, created_at=now_iso(),
        note=clean_note(note), cells=cells, whatsapp_to=[s["phone_hash"] for s in whatsapp],
        app_to=[s["subscription_id"] for s in app], cluster_id=cluster_id, report_id=report_id,
    )
    db.put_advisory(advisory)
    db.log_activity("warning_issued", cluster_id, advisory_id=advisory.advisory_id, warning=kind, radius_m=radius,
                    lat=round(lat, 4), lon=round(lon, 4), report_id=report_id, note=advisory.note,
                    recipients=len(whatsapp) + len(app), ip=ip)
    sent = _send_all(advisory, whatsapp, app, lambda lang, wa: warning_text(kind, advisory.note, lang, wa), "warning")
    log.info("advisory %s issued: %s, %d m, %d of %d sent", advisory.advisory_id, kind, radius, sent,
             len(whatsapp) + len(app))
    return advisory


def lift(advisory_id: str, ip: str) -> Advisory | None:
    """End an active advisory and send the all-clear to the people it warned. None if not active."""
    advisory = db.get_advisory(advisory_id)
    if advisory is None or not db.lift_advisory(advisory_id, now_iso()):
        return None
    db.log_activity("warning_lifted", advisory.cluster_id, advisory_id=advisory_id, warning=advisory.kind, ip=ip)
    # Only people still subscribed: someone who sent STOP since doesn't hear from us again.
    whatsapp = [s for s in (db.get_subscriber(h) for h in advisory.whatsapp_to) if s]
    app = [s for s in (get_app_subscriber(i) for i in advisory.app_to) if s]
    _send_all(advisory, whatsapp, app, lambda lang, wa: warning_lifted_text(advisory.kind, lang, wa), "warning_all_clear")
    return db.get_advisory(advisory_id)


def get_app_subscriber(subscription_id: str) -> dict | None:
    return db.get_app_subscriber(subscription_id)


def _send_all(advisory: Advisory, whatsapp: list[dict], app: list[dict], text_for, kind: str) -> int:
    """Send to every recipient, logging each send; one failure doesn't stop the rest. Returns how many were sent."""
    sent = 0
    for sub in whatsapp:
        to = mask_number(sub["phone"])
        try:
            sid = send_whatsapp(sub["phone"], text_for(sub.get("lang", "en"), True))
        except Exception as exc:
            log.exception("%s failed for one WhatsApp subscriber", kind)
            db.log_activity(kind, advisory.cluster_id, advisory_id=advisory.advisory_id, channel="whatsapp", to=to,
                            ok=False, error=str(exc)[:200])
            continue
        db.log_activity(kind, advisory.cluster_id, advisory_id=advisory.advisory_id, channel="whatsapp", to=to,
                        ok=True, sid=sid)
        sent += 1
    sent += send_app(advisory, app, text_for, kind)
    return sent


def send_app(advisory: Advisory, app: list[dict], text_for, kind: str) -> int:
    """Web push to app subscribers, each in their language, logged like the WhatsApp sends."""
    sent = 0
    for sub in app:
        ok, error = push.send({**sub, "tag": f"advisory-{advisory.advisory_id}"}, "PaaniAlert",
                              text_for(sub.get("lang", "en"), False))
        db.log_activity(kind, advisory.cluster_id, advisory_id=advisory.advisory_id, channel="push",
                        to=push.label(sub), ok=ok, error=error)
        sent += ok
    return sent


def public_rows() -> list[dict]:
    """Active advisories for anyone: centre rounded to about 100 m, no note, nobody's identity."""
    return [{"lat": round(a.lat, 3), "lon": round(a.lon, 3), "radius_m": a.radius_m, "kind": a.kind,
             "created_at": a.created_at}
            for a in db.all_advisories() if a.status == "active"]


def _optional_id(value, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 64:
        raise Invalid(f"{name} must be an id")
    return value
