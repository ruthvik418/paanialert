"""The worker end to end against fake AWS, with Twilio and Bedrock replaced."""
import pytest

PHONE = "whatsapp:+919876543210"


@pytest.fixture
def worker(aws, monkeypatch):
    import worker.app as w
    from agent.runner import AgentUnavailable

    sent = []
    monkeypatch.setattr(w, "send_whatsapp", lambda to, body, media_url=None: sent.append((to, body)) or "SM")

    def no_bedrock(*args, **kwargs):
        raise AgentUnavailable()

    monkeypatch.setattr(w, "agent_reply", no_bedrock)
    w.sent = sent
    return w


def test_complaint_then_pin_attaches_location(worker):
    from common import db
    from common.hashing import phone_hash

    answer = worker.handle({"From": PHONE, "Body": "Nal ka paani peela aa raha hai, badboo hai, 2 din se"})
    assert "save" in answer.lower() and "📍" in answer   # saved, and asked for a pin

    state = db.get_session(phone_hash(PHONE))
    report = db.get_report(state["last_report_id"])
    assert report.colour == "yellow" and report.lat is None

    answer = worker.handle({"From": PHONE, "Body": "", "Latitude": "22.7196", "Longitude": "75.8577"})
    report = db.get_report(state["last_report_id"])
    assert report.lat == 22.7196 and report.geohash6
    assert len(worker.sent) == 2 and worker.sent[0][0] == PHONE


def test_pin_first_is_used_by_next_report(worker):
    from common import db
    from common.hashing import phone_hash

    worker.handle({"From": PHONE, "Body": "", "Latitude": "28.6139", "Longitude": "77.2090"})
    worker.handle({"From": PHONE, "Body": "water is brown and my son has diarrhoea"})
    report = db.get_report(db.get_session(phone_hash(PHONE))["last_report_id"])
    assert report.lat == 28.6139 and report.sick_count == 1 and report.colour == "brown"


def test_greeting_saves_nothing(worker):
    from common import db
    from common.hashing import phone_hash

    answer = worker.handle({"From": PHONE, "Body": "hello"})
    assert "PaaniAlert" in answer
    assert "last_report_id" not in db.get_session(phone_hash(PHONE))
