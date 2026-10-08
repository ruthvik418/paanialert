"""Insert test reports near a point, so you can test clusters without five real phones. Owner: A.

    python scripts/fake_reports.py --near 22.7196,75.8577 --phones 5 --sick 1 --check
    python scripts/fake_reports.py --clean          # delete every fake report and the clusters they made

Fake reports have ids starting with "fake-" and made-up phone hashes, so no
real person is ever messaged because of them. --check runs the cluster check
right away instead of waiting up to 15 minutes.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import uuid
from decimal import Decimal
from pathlib import Path

import boto3
from boto3.dynamodb.conditions import Attr

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from common.geo import geohash6  # noqa: E402
from common.timeutil import now_iso  # noqa: E402

PROFILE = os.environ.get("AWS_PROFILE", "paani")
REGION = os.environ.get("AWS_REGION", "ap-south-1")
STACK = "paanialert"


def resource_id(session, logical_id: str) -> str:
    cfn = session.client("cloudformation")
    return cfn.describe_stack_resource(StackName=STACK, LogicalResourceId=logical_id)["StackResourceDetail"]["PhysicalResourceId"]


def jitter(lat: float, lon: float, metres: float) -> tuple[float, float]:
    angle, dist = random.uniform(0, 2 * math.pi), random.uniform(0, metres)
    return (lat + dist * math.cos(angle) / 111_320,
            lon + dist * math.sin(angle) / (111_320 * math.cos(math.radians(lat))))


def add(session, lat: float, lon: float, phones: int, sick: int) -> None:
    table = session.resource("dynamodb").Table(resource_id(session, "ReportsTable"))
    for i in range(phones):
        rlat, rlon = jitter(lat, lon, 300)
        item = {
            "report_id": f"fake-{uuid.uuid4().hex[:12]}",
            "phone_hash": f"fake-phone-{uuid.uuid4().hex[:8]}",
            "created_at": now_iso(),
            "lat": Decimal(str(round(rlat, 6))), "lon": Decimal(str(round(rlon, 6))),
            "geohash6": geohash6(rlat, rlon),
            "smell": random.choice(["sewage", "sewage", "other"]),
            "colour": random.choice(["yellow", "brown", "cloudy"]),
            "taste": "unknown",
            "since_days": random.randint(1, 3),
            "sick_count": 1 if i < sick else 0,
            "symptoms": ["diarrhoea"] if i < sick else [],
            "lang": "hinglish",
            "source": "pipe",
            "landmark": "TEST REPORT",
        }
        table.put_item(Item=item)
    print(f"Added {phones} fake reports ({sick} with illness) within 300 m of {lat}, {lon}")


def clean(session) -> None:
    reports = session.resource("dynamodb").Table(resource_id(session, "ReportsTable"))
    clusters = session.resource("dynamodb").Table(resource_id(session, "ClustersTable"))
    fake_cells, removed = set(), 0
    scan = {"FilterExpression": Attr("report_id").begins_with("fake-")}
    while True:
        page = reports.scan(**scan)
        for item in page["Items"]:
            fake_cells.add(item.get("geohash6"))
            reports.delete_item(Key={"report_id": item["report_id"]})
            removed += 1
        if "LastEvaluatedKey" not in page:
            break
        scan["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    gone = 0
    for item in clusters.scan()["Items"]:
        if fake_cells.intersection(item.get("cells", [])):
            clusters.delete_item(Key={"cluster_id": item["cluster_id"]})
            gone += 1
    print(f"Deleted {removed} fake reports and {gone} clusters they formed")


def run_check(session) -> None:
    out = session.client("lambda").invoke(FunctionName=resource_id(session, "ClusterFunction"))
    print("Cluster check:", json.loads(out["Payload"].read()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--near", help="lat,lon")
    parser.add_argument("--phones", type=int, default=5)
    parser.add_argument("--sick", type=int, default=0)
    parser.add_argument("--check", action="store_true", help="run the cluster check now")
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    if args.clean:
        clean(session)
    if args.near:
        lat, lon = (float(x) for x in args.near.split(","))
        add(session, lat, lon, args.phones, args.sick)
    if args.check:
        run_check(session)


if __name__ == "__main__":
    main()
