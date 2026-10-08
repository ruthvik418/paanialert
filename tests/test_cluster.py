from datetime import datetime, timedelta, timezone

import pytest

from cluster.rule import evaluate, severity
from common.geo import geohash6
from common.models import Report

NOW = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)
INDORE = (22.7196, 75.8577)


def report(i, phone=None, hours_ago=1, sick=None, lat=INDORE[0], lon=INDORE[1], **kw):
    created = (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
    fields = dict(smell="sewage", colour="yellow")
    fields.update(kw)
    return Report(report_id=f"r{i}", phone_hash=phone or f"p{i}", created_at=created,
                  lat=lat, lon=lon, geohash6=geohash6(lat, lon), sick_count=sick, **fields)


def test_severity_weights():
    assert severity(report(1)) == 5                     # sewage 3 + colour 2
    assert severity(report(2, sick=1, photo_key="k")) == 10
    assert severity(report(3, clears_quickly=True)) == 2.5


def test_four_phones_is_watch_five_is_alert():
    assert evaluate([report(i) for i in range(4)], NOW)[0].level == "watch"
    result = evaluate([report(i) for i in range(5)], NOW)
    assert len(result) == 1 and result[0].level == "alert" and result[0].distinct_phones == 5


def test_two_sick_households_is_alert():
    result = evaluate([report(1, sick=1), report(2, sick=2)], NOW)
    assert result[0].level == "alert" and result[0].sick_households == 2


def test_one_phone_five_times_is_nothing():
    assert evaluate([report(i, phone="same", colour="unknown", smell="other") for i in range(5)], NOW) == []


def test_old_reports_dont_count():
    assert evaluate([report(i, hours_ago=72) for i in range(6)], NOW) == []


def test_neighbouring_cells_join_one_cluster():
    # ~700 m east is the next geohash-6 cell, but still one neighbourhood and one cluster.
    reports = [report(i) for i in range(3)] + [report(10 + i, lon=INDORE[1] + 0.0065) for i in range(2)]
    result = evaluate(reports, NOW)
    assert len(result) == 1 and result[0].distinct_phones == 5


def test_far_away_reports_stay_separate():
    delhi = [report(20 + i, lat=28.6139, lon=77.2090) for i in range(5)]
    result = evaluate([report(i) for i in range(5)] + delhi, NOW)
    assert len(result) == 2


def test_notice_caps_at_watch():
    cell = geohash6(*INDORE)
    assert evaluate([report(i) for i in range(6)], NOW, notice_cells={cell})[0].level == "watch"


@pytest.fixture
def check(aws, monkeypatch):
    import cluster.app as app

    sent, published = [], []
    monkeypatch.setattr(app, "send_whatsapp", lambda to, body, media_url=None: sent.append((to, body)))
    monkeypatch.setattr(app, "publish", lambda arn, subject, message: published.append(subject))
    app.sent, app.published = sent, published
    return app


def test_check_alerts_once_and_escalates(check, monkeypatch):
    from common import db
    from common.timeutil import iso, now

    for i in range(5):
        r = report(i)
        r.created_at = iso(now() - timedelta(hours=1))
        db.put_report(r)
    db.put_subscriber("sub1", "whatsapp:+919800000001", geohash6(*INDORE), "en")

    first = check.run()
    assert first["alerted"] == 1 and len(check.sent) == 1 and "boil" in check.sent[0][1].lower()
    assert check.run()["alerted"] == 0 and len(check.sent) == 1     # never twice

    monkeypatch.setattr(check, "ESCALATE_AFTER_MIN", 0)
    assert check.run()["escalated"] == 1
    assert any("ESCALATION" in s for s in check.published)


def test_closed_cluster_is_not_escalated(check, monkeypatch):
    from common import db
    from common.timeutil import iso, now

    for i in range(5):
        r = report(i)
        r.created_at = iso(now() - timedelta(hours=1))
        db.put_report(r)
    check.run()
    cid = db.all_clusters()[0].cluster_id
    db.update_cluster_status(cid, "fixed", iso(now()))
    monkeypatch.setattr(check, "ESCALATE_AFTER_MIN", 0)
    assert check.run()["escalated"] == 0
