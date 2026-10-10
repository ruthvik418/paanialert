"""Web push for the report app ("Warn me about my area"), with the push sender replaced."""
import json

import pytest

DEVICE = "0b6f4c1e-8a2d-4c4e-9a51-2f0d3c9b7e10"
OTHER_DEVICE = "6a1c2b3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d"
CENTRE = (22.7196, 75.8577)
ENDPOINT = "https://fcm.googleapis.com/fcm/send/abc123:APA91bTest"
KEYS = {"p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM",
        "auth": "tBHItJI5svbpez7KI4CCXg"}
DASH = {"x-dashboard-key": "test-dashboard-key"}


class Sent(list):
    """The pushes sent, plus .fake: the replaced webpush (set .fake.fail_with to an HTTP status to fail)."""


@pytest.fixture
def pushes(aws, monkeypatch):
    """Every push sent: (endpoint, payload dict). Set pushes.fail_with = 410 to make the push service refuse."""
    import pywebpush

    sent = Sent()

    def fake_webpush(subscription_info, data, vapid_private_key, vapid_claims, **kwargs):
        assert vapid_private_key == "test-vapid-private" and vapid_claims["sub"]
        if getattr(fake_webpush, "fail_with", None):
            response = type("R", (), {"status_code": fake_webpush.fail_with})()
            raise pywebpush.WebPushException("refused", response=response)
        sent.append((subscription_info["endpoint"], json.loads(data)))
        return "ok"

    monkeypatch.setattr(pywebpush, "webpush", fake_webpush)
    import api.advisories as advisories
    monkeypatch.setattr(advisories, "send_whatsapp", lambda *a, **k: "SM")
    sent.fake = fake_webpush
    return sent


def app_call(route, body):
    from api.app_report import handler
    resp = handler({"routeKey": route, "body": json.dumps(body)}, None)
    return resp["statusCode"], json.loads(resp["body"])


def dash_call(route, body=None, path=None):
    from api.app import handler
    resp = handler({"routeKey": route, "headers": DASH, "pathParameters": path or {}, "body": json.dumps(body or {}),
                    "requestContext": {"http": {"sourceIp": "203.0.113.9"}}}, None)
    return resp["statusCode"], json.loads(resp["body"])


def subscribe(endpoint=ENDPOINT, device=DEVICE, lang="hi", point=CENTRE):
    return app_call("POST /app/subscribe", {"device_id": device, "subscription": {"endpoint": endpoint, "keys": KEYS},
                                            "lat": point[0], "lon": point[1], "lang": lang})


def test_subscribe_stores_the_area_and_only_that_device_can_unsubscribe(pushes):
    from common import db
    from common.geo import geohash6
    from common.push import subscription_id

    status, body = subscribe()
    assert status == 201 and body["geohash6"] == geohash6(*CENTRE)
    sid = subscription_id(ENDPOINT)
    assert db.get_app_subscriber(sid)["lang"] == "hi"

    app_call("POST /app/unsubscribe", {"device_id": OTHER_DEVICE, "endpoint": ENDPOINT})
    assert db.get_app_subscriber(sid) is not None
    assert app_call("POST /app/unsubscribe", {"device_id": DEVICE, "endpoint": ENDPOINT}) == (200, {"subscribed": False})
    assert db.get_app_subscriber(sid) is None


@pytest.mark.parametrize("endpoint", [
    "http://fcm.googleapis.com/fcm/send/x",          # not https
    "https://example.com/push",                      # not a push service
    "https://fcm.googleapis.com.evil.example/x",     # look-alike host
    "https://169.254.169.254/latest/meta-data",
])
def test_subscribe_only_accepts_browser_push_services(pushes, endpoint):
    assert subscribe(endpoint=endpoint)[0] == 400


def test_push_key_is_served(pushes):
    assert app_call("GET /app/push-key", {}) == (200, {"public_key": "BTestVapidPublicKey"})


def test_advisory_pushes_to_app_subscribers_in_their_language_then_lift_sends_all_clear(pushes):
    from common import db

    subscribe(lang="hi")
    subscribe(endpoint="https://fcm.googleapis.com/fcm/send/far-away", point=(22.80, 75.86), lang="en")   # ~9 km

    assert dash_call("POST /advisories/preview", {"lat": CENTRE[0], "lon": CENTRE[1], "radius_m": 500})[1]["app"] == 1
    status, adv = dash_call("POST /advisories", {"lat": CENTRE[0], "lon": CENTRE[1], "radius_m": 500, "kind": "do_not_use"})
    assert status == 201 and len(adv["app_to"]) == 1
    [(endpoint, payload)] = pushes
    assert endpoint == ENDPOINT and payload["title"] == "PaaniAlert"
    assert "अधिकारियों की चेतावनी" in payload["body"] and "STOP" not in payload["body"]

    pushes.clear()
    assert dash_call("POST /advisories/{id}/lift", path={"id": adv["advisory_id"]})[0] == 200
    [(endpoint, payload)] = pushes
    assert endpoint == ENDPOINT and "हटा दी" in payload["body"]
    rows = [a for a in db.recent_activity("2000-01-01T00:00:00Z") if a.get("channel") == "push"]
    assert {r["kind"] for r in rows} == {"warning", "warning_all_clear"} and all(r["ok"] for r in rows)


def test_subscription_the_push_service_says_is_gone_is_removed(pushes):
    from common import db
    from common.push import subscription_id

    subscribe()
    pushes.fake.fail_with = 410
    dash_call("POST /advisories", {"lat": CENTRE[0], "lon": CENTRE[1], "radius_m": 500, "kind": "boil"})
    assert db.get_app_subscriber(subscription_id(ENDPOINT)) is None
    row = next(a for a in db.recent_activity("2000-01-01T00:00:00Z") if a.get("channel") == "push")
    assert row["ok"] is False and "410" in row["error"]


def test_other_push_failures_keep_the_subscription(pushes):
    from common import db
    from common.push import subscription_id

    subscribe()
    pushes.fake.fail_with = 500
    dash_call("POST /advisories", {"lat": CENTRE[0], "lon": CENTRE[1], "radius_m": 500, "kind": "boil"})
    assert db.get_app_subscriber(subscription_id(ENDPOINT)) is not None


def test_automatic_alert_and_all_clear_push_to_app_subscribers(pushes, monkeypatch):
    import uuid

    import cluster.app as cluster_app
    from common import db
    from common.geo import geohash6
    from common.models import Report
    from common.timeutil import now_iso

    monkeypatch.setattr(cluster_app, "send_whatsapp", lambda *a, **k: "SM")
    subscribe(lang="en")
    for i in range(5):     # 5 phones in one cell: an Alert
        db.put_report(Report(report_id=uuid.uuid4().hex, phone_hash=f"phone-{i}", created_at=now_iso(),
                             lat=CENTRE[0], lon=CENTRE[1], geohash6=geohash6(*CENTRE), smell="sewage"))
    cluster_app.run()
    [(_, alert)] = pushes
    assert "5 bad-water reports near you" in alert["body"] and "STOP" not in alert["body"]

    pushes.clear()
    [c] = db.all_clusters()
    assert dash_call("POST /clusters/{id}/status", {"status": "fixed"}, {"id": c.cluster_id})[1]["all_clear_sent"] == 1
    [(_, clear)] = pushes
    assert "marked the water problem near you as fixed" in clear["body"]
