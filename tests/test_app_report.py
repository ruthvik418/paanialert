"""The web report app's routes (POST /app/report, /app/photo-url) against fake AWS, model replaced."""
import json
import uuid

import pytest

DEVICE = "0b6f4c1e-8a2d-4c4e-9a51-2f0d3c9b7e10"
INDORE = {"lat": 22.7196, "lon": 75.8577}
COMPLAINT = "Nal ka paani peela aa raha hai, badboo hai, 2 din se"


@pytest.fixture
def app(aws, monkeypatch):
    import api.app_report as app_report
    import worker.app as w
    from agent.runner import AgentUnavailable

    def no_whatsapp(*args, **kwargs):
        raise AssertionError("an app report must not send WhatsApp")

    def no_bedrock(*args, **kwargs):
        raise AgentUnavailable()

    monkeypatch.setattr(w, "send_whatsapp", no_whatsapp)
    monkeypatch.setattr(w, "agent_reply", no_bedrock)   # keyword extraction, no network
    app_report._s3 = None
    return app_report


def call(app, route, body):
    raw = body if isinstance(body, str) else json.dumps(body)
    resp = app.handler({"routeKey": f"POST {route}", "body": raw}, None)
    return resp["statusCode"], json.loads(resp["body"])


def report_body(**changes):
    return {"device_id": DEVICE, "text": COMPLAINT, "lang": "en", **INDORE, **changes}


def test_app_report_is_saved_with_channel_app_and_location(app):
    from common import db

    status, body = call(app, "/app/report", report_body())
    assert status == 200 and body["saved"] is True and "saved" in body["reply"]
    report = db.get_report(body["report_id"])
    assert report.channel == "app" and report.extracted_by == "keywords"
    assert (report.lat, report.lon) == (22.7196, 75.8577) and report.geohash6
    assert report.colour == "yellow" and report.phone_masked is None
    assert "📍" not in body["reply"] and "🔔" not in body["reply"]   # has a location; no WhatsApp alerts offer
    assert db.get_contact(report.phone_hash) is None


def test_whatsapp_reports_keep_channel_whatsapp(app, monkeypatch):
    import worker.app as w
    from common import db
    from common.hashing import phone_hash

    monkeypatch.setattr(w, "send_whatsapp", lambda to, body, media_url=None: "SM")
    w.handle({"From": "whatsapp:+919876543210", "Body": COMPLAINT})
    state = db.get_session(phone_hash("whatsapp:+919876543210"))
    assert db.get_report(state["last_report_id"]).channel == "whatsapp"


def test_greeting_is_answered_but_not_saved(app):
    status, body = call(app, "/app/report", report_body(text="hello"))
    assert status == 200 and body == {"reply": body["reply"], "report_id": None, "saved": False}
    assert "PaaniAlert" in body["reply"]


def test_eleventh_report_of_the_day_is_refused(app):
    for _ in range(10):
        assert call(app, "/app/report", report_body())[0] == 200
    status, body = call(app, "/app/report", report_body())
    assert status == 429 and "10 reports" in body["error"]
    other = str(uuid.uuid4())
    assert call(app, "/app/report", report_body(device_id=other))[0] == 200   # per device


def test_retried_request_is_saved_once(app):
    from common import db

    body = report_body(request_id=str(uuid.uuid4()))
    assert call(app, "/app/report", body)[1]["saved"] is True
    assert call(app, "/app/report", body)[1]["saved"] is False
    assert len(db.recent_reports("2000-01-01T00:00:00Z")) == 1


@pytest.mark.parametrize("changes", [
    {"device_id": "not-a-uuid"},
    {"device_id": None},
    {"text": "x" * 1001},
    {"text": 42},
    {"text": ""},                                   # no text and no photo
    {"lat": 51.5, "lon": -0.12},                    # London
    {"lat": "22.7"},
    {"lon": None},
    {"lang": "fr"},
    {"photo_key": "media/someone-else.jpg"},
    {"photo_key": f"app-uploads/{uuid.uuid4()}/{'a' * 32}.jpg"},   # another device's folder
    {"request_id": "abc"},
])
def test_bad_input_is_a_400(app, changes):
    status, body = call(app, "/app/report", report_body(**changes))
    assert status == 400 and body["error"]


def test_body_that_is_not_json_is_a_400(app):
    assert call(app, "/app/report", "{not json")[0] == 400
    assert call(app, "/app/report", "[1, 2]")[0] == 400


def test_photo_url_then_report_with_the_photo(app):
    import boto3

    from common import db

    status, body = call(app, "/app/photo-url", {"device_id": DEVICE, "content_type": "image/jpeg", "size": 2048})
    assert status == 200 and body["photo_key"].startswith(f"app-uploads/{DEVICE}/") and body["expires_in"] == 300
    assert "X-Amz-Signature" in body["url"] and "content-length" in body["url"]
    boto3.client("s3", region_name="ap-south-1").put_object(
        Bucket="media-test", Key=body["photo_key"], Body=b"x" * 2048, ContentType="image/jpeg")

    status, sent = call(app, "/app/report", report_body(photo_key=body["photo_key"]))
    assert status == 200 and db.get_report(sent["report_id"]).photo_key == body["photo_key"]


def test_photo_that_was_never_uploaded_is_a_400(app):
    _, body = call(app, "/app/photo-url", {"device_id": DEVICE, "content_type": "image/png", "size": 10})
    status, sent = call(app, "/app/report", report_body(photo_key=body["photo_key"]))
    assert status == 400 and "wasn't uploaded" in sent["error"]


@pytest.mark.parametrize("changes", [
    {"content_type": "image/gif"},
    {"size": 5 * 1024 * 1024 + 1},
    {"size": 0},
    {"size": "100"},
    {"device_id": "nope"},
])
def test_photo_url_refuses_other_types_and_big_files(app, changes):
    body = {"device_id": DEVICE, "content_type": "image/jpeg", "size": 1000, **changes}
    assert call(app, "/app/photo-url", body)[0] == 400
