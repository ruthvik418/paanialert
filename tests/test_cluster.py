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


def _put_recent(reports):
    from common import db
    from common.timeutil import iso, now

    for r in reports:
        r.created_at = iso(now() - timedelta(hours=1))
        db.put_report(r)


def _growing_outbreak(check):
    """5 phones in one cell, then more one and two cells east, so the strongest cell moves east."""
    from common import db
    from common.timeutil import now

    _put_recent([report(i) for i in range(5)])
    db.put_subscriber("sub1", "whatsapp:+919800000001", geohash6(*INDORE), "en")
    check.run()
    first = db.all_clusters()[0]
    _put_recent([report(10 + i, lon=INDORE[1] + 0.011) for i in range(3)]
                + [report(20 + i, lon=INDORE[1] + 0.022) for i in range(4)])
    moved = evaluate(db.recent_reports("2000-01-01T00:00:00Z"), now())[0]
    assert moved.cluster_id != first.cluster_id     # the setup really moves the strongest cell
    return first


def test_moving_outbreak_alerts_once(check):
    from common import db

    first = _growing_outbreak(check)
    check.run()
    live = [c for c in db.all_clusters() if c.status != "expired"]
    assert [c.cluster_id for c in live] == [first.cluster_id]
    assert live[0].distinct_phones == 12 and live[0].alert_at == first.alert_at
    assert len(check.sent) == 1 and len(check.published) == 1


def test_acknowledged_cluster_stays_acknowledged_as_it_grows(check):
    from common import db
    from common.timeutil import now_iso

    first = _growing_outbreak(check)
    db.update_cluster_status(first.cluster_id, "acknowledged", now_iso())
    summary = check.run()
    c = db.get_cluster(first.cluster_id)
    assert c.status == "acknowledged" and c.distinct_phones == 12
    assert summary["expired"] == 0 and len(check.sent) == 1


@pytest.mark.parametrize("closed_as", ["fixed", "false_alarm"])
def test_new_complaints_after_a_fix_reopen_and_alert_again(check, closed_as):
    from common import db
    from common.timeutil import iso, now

    _put_recent([report(i) for i in range(5)])
    db.put_subscriber("sub1", "whatsapp:+919800000001", geohash6(*INDORE), "en")
    check.run()
    cid = db.all_clusters()[0].cluster_id
    db.update_cluster_status(cid, closed_as, iso(now() - timedelta(minutes=30)))

    assert check.run()["reopened"] == 0 and db.get_cluster(cid).status == closed_as   # nothing new yet

    late = report(50)
    late.created_at = iso(now() - timedelta(minutes=10))
    db.put_report(late)
    summary = check.run()
    c = db.get_cluster(cid)
    assert summary["reopened"] == 1 and c.status == "open" and c.reopen_count == 1 and c.reopened_at
    assert len(check.sent) == 2 and c.alert_at                                          # alerted again
    assert check.run()["reopened"] == 0                                                 # only once


def test_cluster_closed_without_a_status_time_stays_closed(check):
    from common import db
    from common.models import Cluster
    from common.timeutil import iso, now

    _put_recent([report(i) for i in range(5)])
    result = evaluate(db.recent_reports("2000-01-01T00:00:00Z"), now())[0]
    db.put_cluster(Cluster(cluster_id=result.cluster_id, cells=result.cells, centre_lat=0, centre_lon=0,
                           level="alert", report_count=5, distinct_phones=5, sick_households=0, severity=25,
                           status="fixed", first_seen=result.first_seen, alert_at=iso(now())))
    assert check.run()["reopened"] == 0 and db.get_cluster(result.cluster_id).status == "fixed"
    assert check.sent == []
