"""Phone numbers are stored as keyed hashes, so a leaked table can't be reversed
by trying every 10-digit number. The key lives in SSM (/paanialert/hmac_secret)."""
from __future__ import annotations

import hashlib
import hmac

from common.config import secret


def normalise_number(raw: str) -> str:
    """'whatsapp:+91 98765 43210' -> '+919876543210'."""
    number = raw.strip()
    if number.lower().startswith("whatsapp:"):
        number = number[len("whatsapp:"):]
    return "".join(ch for ch in number if ch.isdigit() or ch == "+")


def mask_number(raw: str) -> str:
    """'whatsapp:+919876543210' -> '+91 98•••••210', for showing who reported without the number."""
    number = normalise_number(raw)
    if number.startswith("+91") and len(number) == 13:
        return f"+91 {number[3:5]}•••••{number[-3:]}"
    return f"{number[:3]}•••••{number[-3:]}" if len(number) > 6 else "•••"


def phone_hash(raw: str, key: str | None = None) -> str:
    key = secret("hmac_secret") if key is None else key
    return hmac.new(key.encode(), normalise_number(raw).encode(), hashlib.sha256).hexdigest()
