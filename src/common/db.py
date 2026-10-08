"""DynamoDB helpers. Table names come from environment variables set in template.yaml."""
from __future__ import annotations

import json
import time
from typing import Any

import boto3
from boto3.dynamodb.conditions import Attr, Key

from common.config import REGION, table
from common.models import Cluster, Report, from_item, to_item

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
