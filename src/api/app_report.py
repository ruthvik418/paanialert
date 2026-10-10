"""The web report app's API: a second way to report bad water, alongside WhatsApp. Owner: B.

Public routes (no dashboard key), throttled in template.yaml:

    POST /app/photo-url   {device_id, content_type, size}  -> {url, photo_key, expires_in}
    POST /app/report      {device_id, text, lat, lon, lang, photo_key?, request_id?}
                          -> {reply, report_id, saved}

A report goes through the same worker.handle() as a WhatsApp message, with
From "app:<device_id>" and channel "app", and the reply is returned instead of
sent. The device id is a random UUID the page keeps in localStorage; it is
hashed like a phone number and each one may send 10 reports a day.
"""
from __future__ import annotations

import json
import logging
import os
import re
import uuid

import boto3
from botocore.config import Config

from common import db
from common.config import REGION
from common.hashing import phone_hash
from common.timeutil import now_iso
from worker.app import handle

log = logging.getLogger()
log.setLevel(logging.INFO)

DAILY_LIMIT = 10
MAX_TEXT = 1000
MAX_PHOTO_BYTES = 5 * 1024 * 1024
PHOTO_TYPES = {"image/jpeg": "jpg", "image/png": "png"}
UPLOAD_URL_SECONDS = 300
LANGS = {"en", "hi", "hinglish"}
# India's bounding box (mainland and islands), generous by a little.
INDIA_LAT, INDIA_LON = (6.0, 37.5), (68.0, 97.5)
_s3 = None


class BadRequest(Exception):
    pass


def handler(event, context):
    route = event.get("routeKey", "")
    try:
        body = json.loads(event.get("body") or "{}")
        if not isinstance(body, dict):
            raise BadRequest("Send a JSON object")
        if route == "POST /app/report":
            return report(body)
        if route == "POST /app/photo-url":
            return photo_url(body)
    except (BadRequest, ValueError) as exc:
        return reply(400, {"error": str(exc) if isinstance(exc, BadRequest) else "Send valid JSON"})
    return reply(404, {"error": f"No route {route}"})


def report(body: dict):
    device_id = _device_id(body.get("device_id"))
    text = body.get("text")
    if not isinstance(text, str):
        raise BadRequest("text must be a string")
    text = text.strip()
    if len(text) > MAX_TEXT:
        raise BadRequest(f"text must be at most {MAX_TEXT} characters")
    lat, lon = _number(body.get("lat"), "lat"), _number(body.get("lon"), "lon")
    if not (INDIA_LAT[0] <= lat <= INDIA_LAT[1] and INDIA_LON[0] <= lon <= INDIA_LON[1]):
        raise BadRequest("lat and lon must be a place in India")
    lang = body.get("lang")
    if lang not in LANGS:
        raise BadRequest(f"lang must be one of {sorted(LANGS)}")
    photo_key = body.get("photo_key")
    if photo_key is not None:
        _check_photo(photo_key, device_id)
    if not text and not photo_key:
        raise BadRequest("Write what is wrong with the water, or add a photo")
    request_id = body.get("request_id")
    if request_id is not None:
        request_id = _uuid(request_id, "request_id")

    sender = f"app:{device_id}"
    ph = phone_hash(sender)
    if not db.take_app_quota(ph, now_iso()[:10], DAILY_LIMIT):
        return reply(429, {"error": f"This device has sent {DAILY_LIMIT} reports today. Try again tomorrow."})
    if db.get_language(ph) != lang:
        db.set_language(ph, lang)

    before = db.get_session(ph).get("last_report_id")
    sent: list[str] = []
    msg = {"From": sender, "Body": text, "Latitude": str(lat), "Longitude": str(lon), "channel": "app",
           "PhotoKey": photo_key or ""}
    if request_id:
        msg["MessageSid"] = f"app-{request_id}"   # a retried request is handled once
    answer = handle(msg, send=lambda to, body: sent.append(body))
    after = db.get_session(ph).get("last_report_id")
    saved = bool(after) and after != before
    log.info("app report from one device: saved=%s", saved)
    return reply(200, {"reply": answer, "report_id": after if saved else None, "saved": saved})


def photo_url(body: dict):
    device_id = _device_id(body.get("device_id"))
    content_type = body.get("content_type")
    if content_type not in PHOTO_TYPES:
        raise BadRequest(f"content_type must be one of {sorted(PHOTO_TYPES)}")
    size = body.get("size")
    if not isinstance(size, int) or isinstance(size, bool) or not 0 < size <= MAX_PHOTO_BYTES:
        raise BadRequest(f"size must be the file size in bytes, at most {MAX_PHOTO_BYTES}")
    key = f"app-uploads/{device_id}/{uuid.uuid4().hex}.{PHOTO_TYPES[content_type]}"
    # Content-Type and Content-Length are signed, so S3 refuses any other type or size.
    url = s3().generate_presigned_url(
        "put_object",
        Params={"Bucket": os.environ["MEDIA_BUCKET"], "Key": key, "ContentType": content_type, "ContentLength": size},
        ExpiresIn=UPLOAD_URL_SECONDS,
    )
    return reply(200, {"url": url, "photo_key": key, "expires_in": UPLOAD_URL_SECONDS,
                       "headers": {"Content-Type": content_type}})


def _check_photo(key, device_id: str) -> None:
    """The photo must be one this device uploaded through /app/photo-url, and within the limits."""
    pattern = rf"app-uploads/{re.escape(device_id)}/[0-9a-f]{{32}}\.(jpg|png)"
    if not isinstance(key, str) or not re.fullmatch(pattern, key):
        raise BadRequest("photo_key must come from /app/photo-url for this device")
    try:
        head = s3().head_object(Bucket=os.environ["MEDIA_BUCKET"], Key=key)
    except Exception:
        raise BadRequest("The photo wasn't uploaded. Try adding it again.") from None
    if head["ContentLength"] > MAX_PHOTO_BYTES or head.get("ContentType") not in PHOTO_TYPES:
        raise BadRequest("The photo must be a JPEG or PNG of at most 5 MB")


def _device_id(value) -> str:
    return _uuid(value, "device_id")


def _uuid(value, name: str) -> str:
    """The canonical lower-case form of a UUID written as 36 characters, e.g. from crypto.randomUUID()."""
    if isinstance(value, str) and len(value) == 36:
        try:
            return str(uuid.UUID(value))
        except ValueError:
            pass
    raise BadRequest(f"{name} must be a UUID")


def _number(value, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value != value:
        raise BadRequest(f"{name} must be a number")
    return float(value)


def s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=REGION, config=Config(signature_version="s3v4"))
    return _s3


def reply(status: int, body: dict):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, ensure_ascii=False),
    }
