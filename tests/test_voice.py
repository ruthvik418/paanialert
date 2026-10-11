"""Voice reports: Amazon Transcribe (replaced here), WhatsApp voice notes and the web page's async flow."""
import io
import json

import pytest

PHONE = "whatsapp:+919876543210"
DEVICE = "0b6f4c1e-8a2d-4c4e-9a51-2f0d3c9b7e10"
REQUEST = "5d1c7f0e-2b3a-4c5d-8e9f-0a1b2c3d4e5f"
INDORE = {"lat": 22.7196, "lon": 75.8577}
HINDI = "नल का पानी पीला आ रहा है और बदबू आ रही है"


# agent/voice.py with a fake Transcribe and S3

class FakeTranscribe:
    def __init__(self, statuses, language="hi-IN"):
        self.statuses, self.language, self.started, self.polls = list(statuses), language, None, 0

    def start_transcription_job(self, **kwargs):
        self.started = kwargs

    def get_transcription_job(self, TranscriptionJobName):
        self.polls += 1
        status = self.statuses.pop(0) if len(self.statuses) > 1 else self.statuses[0]
        return {"TranscriptionJob": {"TranscriptionJobStatus": status, "LanguageCode": self.language}}


class FakeS3:
    def __init__(self, transcript):
        self.transcript, self.read = transcript, None

    def get_object(self, Bucket, Key):
        self.read = Key
        body = {"results": {"transcripts": [{"transcript": self.transcript}]}}
        return {"Body": io.BytesIO(json.dumps(body).encode())}


@pytest.fixture
def fake_aws(monkeypatch):
    from agent import voice

    def install(statuses, transcript=HINDI, language="hi-IN"):
        fakes = {"transcribe": FakeTranscribe(statuses, language), "s3": FakeS3(transcript)}
        monkeypatch.setattr(voice, "_clients", fakes)
        monkeypatch.setattr(voice, "_sleep", lambda s: None)
        return fakes
    return install


def test_transcribe_hindi(fake_aws):
    from agent import voice

    fakes = fake_aws(["IN_PROGRESS", "IN_PROGRESS", "COMPLETED"])
    assert voice.transcribe("media-test", "media/SM1.ogg", "ogg") == (HINDI, "hi-IN")
    job = fakes["transcribe"].started
    assert job["MediaFormat"] == "ogg" and job["IdentifyLanguage"] is True
    assert job["LanguageOptions"] == ["hi-IN", "en-IN"]
    assert job["Media"]["MediaFileUri"] == "s3://media-test/media/SM1.ogg"
    assert job["OutputBucketName"] == "media-test" and job["OutputKey"].startswith("transcripts/")
    assert fakes["s3"].read == job["OutputKey"] and fakes["transcribe"].polls == 3


def test_transcribe_gives_up_after_60_seconds(fake_aws):
    from agent import voice

    fakes = fake_aws(["IN_PROGRESS"])
    assert voice.transcribe("media-test", "media/SM1.ogg", "ogg") is None
    assert fakes["transcribe"].polls == 30          # every 2 s for 60 s


def test_empty_transcript_is_none(fake_aws):
    from agent import voice

    fake_aws(["COMPLETED"], transcript="   ")
    assert voice.transcribe("media-test", "media/SM1.ogg", "ogg") is None


def test_failed_job_or_error_is_none(fake_aws, monkeypatch):
    from agent import voice

    fake_aws(["FAILED"])
    assert voice.transcribe("media-test", "media/SM1.ogg", "ogg") is None

    def boom(**kwargs):
        raise RuntimeError("AccessDenied")
    fakes = fake_aws(["COMPLETED"])
    monkeypatch.setattr(fakes["transcribe"], "start_transcription_job", boom)
    assert voice.transcribe("media-test", "media/SM1.ogg", "ogg") is None


# WhatsApp voice notes through the worker

@pytest.fixture
def worker(aws, monkeypatch):
    import worker.app as w
    from agent.runner import AgentUnavailable

    sent, calls = [], []
    monkeypatch.setattr(w, "send_whatsapp", lambda to, body, media_url=None: sent.append((to, body)) or "SM")
    monkeypatch.setattr(w, "save_media", lambda msg, name: (None, f"media/{name}.ogg"))

    def no_bedrock(*args, **kwargs):
        raise AgentUnavailable()
    monkeypatch.setattr(w, "agent_reply", no_bedrock)

    def heard(result):
        def fake(bucket, key, media_format):
            calls.append((bucket, key, media_format))
            return result
        monkeypatch.setattr(w.voice, "transcribe", fake)
    w.sent, w.calls, w.heard = sent, calls, heard
    return w


def voice_note(sid="SMvoice1"):
    return {"From": PHONE, "Body": "", "NumMedia": "1", "MediaUrl0": "https://api.twilio.com/m",
            "MediaContentType0": "audio/ogg", "MessageSid": sid}


def test_hindi_voice_note_is_a_report(worker):
    from common import db
    from common.hashing import phone_hash

    worker.heard((HINDI, "hi-IN"))
    answer = worker.handle(voice_note())
    assert worker.calls == [("media-test", "media/SMvoice1.ogg", "ogg")]
    assert answer.startswith("मैंने सुना: " + HINDI)       # Hindi speaker with no language set: Hindi reply
    assert "दर्ज" in answer
    report = db.get_report(db.get_session(phone_hash(PHONE))["last_report_id"])
    assert report.input_type == "voice" and report.text == "🎤 " + HINDI
    assert report.audio_key == "media/SMvoice1.ogg" and report.lang == "hi"
    assert report.colour == "yellow" and report.smell == "sewage"


def test_long_transcript_is_cut_at_80_characters_in_the_reply(worker):
    from common import db
    from common.hashing import phone_hash

    db.set_language(phone_hash(PHONE), "en")
    long = "The tap water has been yellow and smelly since Monday and my two children have diarrhoea now"
    worker.heard((long, "en-IN"))
    answer = worker.handle(voice_note())
    assert answer.startswith("I heard: " + long[:80].rstrip() + "…\n\n")
    report = db.get_report(db.get_session(phone_hash(PHONE))["last_report_id"])
    assert report.text == "🎤 " + long                  # the whole transcript is kept


@pytest.mark.parametrize("result", [None])           # failed, timed out or empty: voice.transcribe gives None
def test_voice_note_that_cannot_be_read_asks_to_type(worker, result):
    from agent import prompts
    from common import db
    from common.hashing import phone_hash

    worker.heard(result)
    answer = worker.handle(voice_note())
    assert answer.startswith(prompts.VOICE_PENDING["en"])
    assert worker.sent and "last_report_id" not in db.get_session(phone_hash(PHONE))


# The web page: upload, 202, poll, worker, done

@pytest.fixture
def app(worker, monkeypatch):
    import api.app_report as app_report

    monkeypatch.setattr(worker, "send_whatsapp", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no WhatsApp")))
    app_report._s3 = None
    return app_report


def call(app, method, route, body=None, path=None, query=None):
    resp = app.handler({"routeKey": f"{method} {route}", "body": json.dumps(body) if body else None,
                        "pathParameters": path, "queryStringParameters": query}, None)
    return resp["statusCode"], json.loads(resp["body"])


def upload_recording(app):
    import boto3

    status, body = call(app, "POST", "/app/audio-url", {"device_id": DEVICE, "content_type": "audio/webm", "size": 4096})
    assert status == 200 and body["audio_key"].startswith(f"app-uploads/{DEVICE}/audio/")
    assert body["audio_key"].endswith(".webm") and "X-Amz-Signature" in body["url"]
    boto3.client("s3", region_name="ap-south-1").put_object(
        Bucket="media-test", Key=body["audio_key"], Body=b"x" * 4096, ContentType="audio/webm")
    return body["audio_key"]


def queued_messages():
    import os

    import boto3
    sqs = boto3.client("sqs", region_name="ap-south-1")
    got = sqs.receive_message(QueueUrl=os.environ["INCOMING_QUEUE_URL"], MaxNumberOfMessages=10,
                              AttributeNames=["ApproximateReceiveCount"])
    return got.get("Messages", [])


def poll(app, device=DEVICE):
    return call(app, "GET", "/app/report/{request_id}", path={"request_id": REQUEST}, query={"device_id": device})


def test_web_voice_report_is_async(app, worker):
    from common import db

    audio_key = upload_recording(app)
    status, body = call(app, "POST", "/app/report", {"device_id": DEVICE, "text": "", "lang": "en",
                                                     "audio_key": audio_key, "request_id": REQUEST, **INDORE})
    assert status == 202 and body == {"request_id": REQUEST, "status": "processing"}
    assert poll(app) == (200, {"request_id": REQUEST, "status": "processing"})

    # The same request again (the page retried) is not queued twice.
    assert call(app, "POST", "/app/report", {"device_id": DEVICE, "text": "", "lang": "en",
                                             "audio_key": audio_key, "request_id": REQUEST, **INDORE})[0] == 202
    messages = queued_messages()
    assert len(messages) == 1

    worker.heard(("The water is brown and smells like sewage", "en-IN"))
    worker.handler({"Records": [{"body": m["Body"], "attributes": m["Attributes"]} for m in messages]}, None)
    assert worker.calls == [("media-test", audio_key, "webm")]

    status, done = poll(app)
    assert status == 200 and done["status"] == "done" and done["saved"] is True
    assert done["transcript"] == "The water is brown and smells like sewage"
    assert done["reply"].startswith("I heard: The water is brown and smells like sewage\n\nThank you, your report is saved.")
    report = db.get_report(done["report_id"])
    assert report.channel == "app" and report.input_type == "voice" and report.audio_key == audio_key
    assert report.colour == "brown" and (report.lat, report.lon) == (22.7196, 75.8577)

    # SQS delivering it again changes nothing.
    worker.handler({"Records": [{"body": m["Body"], "attributes": m["Attributes"]} for m in messages]}, None)
    assert poll(app)[1]["report_id"] == done["report_id"]


def test_web_voice_that_cannot_be_read_is_done_but_not_saved(app, worker):
    from agent import prompts

    audio_key = upload_recording(app)
    call(app, "POST", "/app/report", {"device_id": DEVICE, "text": "", "lang": "hi", "audio_key": audio_key,
                                      "request_id": REQUEST, **INDORE})
    worker.heard(None)
    worker.handler({"Records": [{"body": m["Body"]} for m in queued_messages()]}, None)
    _, done = poll(app)
    assert done["status"] == "done" and done["saved"] is False and "transcript" not in done
    assert done["reply"] == prompts.VOICE_PENDING["hi"]


def test_only_the_sending_device_can_poll(app):
    audio_key = upload_recording(app)
    call(app, "POST", "/app/report", {"device_id": DEVICE, "text": "", "lang": "en", "audio_key": audio_key,
                                      "request_id": REQUEST, **INDORE})
    assert poll(app, device="11111111-2222-4333-8444-555555555555")[0] == 404


@pytest.mark.parametrize("changes", [
    {"content_type": "audio/ogg"},
    {"content_type": "audio/mp4"},
    {"size": 2 * 1024 * 1024 + 1},
])
def test_audio_url_is_webm_up_to_2_mb(app, changes):
    body = {"device_id": DEVICE, "content_type": "audio/webm", "size": 1000, **changes}
    assert call(app, "POST", "/app/audio-url", body)[0] == 400


def test_audio_key_must_be_this_devices_recording(app):
    status, body = call(app, "POST", "/app/report", {"device_id": DEVICE, "text": "", "lang": "en", **INDORE,
                                                     "audio_key": f"app-uploads/{DEVICE}/0123456789abcdef0123456789abcdef.jpg"})
    assert status == 400 and "audio_key" in body["error"]


def test_typed_reports_stay_synchronous(app):
    status, body = call(app, "POST", "/app/report", {"device_id": DEVICE, "text": "paani bhura hai", "lang": "en",
                                                     **INDORE})
    assert status == 200 and body["saved"] is True and not queued_messages()


def test_officials_get_a_5_minute_link_to_the_voice_note(worker):
    from api.app import handler as dashboard_api
    from common import db
    from common.hashing import phone_hash
    from tests.conftest import SECRETS

    worker.heard((HINDI, "hi-IN"))
    worker.handle(voice_note())
    report_id = db.get_session(phone_hash(PHONE))["last_report_id"]
    resp = dashboard_api({"routeKey": "GET /reports/{id}/audio", "pathParameters": {"id": report_id},
                          "headers": {"x-dashboard-key": SECRETS["dashboard_key"]}}, None)
    body = json.loads(resp["body"])
    assert resp["statusCode"] == 200 and "SMvoice1.ogg" in body["url"] and body["expires_in"] == 300
    resp = dashboard_api({"routeKey": "GET /reports/{id}/audio", "pathParameters": {"id": report_id}, "headers": {}}, None)
    assert resp["statusCode"] == 401
