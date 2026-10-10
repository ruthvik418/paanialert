"""Runs the cluster rule every 15 minutes and acts on changes. Owner: A.

- none → Watch → Alert: store it. On reaching Alert (once per cluster): WhatsApp
  advisory to subscribers in the area, and an SNS message to the ward engineer.
- Still open ESCALATE_AFTER_MIN minutes after the alert: SNS to the district
  health officer, once.
- No longer meeting the rule: status becomes expired.
- One outbreak keeps one cluster: a result that overlaps an open or acknowledged
  cluster continues it (same id, status and alert time), even when its strongest
  cell moves.
"""
from __future__ import annotations

import logging
import os
from datetime import timedelta

import boto3

from agent.messages import advisory_text, official_text
from cluster.rule import _parse, evaluate
from common import db
from common.models import Cluster
from common.timeutil import hours_ago_iso, iso, now
from common.twilio_send import send_whatsapp

log = logging.getLogger()
log.setLevel(logging.INFO)

ESCALATE_AFTER_MIN = int(os.environ.get("ESCALATE_AFTER_MIN", "1440"))
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "")
_sns = None


def handler(event, context):
    summary = run()
    log.info("cluster check: %s", summary)
    return summary


def run() -> dict:
    current = now()
    reports = db.recent_reports(hours_ago_iso(48))
    notices = active_notice_cells(iso(current))
    results = evaluate(reports, current, notices)
    existing = db.all_clusters()
    summary = {"reports": len(reports), "clusters": len(results), "alerted": 0, "escalated": 0, "expired": 0}
    matched: set[str] = set()

    for r in results:
        prev = match(r, existing, matched)
        if prev is None and r.cluster_id in matched:
            log.warning("cluster id %s already taken this run; skipped", r.cluster_id)
            continue
        matched.add(prev.cluster_id if prev else r.cluster_id)
        cluster = Cluster(
            cluster_id=prev.cluster_id if prev else r.cluster_id, cells=r.cells,
            centre_lat=r.centre_lat, centre_lon=r.centre_lon,
            level=r.level, report_count=r.report_count, distinct_phones=r.distinct_phones,
            sick_households=r.sick_households, severity=r.severity,
            status=prev.status if prev else "open",
            first_seen=prev.first_seen if prev else r.first_seen,
            alert_at=prev.alert_at if prev else None,
            escalated_at=prev.escalated_at if prev else None,
        )
        if cluster.level == "alert" and cluster.alert_at is None and cluster.status == "open":
            cluster.alert_at = iso(current)
            send_alerts(cluster)
            summary["alerted"] += 1
        db.put_cluster(cluster)

    for c in existing:
        if c.cluster_id not in matched and c.status in ("open", "acknowledged"):
            c.status = "expired"
            db.put_cluster(c)
            summary["expired"] += 1

    for c in db.open_clusters():
        if c.status == "open" and c.alert_at and not c.escalated_at:
            if current - _parse(c.alert_at) >= timedelta(minutes=ESCALATE_AFTER_MIN):
                escalate(c)
                c.escalated_at = iso(current)
                db.put_cluster(c)
                summary["escalated"] += 1
    return summary


def match(r, existing: list[Cluster], taken: set[str]) -> Cluster | None:
    """The stored cluster this result continues, so one outbreak keeps one id as its strongest cell moves.

    An open or acknowledged cluster whose cells overlap wins (the oldest if several);
    otherwise a closed cluster with the same id carries on as before.
    """
    cells = set(r.cells)
    live = [c for c in existing if c.cluster_id not in taken
            and c.status in ("open", "acknowledged") and cells.intersection(c.cells)]
    if live:
        return min(live, key=lambda c: (c.first_seen or "", c.cluster_id))
    same = next((c for c in existing if c.cluster_id == r.cluster_id), None)
    if same and same.cluster_id not in taken and same.status != "expired":
        return same
    return None


def send_alerts(c: Cluster) -> None:
    publish(os.environ.get("WARD_TOPIC_ARN"), f"PaaniAlert: bad-water alert ({c.report_count} reports)",
            official_text(c.cluster_id, c.level, c.report_count, c.distinct_phones, c.sick_households,
                          c.centre_lat, c.centre_lon, DASHBOARD_URL))
    for sub in db.subscribers_in_cells(c.cells):
        try:
            send_whatsapp(sub["phone"], advisory_text(c.report_count, c.sick_households, sub.get("lang", "en")))
        except Exception:
            # Usually Twilio's 24-hour window or missing credentials; one failure mustn't stop the rest.
            log.exception("advisory failed for one subscriber in %s", c.cluster_id)


def escalate(c: Cluster) -> None:
    hours = ESCALATE_AFTER_MIN / 60
    publish(os.environ.get("HEALTH_TOPIC_ARN"),
            f"PaaniAlert ESCALATION: no action on bad-water alert after {hours:g} h",
            f"Nobody has acknowledged or closed this alert since {c.alert_at}.\n\n" +
            official_text(c.cluster_id, c.level, c.report_count, c.distinct_phones, c.sick_households,
                          c.centre_lat, c.centre_lon, DASHBOARD_URL))


def publish(topic_arn: str | None, subject: str, message: str) -> None:
    global _sns
    if not topic_arn:
        log.warning("no SNS topic configured; skipped: %s", subject)
        return
    if _sns is None:
        _sns = boto3.client("sns")
    _sns.publish(TopicArn=topic_arn, Subject=subject[:100], Message=message)
    log.info("published to %s: %s", topic_arn.rsplit(":", 1)[-1], subject)


def active_notice_cells(now_iso: str) -> set[str]:
    return {n["geohash6"] for n in db.all_notices() if n.get("valid_until", "") >= now_iso}
