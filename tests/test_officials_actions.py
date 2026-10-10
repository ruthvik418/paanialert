"""Officials' actions: report status, and manual advisories (issue, recipients, lift), against fake AWS."""
import json

import pytest

KEY = {"x-dashboard-key": "test-dashboard-key"}
IP = "203.0.113.7"
CENTRE = (22.7196, 75.8577)            # Rajwada, Indore
METRES_PER_DEG_LAT = 111_320


def api(route, body=None, path=None, headers=KEY):
    from api.app import handler
    event = {"routeKey": route, "headers": headers, "pathParameters": path or {},
             "requestContext": {"http": {"sourceIp": IP}}}
    if body is not None:
        event["body"] = json.dumps(body)
    resp = handler(event, None)
    return resp["statusCode"], json.loads(resp["body"])


def north(km: float) -> tuple[float, float]:
    return CENTRE[0] + km * 1000 / METRES_PER_DEG_LAT, CENTRE[1]


@pytest.fixture
def sent(aws, monkeypatch):
    """Every WhatsApp the advisories send: (to, body)."""
    import api.advisories as advisories
    out = []
    monkeypatch.setattr(advisories, "send_whatsapp", lambda to, body, media_url=None: out.append((to, body)) or "SM1")
    return out


def subscribe(phone: str, point: tuple[float, float], lang: str = "en"):
    from common import db
    from common.geo import geohash6
    from common.hashing import phone_hash
    db.put_subscriber(phone_hash(phone), phone, geohash6(*point), lang)


def save_report(phone_hash: str, sick: bool = False):
    from common import db
    from common.geo import geohash6
    from common.models import Report
    from common.timeutil import now_iso
    import uuid
    r = Report(report_id=uuid.uuid4().hex, phone_hash=phone_hash, created_at=now_iso(), lat=CENTRE[0],
               lon=CENTRE[1], geohash6=geohash6(*CENTRE), smell="sewage", colour="brown", sick_count=1 if sick else None)
    db.put_report(r)
    return r


# Report status

def test_report_status_is_saved_and_logged_with_the_ip(aws):
    from common import db

    r = save_report("p1")
    status, body = api("POST /reports/{id}/status", {"status": "reviewing", "note": "Engineer visiting, see https://x.example"},
                       {"id": r.report_id})
    assert status == 200 and body["status"] == "reviewing"
    stored = db.get_report(r.report_id)
    assert stored.status == "reviewing" and stored.status_at and "https" not in stored.status_note
    row = next(a for a in db.recent_activity("2000-01-01T00:00:00Z") if a["kind"] == "report_status")
    assert row["report_id"] == r.report_id and row["was"] == "new" and row["ip"] == IP


def test_report_status_rejects_unknown_status_and_report(aws):
    r = save_report("p1")
    assert api("POST /reports/{id}/status", {"status": "deleted"}, {"id": r.report_id})[0] == 400
    assert api("POST /reports/{id}/status", {"status": "resolved"}, {"id": "nope"})[0] == 404


def test_false_report_does_not_count_toward_a_cluster(aws):
    import cluster.app as cluster_app
    from common import db

    reports = [save_report(f"phone-{i}") for i in range(5)]          # 5 phones: an Alert
    assert cluster_app.evaluate(reports, cluster_app.now())[0].level == "alert"
    assert api("POST /reports/{id}/status", {"status": "false_report"}, {"id": reports[0].report_id})[0] == 200

    cluster_app.run()
    [c] = db.all_clusters()
    assert c.level == "watch" and c.distinct_phones == 4 and reports[0].report_id not in c.report_ids


# Advisories

def test_recipients_follow_the_radius(sent):
    subscribe("whatsapp:+919800000001", CENTRE)         # at the centre
    subscribe("whatsapp:+919800000002", north(1.5))     # 1.5 km away
    subscribe("whatsapp:+919800000003", north(3.5))     # 3.5 km away
    subscribe("whatsapp:+919800000004", north(10))      # 10 km away

    counts = {r: api("POST /advisories/preview", {"lat": CENTRE[0], "lon": CENTRE[1], "radius_m": r})[1]["total"]
              for r in (500, 1000, 2000)}
    assert counts[500] == 1 and counts[2000] == 2 and counts[500] <= counts[1000] <= counts[2000]

    status, adv = api("POST /advisories", {"lat": CENTRE[0], "lon": CENTRE[1], "radius_m": 2000, "kind": "boil"})
    assert status == 201 and adv["status"] == "active" and len(adv["whatsapp_to"]) == 2
    assert sorted(to for to, _ in sent) == ["whatsapp:+919800000001", "whatsapp:+919800000002"]
    assert all("boil" in body.lower() for _, body in sent)


def test_warning_is_in_each_persons_language_and_the_note_has_no_links(sent):
    subscribe("whatsapp:+919800000001", CENTRE, "hi")
    note = "Tanker at ward office 4 pm. Details: bit.ly/xyz " + "x" * 300
    status, adv = api("POST /advisories", {"lat": CENTRE[0], "lon": CENTRE[1], "radius_m": 500, "kind": "do_not_use",
                                           "note": note})
    assert status == 201 and len(adv["note"]) <= 200 and "bit.ly" not in adv["note"]
    [(_, body)] = sent
    assert "अधिकारियों की चेतावनी" in body and "Tanker at ward office" in body and "bit.ly" not in body


def test_lift_sends_the_all_clear_to_the_same_people(sent):
    from common import db

    subscribe("whatsapp:+919800000001", CENTRE)
    _, adv = api("POST /advisories", {"lat": CENTRE[0], "lon": CENTRE[1], "radius_m": 500, "kind": "boil",
                                      "cluster_id": "tsjcnp"})
    subscribe("whatsapp:+919800000009", CENTRE)         # joined after the warning: wasn't warned, no all-clear
    sent.clear()

    status, lifted = api("POST /advisories/{id}/lift", path={"id": adv["advisory_id"]})
    assert status == 200 and lifted["status"] == "lifted" and lifted["lifted_at"]
    assert [to for to, _ in sent] == ["whatsapp:+919800000001"] and "lifted" in sent[0][1]
    assert api("POST /advisories/{id}/lift", path={"id": adv["advisory_id"]})[0] == 409     # only once

    kinds = [(a["kind"], a.get("ip")) for a in db.recent_activity("2000-01-01T00:00:00Z")]
    assert ("warning_issued", IP) in kinds and ("warning_lifted", IP) in kinds
    assert [a["kind"] for a in db.recent_activity("2000-01-01T00:00:00Z")].count("warning_all_clear") == 1


def test_public_advisories_are_rounded_and_only_active(sent):
    _, adv = api("POST /advisories", {"lat": 22.71964, "lon": 75.85771, "radius_m": 1000, "kind": "boil",
                                      "note": "internal: call Ravi"})
    _, gone = api("POST /advisories", {"lat": 22.6, "lon": 75.8, "radius_m": 500, "kind": "do_not_use"})
    api("POST /advisories/{id}/lift", path={"id": gone["advisory_id"]})

    status, body = api("GET /public/advisories", headers={})
    assert status == 200
    assert body["advisories"] == [{"lat": 22.72, "lon": 75.858, "radius_m": 1000, "kind": "boil",
                                   "created_at": adv["created_at"]}]


@pytest.mark.parametrize("body", [
    {"lat": 22.7, "lon": 75.8, "radius_m": 750, "kind": "boil"},
    {"lat": 22.7, "lon": 75.8, "radius_m": 500, "kind": "panic"},
    {"lat": 51.5, "lon": -0.1, "radius_m": 500, "kind": "boil"},
    {"lat": "22.7", "lon": 75.8, "radius_m": 500, "kind": "boil"},
    {"lat": 22.7, "lon": 75.8, "radius_m": 500, "kind": "boil", "note": 5},
])
def test_bad_advisory_is_a_400(sent, body):
    assert api("POST /advisories", body)[0] == 400
    assert not sent


@pytest.mark.parametrize("route,path", [
    ("POST /advisories", None), ("POST /advisories/preview", None), ("GET /advisories", None),
    ("POST /advisories/{id}/lift", {"id": "x"}), ("POST /reports/{id}/status", {"id": "x"}),
])
def test_actions_need_the_dashboard_key(sent, route, path):
    body = {"lat": 22.7, "lon": 75.8, "radius_m": 500, "kind": "boil", "status": "resolved"}
    assert api(route, body, path, headers={})[0] == 401
    assert api(route, body, path, headers={"x-dashboard-key": "wrong"})[0] == 401
    assert not sent
