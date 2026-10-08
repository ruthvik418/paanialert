"""Copy photos and voice notes from Twilio into our S3 bucket. Owner: B.

The bucket deletes everything after 7 days (lifecycle rule in template.yaml).
"""
from __future__ import annotations

import logging
import os

import boto3
import requests

from common.config import REGION, secret

log = logging.getLogger(__name__)

_EXTENSIONS = {
    "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
    "audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/amr": "amr", "audio/mp4": "m4a",
}
_s3 = None


def save_media(msg: dict, name: str) -> tuple[str | None, str | None]:
    """Return (photo_key, audio_key) for the first attachment, or (None, None)."""
    if int(msg.get("NumMedia") or 0) < 1 or not msg.get("MediaUrl0"):
        return None, None
    content_type = (msg.get("MediaContentType0") or "").split(";")[0].strip()
    extension = _EXTENSIONS.get(content_type)
    if not extension:
        log.info("ignoring attachment of type %s", content_type)
        return None, None
    try:
        resp = requests.get(
            msg["MediaUrl0"],
            auth=(secret("twilio_account_sid"), secret("twilio_auth_token")),
            timeout=20,
        )
        resp.raise_for_status()
    except Exception:
        log.exception("could not download media")
        return None, None

    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3", region_name=REGION)
    key = f"media/{name}.{extension}"
    _s3.put_object(Bucket=os.environ["MEDIA_BUCKET"], Key=key, Body=resp.content, ContentType=content_type)
    return (key, None) if content_type.startswith("image/") else (None, key)
