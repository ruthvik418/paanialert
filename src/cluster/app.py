"""Runs the cluster rule every 15 minutes and acts on changes. Owner: A.

- none → Watch → Alert: store it. On reaching Alert (once per cluster): WhatsApp
  advisory to subscribers in the area, and an SNS message to the ward engineer.
- Still open ESCALATE_AFTER_MIN minutes after the alert: SNS to the district
  health officer, once.
- No longer meeting the rule: status becomes expired.
- One outbreak keeps one cluster: a result that overlaps an open or acknowledged
  cluster continues it (same id, status and alert time), even when its strongest
  cell moves.
- Fixed or false alarm, but new complaints in its cells since: reopened, and
  alerted again like a new outbreak.
- Everything it does (level reached, each advisory, SNS, escalation, reopening)
  is written to the Activity table for the dashboard.
"""
from __future__ import annotations

import logging
import os
from dataclasses import replace
from datetime import timedelta

import boto3

from agent.messages import advisory_text, all_clear_text, official_text
from cluster.rule import _parse, evaluate
from common import db
from common.hashing import mask_number
from common.models import Cluster
from common.timeutil import hours_ago_iso, iso, now
from common.twilio_send import send_whatsapp

log = logging.getLogger()
log.setLevel(logging.INFO)

ESCALATE_AFTER_MIN = int(os.environ.get("ESCALATE_AFTER_MIN", "1440"))
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "")
LEVEL_RANK = {"none": 0, "watch": 1, "alert": 2}
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
    summary = {"reports": len(reports), "clusters": len(results), "alerted": 0, "escalated": 0, "expired": 0,
               "reopened": 0}
    matched: set[str] = set()

    for r in results:
        prev = match(r, existing, matched)
        if prev is None and r.cluster_id in matched:
            log.warning("cluster id %s already taken this run; skipped", r.cluster_id)
            continue
        matched.add(prev.cluster_id if prev else r.cluster_id)
        counts = dict(cells=r.cells, centre_lat=r.centre_lat, centre_lon=r.centre_lon, level=r.level,
                      report_count=r.report_count, distinct_phones=r.distinct_phones,
                      sick_households=r.sick_households, severity=r.severity, report_ids=r.report_ids)
        if prev:
            cluster = replace(prev, **counts)   # keeps id, status, first_seen, alert and escalation times
        else:
            cluster = Cluster(cluster_id=r.cluster_id, first_seen=r.first_seen, **counts)
        if prev and complaints_since_closed(prev, reports):
            cluster.status, cluster.status_at, cluster.reopened_at = "open", iso(current), iso(current)
            cluster.reopen_count += 1
            cluster.alert_at = cluster.escalated_at = None    # alert again like a new outbreak
            log.info("reopened %s after new complaints", cluster.cluster_id)
            db.log_activity("status", cluster.cluster_id, status="reopened", was=prev.status)
            summary["reopened"] += 1
        if LEVEL_RANK[cluster.level] > LEVEL_RANK[prev.level if prev else "none"]:
            db.log_activity("level", cluster.cluster_id, level=cluster.level, report_count=cluster.report_count,
                            distinct_phones=cluster.distinct_phones, sick_households=cluster.sick_households)
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
                db.log_activity("escalated", c.cluster_id, after_min=ESCALATE_AFTER_MIN)
                summary["escalated"] += 1
    return summary


def match(r, existing: list[Cluster], taken: set[str]) -> Cluster | None:
    """The stored cluster this result continues, so one outbreak keeps one id as its strongest cell moves.

    An open or acknowledged cluster whose cells overlap wins (the oldest if several).
    Otherwise a fixed or false-alarm one that overlaps (the same id first, then the
    most recently closed): it stays closed unless complaints_since_closed().
    """
    cells = set(r.cells)
    overlapping = [c for c in existing if c.cluster_id not in taken and cells.intersection(c.cells)]
    live = [c for c in overlapping if c.status in ("open", "acknowledged")]
    if live:
        return min(live, key=lambda c: (c.first_seen or "", c.cluster_id))
    # Clusters closed before status_at was stored only continue under their own id, as before,
    # so they can't swallow a new outbreak nearby that should alert.
    closed = [c for c in overlapping if c.status in ("fixed", "false_alarm")
              and (c.status_at or c.cluster_id == r.cluster_id)]
    if closed:
        return max(closed, key=lambda c: (c.cluster_id == r.cluster_id, c.status_at or "", c.cluster_id))
    return None


def complaints_since_closed(c: Cluster, reports) -> bool:
    """A fixed or false-alarm cluster with a report in its cells after its status was set.

    Clusters closed before status_at was kept have none, and are never reopened.
    """
    if c.status not in ("fixed", "false_alarm") or not c.status_at:
        return False
    cells = set(c.cells)
    return any(r.geohash6 in cells and r.created_at > c.status_at for r in reports)


def send_alerts(c: Cluster) -> None:
    notify("ward", c, f"PaaniAlert: bad-water alert ({c.report_count} reports)",
           official_text(c.cluster_id, c.level, c.report_count, c.distinct_phones, c.sick_households,
                         c.centre_lat, c.centre_lon, DASHBOARD_URL))
    message_subscribers(c, "advisory", lambda lang: advisory_text(c.report_count, c.sick_households, lang))


def send_all_clear(c: Cluster) -> int:
    """WhatsApp all-clear to subscribers in the area, in their language. Returns how many were sent."""
    return message_subscribers(c, "all_clear", all_clear_text)


def message_subscribers(c: Cluster, kind: str, text_for) -> int:
    """WhatsApp every subscriber in the cluster's cells, logging each one. Returns how many were sent."""
    sent = 0
    for sub in db.subscribers_in_cells(c.cells):
        to = mask_number(sub["phone"])
        try:
            sid = send_whatsapp(sub["phone"], text_for(sub.get("lang", "en")))
        except Exception as exc:
            # Usually Twilio's 24-hour window or missing credentials; one failure mustn't stop the rest.
            log.exception("%s failed for one subscriber in %s", kind, c.cluster_id)
            db.log_activity(kind, c.cluster_id, to=to, ok=False, error=str(exc)[:200])
            continue
        db.log_activity(kind, c.cluster_id, to=to, ok=True, sid=sid)
        sent += 1
    return sent


def escalate(c: Cluster) -> None:
    hours = ESCALATE_AFTER_MIN / 60
    notify("health", c, f"PaaniAlert ESCALATION: no action on bad-water alert after {hours:g} h",
           f"Nobody has acknowledged or closed this alert since {c.alert_at}.\n\n" +
           official_text(c.cluster_id, c.level, c.report_count, c.distinct_phones, c.sick_households,
                         c.centre_lat, c.centre_lon, DASHBOARD_URL))


def notify(to: str, c: Cluster, subject: str, message: str) -> None:
    """SNS to the ward engineer ("ward") or district health officer ("health"), logged as activity."""
    topic = os.environ.get("WARD_TOPIC_ARN" if to == "ward" else "HEALTH_TOPIC_ARN")
    try:
        published = publish(topic, subject, message)
    except Exception as exc:
        db.log_activity("sns", c.cluster_id, to=to, subject=subject[:100], ok=False, error=str(exc)[:200])
        raise
    db.log_activity("sns", c.cluster_id, to=to, subject=subject[:100], ok=bool(published),
                    error=None if published else "no SNS topic configured")


def publish(topic_arn: str | None, subject: str, message: str) -> bool:
    global _sns
    if not topic_arn:
        log.warning("no SNS topic configured; skipped: %s", subject)
        return False
    if _sns is None:
        _sns = boto3.client("sns")
    _sns.publish(TopicArn=topic_arn, Subject=subject[:100], Message=message)
    log.info("published to %s: %s", topic_arn.rsplit(":", 1)[-1], subject)
    return True


def active_notice_cells(now_iso: str) -> set[str]:
    return {n["geohash6"] for n in db.all_notices() if n.get("valid_until", "") >= now_iso}
