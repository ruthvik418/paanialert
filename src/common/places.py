"""Turn a location pin into a short area name ("Rajwada, Indore") with Amazon Location.

Best effort: if the lookup fails, the report is saved without a name.
"""
from __future__ import annotations

import logging
import os

import boto3

from common.config import REGION

log = logging.getLogger(__name__)
_client = None


def area_name(lat: float, lon: float) -> str | None:
    if os.environ.get("AREA_LOOKUP", "on") == "off":
        return None
    global _client
    try:
        if _client is None:
            _client = boto3.client("geo-places", region_name=REGION)
        items = _client.reverse_geocode(QueryPosition=[lon, lat], MaxResults=1, Language="en")["ResultItems"]
        if not items:
            return None
        address = items[0].get("Address", {})
        parts = []
        for key in ("SubDistrict", "District", "Locality"):
            value = address.get(key)
            if isinstance(value, str) and value and value not in parts:
                parts.append(value)
        return ", ".join(parts[-2:]) or items[0].get("Title")
    except Exception:
        log.warning("area lookup failed", exc_info=True)
        return None
