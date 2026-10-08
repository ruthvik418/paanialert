"""Outgoing WhatsApp messages through Twilio's REST API. Owner: B.

Free-form messages only reach people who wrote to the bot in the last 24 hours
(Twilio error 63016 otherwise). Production alerts need a Meta-approved template.
"""
from __future__ import annotations

import logging

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from common.config import TWILIO_WHATSAPP_FROM, secret

log = logging.getLogger(__name__)
_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        _client = Client(secret("twilio_account_sid"), secret("twilio_auth_token"))
    return _client


def send_whatsapp(to: str, body: str, media_url: str | None = None) -> str:
    """Send a message and return its Twilio SID. Retries once on network errors."""
    to = to if to.startswith("whatsapp:") else "whatsapp:" + to
    kwargs = {"from_": TWILIO_WHATSAPP_FROM, "to": to, "body": body[:1600]}
    if media_url:
        kwargs["media_url"] = [media_url]
    for attempt in (1, 2):
        try:
            message = _get_client().messages.create(**kwargs)
            log.info("sent whatsapp sid=%s", message.sid)
            return message.sid
        except TwilioRestException:
            raise  # Twilio said no (bad number, outside 24 h window): retrying won't help
        except Exception:
            if attempt == 2:
                raise
            log.warning("send failed, retrying once", exc_info=True)
    raise RuntimeError("unreachable")
