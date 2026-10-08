import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from common.models import Cluster, Report, from_item, to_item  # noqa: E402


def test_report_round_trip():
    report = Report(
        report_id="r1",
        phone_hash="abc",
        created_at="2026-10-08T10:00:00Z",
        lat=22.7196,
        lon=75.8577,
        smell="sewage",
        sick_count=0,
    )
    item = to_item(report)
    assert item["lat"] == Decimal("22.7196")
    assert "photo_key" not in item          # empty values are dropped
    assert item["sick_count"] == 0          # zero is kept: nobody sick is real data
    assert from_item(Report, item) == report


def test_cluster_ignores_unknown_keys():
    item = {
        "cluster_id": "tsq4f2", "cells": ["tsq4f2"], "centre_lat": Decimal("22.72"),
        "centre_lon": Decimal("75.86"), "level": "alert", "report_count": 6,
        "distinct_phones": 5, "sick_households": 2, "severity": Decimal("23.5"),
        "ttl": 123,
    }
    cluster = from_item(Cluster, item)
    assert cluster.severity == 23.5
    assert cluster.status == "open"
