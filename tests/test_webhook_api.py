import json
from urllib.parse import urlencode

import boto3
from twilio.request_validator import RequestValidator

from conftest import SECRETS

HOST = "abc123.execute-api.ap-south-1.amazonaws.com"


def _twilio_event(params, signature=None):
    url = f"https://{HOST}/whatsapp"
    sig = signature or RequestValidator(SECRETS["twilio_auth_token"]).compute_signature(url, params)
    return {
        "rawPath": "/whatsapp",
        "requestContext": {"domainName": HOST},
        "headers": {"x-twilio-signature": sig, "content-type": "application/x-www-form-urlencoded"},
        "body": urlencode(params),
        "isBase64Encoded": False,
    }


def test_webhook_queues_signed_message(aws):
    from webhook.app import handler

    params = {"From": "whatsapp:+919876543210", "Body": "paani peela hai", "MessageSid": "SM1", "NumMedia": "0"}
    resp = handler(_twilio_event(params), None)
    assert resp["statusCode"] == 200 and "<Message>" in resp["body"]

    import os
    msgs = boto3.client("sqs", region_name="ap-south-1").receive_message(QueueUrl=os.environ["INCOMING_QUEUE_URL"])
    body = json.loads(msgs["Messages"][0]["Body"])
    assert body["Body"] == "paani peela hai" and body["From"] == "whatsapp:+919876543210"


def test_webhook_rejects_bad_signature(aws):
    from webhook.app import handler

    resp = handler(_twilio_event({"From": "whatsapp:+1", "Body": "x"}, signature="bogus"), None)
    assert resp["statusCode"] == 403


def _api(route, key=SECRETS["dashboard_key"], **extra):
    event = {"routeKey": route, "headers": {"x-dashboard-key": key} if key else {}}
    event.update(extra)
    return event


def test_reports_need_the_key_and_hide_phone_hash(aws):
    from agent.reports import TurnContext, save_extracted
    from api.app import handler

    save_extracted(TurnContext(phone_hash="secret-hash", lang="en", lat=22.72, lon=75.86), {"smell": "sewage"},
                   extracted_by="keywords")

    assert handler(_api("GET /reports", key=None), None)["statusCode"] == 401
    assert handler(_api("GET /reports", key="wrong"), None)["statusCode"] == 401

    resp = handler(_api("GET /reports"), None)
    rows = json.loads(resp["body"])["reports"]
    assert resp["statusCode"] == 200 and len(rows) == 1
    assert rows[0]["smell"] == "sewage" and rows[0]["geohash6"]
    assert "phone_hash" not in rows[0]


def test_cluster_status_and_public_view(aws):
    from api.app import handler
    from common import db
    from common.models import Cluster

    db.put_cluster(Cluster(
        cluster_id="tsq4f2", cells=["tsq4f2"], centre_lat=22.71698, centre_lon=75.85510,
        level="alert", report_count=6, distinct_phones=5, sick_households=2, severity=23.5,
        first_seen="2026-10-08T10:00:00Z",
    ))
    public = json.loads(handler({"routeKey": "GET /public/clusters"}, None)["body"])["clusters"]
    assert public[0]["lat"] == 22.717 and "cells" not in public[0]

    ok = handler(_api("POST /clusters/{id}/status", pathParameters={"id": "tsq4f2"},
                      body=json.dumps({"status": "fixed"})), None)
    assert ok["statusCode"] == 200 and db.get_cluster("tsq4f2").status == "fixed"

    bad = handler(_api("POST /clusters/{id}/status", pathParameters={"id": "tsq4f2"},
                       body=json.dumps({"status": "deleted"})), None)
    assert bad["statusCode"] == 400
    missing = handler(_api("POST /clusters/{id}/status", pathParameters={"id": "nope"},
                           body=json.dumps({"status": "fixed"})), None)
    assert missing["statusCode"] == 404


def _alerted_cluster(cluster_id="tsq4f2", alert_at="2026-10-08T11:00:00Z"):
    from common import db
    from common.models import Cluster

    db.put_cluster(Cluster(
        cluster_id=cluster_id, cells=[cluster_id], centre_lat=22.71698, centre_lon=75.85510,
        level="alert", report_count=6, distinct_phones=5, sick_households=2, severity=23.5,
        first_seen="2026-10-08T10:00:00Z", alert_at=alert_at,
    ))


def _status(cluster_id, status):
    from api.app import handler

    return handler(_api("POST /clusters/{id}/status", pathParameters={"id": cluster_id},
                        body=json.dumps({"status": status})), None)


def test_fixed_sends_all_clear_in_each_language(aws, monkeypatch):
    import cluster.app as cluster_app
    from common import db

    sent = []

    def fake_send(to, body, media_url=None):
        if to.endswith("0002"):
            raise RuntimeError("outside the 24-hour window")
        sent.append((to, body))
        return "SM"

    monkeypatch.setattr(cluster_app, "send_whatsapp", fake_send)
    _alerted_cluster()
    db.put_subscriber("s1", "whatsapp:+919800000001", "tsq4f2", "hi")
    db.put_subscriber("s2", "whatsapp:+919800000002", "tsq4f2", "en")   # this one fails
    db.put_subscriber("s3", "whatsapp:+919800000003", "tsq4f2", "en")
    db.put_subscriber("s4", "whatsapp:+919800000004", "zzzzzz", "en")   # somewhere else

    resp = _status("tsq4f2", "fixed")
    assert json.loads(resp["body"])["all_clear_sent"] == 2
    by_phone = dict(sent)
    assert set(by_phone) == {"whatsapp:+919800000001", "whatsapp:+919800000003"}
    assert "ठीक" in by_phone["whatsapp:+919800000001"] and "fixed" in by_phone["whatsapp:+919800000003"]

    _status("tsq4f2", "fixed")                                         # marking it fixed again
    assert len(sent) == 2


def test_no_all_clear_unless_fixed_and_warned(aws, monkeypatch):
    import cluster.app as cluster_app
    from common import db

    sent = []
    monkeypatch.setattr(cluster_app, "send_whatsapp", lambda to, body, media_url=None: sent.append(to))
    _alerted_cluster("aaaaaa")
    _alerted_cluster("bbbbbb")
    _alerted_cluster("cccccc", alert_at=None)                          # only reached Watch: nobody warned
    for cell in ("aaaaaa", "bbbbbb", "cccccc"):
        db.put_subscriber(f"s-{cell}", f"whatsapp:+91980000{cell[:4]}", cell, "en")

    _status("aaaaaa", "acknowledged")
    _status("bbbbbb", "false_alarm")
    _status("cccccc", "fixed")
    assert sent == []


def _saved_report(**ctx):
    from agent.reports import TurnContext, save_extracted
    from common import db

    report = save_extracted(TurnContext(phone_hash="hash-1", lang="en", lat=22.7196, lon=75.8577,
                                        text="paani mein badboo", profile_name="Ravi Kumar",
                                        phone_masked="+91 98•••••210", **ctx), {"smell": "sewage"},
                            extracted_by="keywords")
    db.put_contact("hash-1", "+919876543210")
    return report


def test_full_number_only_from_the_audited_contact_route(aws):
    import boto3

    import cluster.app as cluster_app
    from api.app import handler

    report = _saved_report()
    cluster_app.run()

    rows = json.loads(handler(_api("GET /reports"), None)["body"])["reports"]
    assert rows[0]["profile_name"] == "Ravi Kumar" and rows[0]["text"] == "paani mein badboo"
    assert rows[0]["phone_masked"] == "+91 98•••••210"
    for route in ("GET /reports", "GET /clusters", "GET /public/clusters"):
        assert "9876543210" not in handler(_api(route), None)["body"]

    path = {"pathParameters": {"id": report.report_id}}
    assert handler(_api("POST /reports/{id}/contact", key=None, **path), None)["statusCode"] == 401
    audit = boto3.resource("dynamodb", region_name="ap-south-1").Table("AuditLog")
    assert audit.scan()["Items"] == []

    event = _api("POST /reports/{id}/contact", **path,
                 requestContext={"http": {"sourceIp": "203.0.113.7", "userAgent": "Firefox"}})
    resp = handler(event, None)
    assert resp["statusCode"] == 200 and json.loads(resp["body"])["phone"] == "+919876543210"
    rows = audit.scan()["Items"]
    assert len(rows) == 1 and rows[0]["report_id"] == report.report_id
    assert rows[0]["ip"] == "203.0.113.7" and rows[0]["user_agent"] == "Firefox" and rows[0]["at"]

    missing = handler(_api("POST /reports/{id}/contact", pathParameters={"id": "nope"}), None)
    assert missing["statusCode"] == 404


def test_photo_link_lasts_five_minutes(aws):
    from api.app import handler

    with_photo = _saved_report(photo_key="media/SM1.jpg")
    without = _saved_report()
    assert handler(_api("GET /reports/{id}/photo", key=None,
                        pathParameters={"id": with_photo.report_id}), None)["statusCode"] == 401
    body = json.loads(handler(_api("GET /reports/{id}/photo", pathParameters={"id": with_photo.report_id}), None)["body"])
    assert "media/SM1.jpg" in body["url"] and "X-Amz-Expires=300" in body["url"] and body["expires_in"] == 300
    assert handler(_api("GET /reports/{id}/photo", pathParameters={"id": without.report_id}), None)["statusCode"] == 404


def test_status_changes_and_all_clear_show_in_activity(aws, monkeypatch):
    import cluster.app as cluster_app
    from api.app import handler
    from common import db

    monkeypatch.setattr(cluster_app, "send_whatsapp", lambda to, body, media_url=None: "SMclear")
    _alerted_cluster()
    db.put_subscriber("s1", "whatsapp:+919800000001", "tsq4f2", "en")
    _status("tsq4f2", "acknowledged")
    _status("tsq4f2", "fixed")

    assert handler(_api("GET /activity", key=None), None)["statusCode"] == 401
    rows = json.loads(handler(_api("GET /activity"), None)["body"])["activity"]
    assert [r["at"] for r in rows] == sorted((r["at"] for r in rows), reverse=True)
    statuses = [r["status"] for r in rows if r["kind"] == "status"]
    assert sorted(statuses) == ["acknowledged", "fixed"]
    clear = [r for r in rows if r["kind"] == "all_clear"]
    assert len(clear) == 1 and clear[0]["ok"] is True and clear[0]["to"] == "+91 98•••••001"

    later = handler(_api("GET /activity", queryStringParameters={"since": "2999-01-01T00:00:00Z"}), None)
    assert json.loads(later["body"])["activity"] == []
