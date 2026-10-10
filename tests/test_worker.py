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
    assert "saved" in answer and "📍" in answer         # saved in English, asked for a pin
    assert "Choose your language" in answer             # first contact shows the language menu

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


def test_language_choice_sticks(worker):
    worker.handle({"From": PHONE, "Body": "hello"})          # first contact: English + menu
    assert "Tell me" in worker.sent[-1][1] and "1️⃣" in worker.sent[-1][1]
    worker.handle({"From": PHONE, "Body": "2"})               # picks Hindi
    assert "हिंदी" in worker.sent[-1][1]
    answer = worker.handle({"From": PHONE, "Body": "paani bhura hai"})
    assert "दर्ज" in answer and "1️⃣" not in answer
    worker.handle({"From": PHONE, "Body": "language"})        # menu again
    worker.handle({"From": PHONE, "Body": "3"})               # Hinglish
    assert "Hinglish" in worker.sent[-1][1]


def test_number_without_menu_is_not_a_language(worker):
    worker.handle({"From": PHONE, "Body": "hello"})
    worker.handle({"From": PHONE, "Body": "paani peela hai"})  # clears the menu
    worker.handle({"From": PHONE, "Body": "2"})               # answer, not a language pick
    from common import db
    from common.hashing import phone_hash
    assert db.get_language(phone_hash(PHONE)) is None


def test_pin_adds_area_name(worker, monkeypatch):
    from common import db
    from common.hashing import phone_hash

    monkeypatch.setattr(worker, "area_name", lambda lat, lon: "Rajwada, Indore")
    worker.handle({"From": PHONE, "Body": "paani peela hai"})
    worker.handle({"From": PHONE, "Body": "", "Latitude": "22.7196", "Longitude": "75.8577"})
    report = db.get_report(db.get_session(phone_hash(PHONE))["last_report_id"])
    assert report.area == "Rajwada, Indore"


def test_offer_alerts_after_pin_and_subscribe(worker):
    from common import db
    from common.geo import geohash6
    from common.hashing import phone_hash

    worker.handle({"From": PHONE, "Body": "water is yellow and smells bad"})
    answer = worker.handle({"From": PHONE, "Body": "", "Latitude": "22.7196", "Longitude": "75.8577"})
    assert "🔔" in answer                                     # offered alerts once located
    assert "SUBSCRIBED" not in answer
    answer = worker.handle({"From": PHONE, "Body": "haan"})
    sub = db.get_subscriber(phone_hash(PHONE))
    assert "✅" in answer and sub["geohash6"] == geohash6(22.7196, 75.8577) and sub["phone"] == PHONE

    # A second report doesn't ask again.
    worker.handle({"From": PHONE, "Body": "still dirty water"})
    answer = worker.handle({"From": PHONE, "Body": "", "Latitude": "22.7196", "Longitude": "75.8577"})
    assert "🔔" not in answer


def test_no_means_no_and_yes_later_is_just_a_message(worker):
    from common import db
    from common.hashing import phone_hash

    worker.handle({"From": PHONE, "Body": "", "Latitude": "28.6139", "Longitude": "77.2090"})
    answer = worker.handle({"From": PHONE, "Body": "paani kala hai"})       # pin first, so offer comes now
    assert "🔔" in answer
    assert "ठीक" in worker.handle({"From": PHONE, "Body": "nahi"}) or "Okay" in worker.sent[-1][1]
    worker.handle({"From": PHONE, "Body": "yes"})                           # not after a question: ignored
    assert db.get_subscriber(phone_hash(PHONE)) is None


def test_same_message_sid_is_handled_once(worker):
    from common import db
    from common.hashing import phone_hash

    msg = {"From": PHONE, "Body": "paani bhura hai, badboo aa rahi hai", "MessageSid": "SMdup1"}
    assert worker.handle(msg)
    assert worker.handle(dict(msg)) == ""                    # Twilio retry or SQS redelivery
    assert len(worker.sent) == 1
    assert len(db.recent_reports("2000-01-01T00:00:00Z")) == 1
    assert [t["role"] for t in db.get_session(phone_hash(PHONE))["turns"]] == ["user", "assistant"]


def test_failed_message_can_be_retried(worker, monkeypatch):
    calls = []

    def flaky(to, body, media_url=None):
        calls.append(to)
        if len(calls) == 1:
            raise RuntimeError("Twilio down")
        return "SM"

    monkeypatch.setattr(worker, "send_whatsapp", flaky)
    msg = {"From": PHONE, "Body": "hello", "MessageSid": "SMretry1"}
    with pytest.raises(RuntimeError):
        worker.handle(msg)
    assert worker.handle(dict(msg))                          # the SQS retry is not skipped
    assert len(calls) == 2
