"""The web report app's API: a second way to report bad water, alongside WhatsApp. Owner: B.

Public routes (no dashboard key), throttled in template.yaml:

    POST /app/photo-url   {device_id, content_type, size}  -> {url, photo_key, expires_in}
    POST /app/report      {device_id, text, lat, lon, lang, photo_key?, request_id?}
                          -> {reply, report_id, saved}
    GET  /app/push-key    -> {public_key}   (VAPID, for "Warn me about my area")
    POST /app/subscribe   {device_id, subscription, lat, lon, lang} -> {subscribed, geohash6}
    POST /app/unsubscribe {device_id, endpoint} -> {subscribed: false}

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

from common import db, push
from common.config import REGION, secret
from common.geo import geohash6
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
_B64URL = re.compile(r"[A-Za-z0-9_-]{16,200}={0,2}")
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
        if route == "POST /app/subscribe":
            return subscribe(body)
        if route == "POST /app/unsubscribe":
            return unsubscribe(body)
        if route == "GET /app/push-key":
            return reply(200, {"public_key": secret("vapid_public_key")})
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
    lat, lon = _india(body.get("lat"), body.get("lon"))
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


def subscribe(body: dict):
    """Ask for warnings about one area: the browser's push subscription plus the point it cares about."""
    device_id = _device_id(body.get("device_id"))
    sub = body.get("subscription")
    if not isinstance(sub, dict) or not isinstance(sub.get("keys"), dict):
        raise BadRequest("subscription must be the browser's PushSubscription as JSON")
    endpoint = sub.get("endpoint")
    if not push.allowed_endpoint(endpoint):
        raise BadRequest("subscription endpoint must be a browser push service")
    p256dh, auth = sub["keys"].get("p256dh"), sub["keys"].get("auth")
    if not all(isinstance(k, str) and _B64URL.fullmatch(k) for k in (p256dh, auth)):
        raise BadRequest("subscription keys must be base64url")
    lat, lon = _india(body.get("lat"), body.get("lon"))
    lang = body.get("lang")
    if lang not in LANGS:
        raise BadRequest(f"lang must be one of {sorted(LANGS)}")
    item = {
        "subscription_id": push.subscription_id(endpoint), "endpoint": endpoint, "p256dh": p256dh, "auth": auth,
        "geohash6": geohash6(lat, lon), "lang": lang, "device_hash": phone_hash(f"app:{device_id}"),
        "created_at": now_iso(),
    }
    db.put_app_subscriber(item)
    log.info("app device subscribed to warnings in cell %s", item["geohash6"])
    return reply(201, {"subscribed": True, "geohash6": item["geohash6"]})


def unsubscribe(body: dict):
    device_id = _device_id(body.get("device_id"))
    endpoint = body.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint:
        raise BadRequest("endpoint must be the subscription's endpoint")
    existing = db.get_app_subscriber(push.subscription_id(endpoint))
    # Only the device that subscribed can remove it.
    if existing and existing.get("device_hash") == phone_hash(f"app:{device_id}"):
        db.delete_app_subscriber(existing["subscription_id"])
    return reply(200, {"subscribed": False})


def _india(lat, lon) -> tuple[float, float]:
    lat, lon = _number(lat, "lat"), _number(lon, "lon")
    if not (INDIA_LAT[0] <= lat <= INDIA_LAT[1] and INDIA_LON[0] <= lon <= INDIA_LON[1]):
        raise BadRequest("lat and lon must be a place in India")
    return lat, lon


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
