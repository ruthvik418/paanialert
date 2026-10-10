"""Dashboard API. Owner: A.

Every route except /health and /public/* needs the x-dashboard-key header,
which is checked against SSM /paanialert/dashboard_key.

Reports carry the reporter's WhatsApp name and a masked number. The full number
is only returned by POST /reports/{id}/contact, and each call is audited.
"""
from __future__ import annotations

import hmac
import json
import logging
import os
from dataclasses import asdict

import boto3
from botocore.config import Config

from cluster.app import send_all_clear
from common import db
from common.config import REGION, secret
from common.timeutil import hours_ago_iso, now_iso

log = logging.getLogger()
log.setLevel(logging.INFO)

STATUSES = {"acknowledged", "fixed", "false_alarm"}
PHOTO_URL_SECONDS = 300
_s3 = None


def handler(event, context):
    route = event.get("routeKey", "")
    if route.startswith("GET /public/"):
        return public_clusters()
    if not authorised(event):
        return reply(401, {"error": "Missing or wrong x-dashboard-key"})
    if route == "GET /reports":
        return reports(event)
    if route == "GET /clusters":
        return clusters()
    if route == "POST /clusters/{id}/status":
        return set_status(event)
    if route == "POST /reports/{id}/contact":
        return contact(event)
    if route == "GET /reports/{id}/photo":
        return photo(event)
    if route == "GET /activity":
        return activity(event)
    return reply(404, {"error": f"No route {route}"})


def authorised(event) -> bool:
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    given = headers.get("x-dashboard-key", "")
    return bool(given) and hmac.compare_digest(given, secret("dashboard_key"))


def reports(event):
    params = event.get("queryStringParameters") or {}
    since = params.get("since") or hours_ago_iso(48)
    rows = []
    for r in db.recent_reports(since):
        row = asdict(r)
        row.pop("phone_hash", None)
        rows.append(row)
    return reply(200, {"reports": rows, "since": since})


def contact(event):
    """The reporter's full number. Every call is written to the AuditLog before the number is returned."""
    report = db.get_report((event.get("pathParameters") or {}).get("id", ""))
    phone = db.get_contact(report.phone_hash) if report else None
    if not phone:
        return reply(404, {"error": "No number on file for this report"})
    http = (event.get("requestContext") or {}).get("http") or {}
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
    db.put_audit(report.report_id, now_iso(), http.get("sourceIp", ""),
                 http.get("userAgent") or headers.get("user-agent", ""))
    log.info("number shown for report %s", report.report_id)
    return reply(200, {"report_id": report.report_id, "phone": phone})


def photo(event):
    """A link to the report's photo that works for 5 minutes."""
    global _s3
    report = db.get_report((event.get("pathParameters") or {}).get("id", ""))
    if not report or not report.photo_key:
        return reply(404, {"error": "No photo for this report"})
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=REGION, config=Config(signature_version="s3v4"))
    url = _s3.generate_presigned_url(
        "get_object", Params={"Bucket": os.environ["MEDIA_BUCKET"], "Key": report.photo_key},
        ExpiresIn=PHOTO_URL_SECONDS,
    )
    return reply(200, {"url": url, "expires_in": PHOTO_URL_SECONDS})


def activity(event):
    """Everything PaaniAlert did (alerts, messages, emails, status changes), newest first."""
    params = event.get("queryStringParameters") or {}
    since = params.get("since") or hours_ago_iso(48)
    return reply(200, {"activity": db.recent_activity(since), "since": since})


def clusters():
    cutoff = hours_ago_iso(48)
    rows = [asdict(c) for c in db.all_clusters()
            if c.status in ("open", "acknowledged") or (c.first_seen or "") >= cutoff]
    return reply(200, {"clusters": rows})


def set_status(event):
    cluster_id = (event.get("pathParameters") or {}).get("id", "")
    try:
        status = json.loads(event.get("body") or "{}").get("status")
    except ValueError:
        status = None
    if status not in STATUSES:
        return reply(400, {"error": f"status must be one of {sorted(STATUSES)}"})
    before = db.get_cluster(cluster_id)
    if before is None:
        return reply(404, {"error": "No such cluster"})
    try:
        db.update_cluster_status(cluster_id, status, now_iso())
    except Exception as exc:
        if "ConditionalCheckFailed" in type(exc).__name__ or "ConditionalCheckFailed" in str(exc):
            return reply(404, {"error": "No such cluster"})
        raise
    log.info("cluster %s set to %s", cluster_id, status)
    db.log_activity("status", cluster_id, status=status, was=before.status)
    all_clear = 0
    # Only people who were warned get the all-clear, and only once.
    if status == "fixed" and before.status != "fixed" and before.alert_at:
        all_clear = send_all_clear(before)
    return reply(200, {"cluster_id": cluster_id, "status": status, "all_clear_sent": all_clear})


def public_clusters():
    """What anyone can see: no report text, location rounded to about 100 m."""
    rows = []
    for c in db.open_clusters():
        rows.append({
            "level": c.level,
            "lat": round(c.centre_lat, 3),
            "lon": round(c.centre_lon, 3),
            "report_count": c.report_count,
            "sick_households": c.sick_households,
            "status": c.status,
            "first_seen": c.first_seen,
            "alert_at": c.alert_at,
        })
    return reply(200, {"clusters": rows})


def reply(status: int, body: dict):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }
