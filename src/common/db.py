"""DynamoDB helpers. Table names come from environment variables set in template.yaml."""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr, Key

from common.config import REGION, table
from common.models import Advisory, Cluster, Report, _from_dynamo, _to_dynamo, from_item, to_item
from common.timeutil import now_iso

log = logging.getLogger(__name__)
_resource = None


def _table(name: str):
    global _resource
    if _resource is None:
        _resource = boto3.resource("dynamodb", region_name=REGION)
    return _resource.Table(table(name))


def _query_all(tbl, **kwargs) -> list[dict[str, Any]]:
    items = []
    while True:
        resp = tbl.query(**kwargs)
        items += resp["Items"]
        if "LastEvaluatedKey" not in resp:
            return items
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def _scan_all(tbl, **kwargs) -> list[dict[str, Any]]:
    items = []
    while True:
        resp = tbl.scan(**kwargs)
        items += resp["Items"]
        if "LastEvaluatedKey" not in resp:
            return items
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


# Reports

def put_report(report: Report) -> None:
    _table("reports").put_item(Item=to_item(report))


def get_report(report_id: str) -> Report | None:
    item = _table("reports").get_item(Key={"report_id": report_id}).get("Item")
    return from_item(Report, item) if item else None


def update_report_status(report_id: str, status: str, note: str | None, at_iso: str) -> None:
    """Officials' status for one report; raises ConditionalCheckFailed if there's no such report."""
    _table("reports").update_item(
        Key={"report_id": report_id},
        UpdateExpression="SET #s = :s, status_at = :t" + (", status_note = :n" if note else " REMOVE status_note"),
        ConditionExpression="attribute_exists(report_id)",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": status, ":t": at_iso, **({":n": note} if note else {})},
    )


def reports_in_cells(cells: list[str], since_iso: str) -> list[Report]:
    tbl = _table("reports")
    out: list[Report] = []
    for cell in cells:
        items = _query_all(
            tbl,
            IndexName="geo-time",
            KeyConditionExpression=Key("geohash6").eq(cell) & Key("created_at").gte(since_iso),
        )
        out += [from_item(Report, i) for i in items]
    return out


def recent_reports(since_iso: str) -> list[Report]:
    """Every report since a time. A scan is fine at hackathon scale."""
    items = _scan_all(_table("reports"), FilterExpression=Attr("created_at").gte(since_iso))
    return sorted((from_item(Report, i) for i in items), key=lambda r: r.created_at, reverse=True)


# Clusters

def get_cluster(cluster_id: str) -> Cluster | None:
    item = _table("clusters").get_item(Key={"cluster_id": cluster_id}).get("Item")
    return from_item(Cluster, item) if item else None


def put_cluster(cluster: Cluster) -> None:
    _table("clusters").put_item(Item=to_item(cluster))


def all_clusters() -> list[Cluster]:
    return [from_item(Cluster, i) for i in _scan_all(_table("clusters"))]


def open_clusters() -> list[Cluster]:
    return [c for c in all_clusters() if c.status in ("open", "acknowledged")]


def update_cluster_status(cluster_id: str, status: str, at_iso: str) -> None:
    _table("clusters").update_item(
        Key={"cluster_id": cluster_id},
        UpdateExpression="SET #s = :s, status_at = :t",
        ConditionExpression="attribute_exists(cluster_id)",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={":s": status, ":t": at_iso},
    )


# Activity: one row for everything PaaniAlert does about a cluster, shown on the dashboard.
# kinds: level, advisory, all_clear, sns, escalated, status

def log_activity(kind: str, cluster_id: str | None = None, **detail: Any) -> None:
    """Never raises: a failed log row must not stop an alert from going out."""
    item = {"activity_id": uuid.uuid4().hex, "at": now_iso(), "kind": kind,
            **{k: v for k, v in detail.items() if v is not None}}
    if cluster_id:
        item["cluster_id"] = cluster_id
    try:
        _table("activity").put_item(Item=_to_dynamo(item))
    except Exception:
        log.exception("could not log %s activity for %s", kind, cluster_id)


def recent_activity(since_iso: str) -> list[dict[str, Any]]:
    """Newest first. A scan is fine at hackathon scale."""
    items = _scan_all(_table("activity"), FilterExpression=Attr("at").gte(since_iso))
    rows = [_from_dynamo(i) for i in items]
    return sorted(rows, key=lambda r: (r["at"], r["activity_id"]), reverse=True)


# Maintenance notices: {"geohash6", "text", "valid_until"}

def all_notices() -> list[dict[str, Any]]:
    return _scan_all(_table("notices"))


def put_notice(geohash6: str, text: str, valid_until_iso: str) -> None:
    _table("notices").put_item(Item={"geohash6": geohash6, "text": text, "valid_until": valid_until_iso})


# Subscribers (the one table that keeps a real number, because alerts need it)

def put_subscriber(phone_hash: str, phone: str, geohash6: str, lang: str) -> None:
    _table("subscribers").put_item(
        Item={"phone_hash": phone_hash, "phone": phone, "geohash6": geohash6, "lang": lang}
    )


def get_subscriber(phone_hash: str) -> dict[str, Any] | None:
    return _table("subscribers").get_item(Key={"phone_hash": phone_hash}).get("Item")


def delete_subscriber(phone_hash: str) -> None:
    _table("subscribers").delete_item(Key={"phone_hash": phone_hash})


def update_subscriber_lang(phone_hash: str, lang: str) -> None:
    """Keep alerts in the language the person chose, if they're subscribed."""
    try:
        _table("subscribers").update_item(
            Key={"phone_hash": phone_hash},
            UpdateExpression="SET lang = :l",
            ConditionExpression="attribute_exists(phone_hash)",
            ExpressionAttributeValues={":l": lang},
        )
    except Exception as exc:
        if "ConditionalCheckFailed" not in str(exc):
            raise


# Contacts: the full number behind a phone hash, for officials to call a reporter back.
# Read only through POST /reports/{id}/contact, which writes an audit row first.

def put_contact(phone_hash: str, phone: str) -> None:
    _table("contacts").put_item(Item={"phone_hash": phone_hash, "phone": phone})


def get_contact(phone_hash: str) -> str | None:
    item = _table("contacts").get_item(Key={"phone_hash": phone_hash}).get("Item")
    return item.get("phone") if item else None


def put_audit(report_id: str, at_iso: str, ip: str, user_agent: str) -> None:
    """Who saw a reporter's number: {audit_id, report_id, at, ip, user_agent}."""
    _table("audit").put_item(Item={
        "audit_id": uuid.uuid4().hex, "report_id": report_id, "at": at_iso,
        "ip": ip or "unknown", "user_agent": (user_agent or "unknown")[:300],
    })


# Language preference per phone. Kept apart from Sessions, which expire after 24 hours.

def get_language(phone_hash: str) -> str | None:
    item = _table("preferences").get_item(Key={"phone_hash": phone_hash}).get("Item")
    return item.get("lang") if item else None


def set_language(phone_hash: str, lang: str) -> None:
    _table("preferences").put_item(Item={"phone_hash": phone_hash, "lang": lang})


def subscribers_in_cells(cells: list[str]) -> list[dict[str, Any]]:
    tbl = _table("subscribers")
    out: list[dict[str, Any]] = []
    for cell in cells:
        out += _query_all(tbl, IndexName="by-cell", KeyConditionExpression=Key("geohash6").eq(cell))
    return out


# Processed messages: Twilio retries webhooks and SQS can deliver twice, so each MessageSid is handled once

def claim_message(message_sid: str) -> bool:
    """True the first time a MessageSid is seen. The row expires after 2 days."""
    try:
        _table("processed").put_item(
            Item={"message_sid": message_sid, "expires_at": int(time.time()) + 2 * 24 * 3600},
            ConditionExpression="attribute_not_exists(message_sid)",
        )
        return True
    except Exception as exc:
        if "ConditionalCheckFailed" in str(exc):
            return False
        raise


def release_message(message_sid: str) -> None:
    """Undo a claim when handling failed, so the SQS retry runs."""
    _table("processed").delete_item(Key={"message_sid": message_sid})


# Sessions: short conversation memory per phone, expires after 24 hours

def get_session(phone_hash: str) -> dict[str, Any]:
    """{"turns": [{"role", "text"}], "last_report_id": str|None, "pending_location": [lat, lon]|None}"""
    item = _table("sessions").get_item(Key={"phone_hash": phone_hash}).get("Item") or {}
    return json.loads(item.get("state_json", "{}"))


def put_session(phone_hash: str, state: dict[str, Any]) -> None:
    state = dict(state, turns=state.get("turns", [])[-10:])
    _table("sessions").put_item(Item={
        "phone_hash": phone_hash,
        "state_json": json.dumps(state, ensure_ascii=False),
        "expires_at": int(time.time()) + 24 * 3600,
    })


# App quota: how many reports each web-app device sent today (UTC), so one device can't flood the map

def take_app_quota(device_hash: str, day: str, limit: int) -> bool:
    """Count one report for this device today; False once it already has `limit`. Rows expire after 2 days."""
    try:
        _table("app_quota").update_item(
            Key={"quota_id": f"{device_hash}#{day}"},
            UpdateExpression="ADD sent :one SET expires_at = :exp",
            ConditionExpression="attribute_not_exists(sent) OR sent < :limit",
            ExpressionAttributeValues={":one": 1, ":limit": limit, ":exp": int(time.time()) + 2 * 24 * 3600},
        )
        return True
    except Exception as exc:
        if "ConditionalCheckFailed" in str(exc):
            return False
        raise


# Advisories: warnings officials issue for an area (boil water / don't use), until lifted

def put_advisory(advisory: Advisory) -> None:
    _table("advisories").put_item(Item=to_item(advisory))


def get_advisory(advisory_id: str) -> Advisory | None:
    item = _table("advisories").get_item(Key={"advisory_id": advisory_id}).get("Item")
    return from_item(Advisory, item) if item else None


def all_advisories() -> list[Advisory]:
    """Newest first. A scan is fine at hackathon scale."""
    return sorted((from_item(Advisory, i) for i in _scan_all(_table("advisories"))),
                  key=lambda a: a.created_at, reverse=True)


def lift_advisory(advisory_id: str, at_iso: str) -> bool:
    """Mark an active advisory lifted. False if it's missing or already lifted."""
    try:
        _table("advisories").update_item(
            Key={"advisory_id": advisory_id},
            UpdateExpression="SET #s = :lifted, lifted_at = :t",
            ConditionExpression="#s = :active",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":lifted": "lifted", ":active": "active", ":t": at_iso},
        )
        return True
    except Exception as exc:
        if "ConditionalCheckFailed" in str(exc):
            return False
        raise
