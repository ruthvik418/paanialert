"""Twilio calls POST /whatsapp for every incoming message. Owner: A.

Twilio gives up after about 15 seconds, so this only checks the signature, puts
the message on SQS and replies at once. The worker does the slow part.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from urllib.parse import parse_qs
from xml.sax.saxutils import escape

import boto3
from twilio.request_validator import RequestValidator

from common.config import REGION, secret

log = logging.getLogger()
log.setLevel(logging.INFO)

FIELDS = (
    "From", "Body", "NumMedia", "MediaUrl0", "MediaContentType0",
    "Latitude", "Longitude", "ProfileName", "MessageSid", "WaId",
)
ACK = "Got it, checking… / Mil gaya, dekh rahe hain…"

_sqs = None


def handler(event, context):
    params = parse_form(event)
    headers = {k.lower(): v for k, v in (event.get("headers") or {}).items()}

    try:
        token = secret("twilio_auth_token")
    except Exception:
        log.error("SSM parameter twilio_auth_token is missing; add it, then retry")
        return response(503, "Not configured", "text/plain")

    url = public_url(event)
    if not RequestValidator(token).validate(url, params, headers.get("x-twilio-signature", "")):
        log.warning("Rejected request with a bad Twilio signature for %s", url)
        return response(403, "Forbidden", "text/plain")

    message = {k: params.get(k, "") for k in FIELDS}
    queue().send_message(QueueUrl=os.environ["INCOMING_QUEUE_URL"], MessageBody=json.dumps(message))
    log.info("queued message sid=%s", message["MessageSid"])
    return response(200, twiml(ACK), "text/xml")


def parse_form(event) -> dict[str, str]:
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    return {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True).items()}


def public_url(event) -> str:
    """The exact URL Twilio called, which the signature is computed over."""
    ctx = event.get("requestContext") or {}
    host = ctx.get("domainName") or (event.get("headers") or {}).get("host", "")
    url = f"https://{host}{event.get('rawPath', '/whatsapp')}"
    query = event.get("rawQueryString")
    return f"{url}?{query}" if query else url


def twiml(text: str) -> str:
    return f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(text)}</Message></Response>'


def response(status: int, body: str, content_type: str) -> dict:
    return {"statusCode": status, "headers": {"Content-Type": content_type}, "body": body}


def queue():
    global _sqs
    if _sqs is None:
        _sqs = boto3.client("sqs", region_name=REGION)
    return _sqs
