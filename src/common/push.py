"""Web push to the report app's subscribers ("Warn me about my area"). Owner: B.

Each subscription is the browser's push endpoint and keys, stored with the
geohash-6 cell the person asked about (AppSubscribers table). Messages are
signed with the VAPID key in SSM (/paanialert/vapid_private_key). When a push
service answers 404 or 410 the browser has dropped the subscription, so we
delete it too.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
from urllib.parse import urlparse

from common import db
from common.config import secret

log = logging.getLogger(__name__)

# Only the browsers' own push services: the server POSTs to this URL, so it must never be arbitrary.
PUSH_HOSTS = ("fcm.googleapis.com", "updates.push.services.mozilla.com", "push.services.mozilla.com",
              "web.push.apple.com", "notify.windows.com")
TTL_SECONDS = 12 * 3600
GONE = {404, 410}


def allowed_endpoint(endpoint) -> bool:
    if not isinstance(endpoint, str) or len(endpoint) > 1000:
        return False
    url = urlparse(endpoint)
    host = (url.hostname or "").lower()
    return url.scheme == "https" and any(host == h or host.endswith("." + h) for h in PUSH_HOSTS)


def subscription_id(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode()).hexdigest()[:32]


def label(sub: dict) -> str:
    """How a push recipient appears in the Activity log: a short id, nothing personal."""
    return f"app device {sub['subscription_id'][:6]}…"


def send(sub: dict, title: str, body: str, url: str = "/report") -> tuple[bool, str | None]:
    """Push one notification. (ok, error). A subscription the push service says is gone is deleted."""
    from pywebpush import WebPushException, webpush

    try:
        webpush(
            subscription_info={"endpoint": sub["endpoint"], "keys": {"p256dh": sub["p256dh"], "auth": sub["auth"]}},
            data=json.dumps({"title": title, "body": body[:900], "url": url, "tag": sub.get("tag", "paanialert")}),
            vapid_private_key=secret("vapid_private_key"),
            vapid_claims={"sub": os.environ.get("VAPID_SUBJECT", "mailto:alerts@paanialert.invalid")},
            ttl=TTL_SECONDS, timeout=10,
        )
        return True, None
    except WebPushException as exc:
        status = getattr(exc.response, "status_code", None)
        if status in GONE:
            db.delete_app_subscriber(sub["subscription_id"])
            log.info("push subscription gone (%s); removed", status)
            return False, f"subscription gone ({status}); removed"
        return False, f"push failed ({status}): {str(exc)[:150]}"
    except Exception as exc:   # network, bad keys: one failure mustn't stop the rest
        return False, f"push failed: {str(exc)[:150]}"
