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

    save_extracted(TurnContext(phone_hash="secret-hash", lang="en", lat=22.72, lon=75.86), {"smell": "sewage"})

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
