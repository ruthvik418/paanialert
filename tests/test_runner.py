"""The agent runner with the model replaced: Mantle (OpenAI-compatible) and Converse paths."""
import json
import logging

import pytest

PHONE = "whatsapp:+919876543210"
COMPLAINT = "Nal ka paani peela aa raha hai, badboo hai, 2 din se"
NOTHING = {"smell": "unknown", "colour": "unknown", "taste": "unknown", "since_days": None, "sick_count": None,
           "symptoms": [], "source": "unknown", "landmark": None, "clears_quickly": None}
COMPLAINT_FIELDS = {**NOTHING, "smell": "sewage", "colour": "yellow", "since_days": 2, "source": "pipe"}


def text(content):
    return {"content": content}


def fields(arguments):
    """The model filling ReportFields; arguments is a dict, or a raw string to send malformed JSON."""
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return {"tool_calls": [{"id": "call_1", "type": "function",
                            "function": {"name": "ReportFields", "arguments": raw}}]}


@pytest.fixture
def mantle(aws, monkeypatch):
    """Scripted replies per model id, served through a fake openai.AsyncOpenAI."""
    import openai
    from openai.types.chat import ChatCompletion

    import agent.runner as runner

    monkeypatch.setattr(runner, "MODEL_ENDPOINT", "mantle")
    monkeypatch.setattr(runner, "MODEL_IDS", ["model-a", "model-b"])
    scripts: dict[str, list] = {}
    clients: list[dict] = []
    requests: list[dict] = []

    class FakeClient:
        def __init__(self, **client_args):
            clients.append(client_args)
            self.chat = self
            self.completions = self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def create(self, **request):
            requests.append(request)
            step = scripts[request["model"]].pop(0)
            if isinstance(step, Exception):
                raise step
            message = {"role": "assistant", "content": None, **step}
            return ChatCompletion.model_validate({
                "id": "chatcmpl-1", "object": "chat.completion", "created": 0, "model": request["model"],
                "choices": [{"index": 0, "message": message,
                             "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}],
            })

    monkeypatch.setattr(openai, "AsyncOpenAI", FakeClient)
    return scripts, clients, requests


def _ctx(lang="en"):
    from agent.reports import TurnContext
    return TurnContext(phone_hash="hash-1", lang=lang, text=COMPLAINT)


def test_complaint_is_saved_and_the_reply_is_built_by_code(mantle):
    from agent.runner import reply
    from common import db

    scripts, clients, _ = mantle
    scripts["model-a"] = [fields(COMPLAINT_FIELDS)]
    ctx = _ctx()
    answer = reply(COMPLAINT, ctx, [])
    assert answer.startswith("✅ Report saved: yellow water, sewage smell, for 2 days.")
    assert "boil" in answer and "📍" in answer                     # ADVICE, then ASK_LOCATION (no pin)
    report = db.get_report(ctx.saved.report_id)
    assert report.colour == "yellow" and report.extracted_by == "agent:model-a"
    # Short-lived token from the worker's credentials, not a stored key.
    assert clients[0]["base_url"] == "https://bedrock-mantle.ap-south-1.api.aws/v1"
    assert clients[0]["api_key"].startswith("bedrock-api-key-")


def test_confirmation_in_hindi_with_a_pin():
    from agent.runner import ReportFields, confirmation

    f = ReportFields(**{**NOTHING, "colour": "brown", "sick_count": 0})
    assert confirmation(f, "hi") == "✅ शिकायत दर्ज: भूरा पानी, कोई बीमार नहीं।"


def test_model_that_says_saved_in_text_is_forced_to_fill_the_fields(mantle):
    """Replying "saved" without the tool no longer loses the complaint: Strands forces the tool call."""
    from agent.runner import reply

    scripts, _, requests = mantle
    scripts["model-a"] = [text("Your report has been saved, thank you."), fields(COMPLAINT_FIELDS)]
    ctx = _ctx()
    reply(COMPLAINT, ctx, [])
    assert ctx.saved.extracted_by == "agent:model-a"
    assert requests[1]["tool_choice"] == {"type": "function", "function": {"name": "ReportFields"}}


def test_malformed_tool_call_is_retried_not_read_as_nothing_wrong(mantle):
    from agent.runner import reply

    scripts, _, _ = mantle
    # DeepSeek once sent reply text glued onto the JSON; Strands then passes {}, which must fail validation.
    scripts["model-a"] = [fields('{"smell": "sewage", "colour": "yellow"} धन्यवाद'),
                          fields(COMPLAINT_FIELDS)]
    ctx = _ctx()
    reply(COMPLAINT, ctx, [])
    assert ctx.saved is not None and ctx.saved.colour == "yellow"


def test_model_error_moves_to_the_next_model(mantle, caplog):
    from agent.runner import reply

    scripts, _, _ = mantle
    scripts["model-a"] = [RuntimeError("Mantle timeout")]
    scripts["model-b"] = [fields(COMPLAINT_FIELDS)]
    ctx = _ctx()
    with caplog.at_level(logging.WARNING, logger="agent.runner"):
        reply(COMPLAINT, ctx, [])
    assert ctx.saved.extracted_by == "agent:model-b"
    assert "model bedrock:model-a failed" in caplog.text


def test_greeting_gets_a_short_model_reply_and_saves_nothing(mantle):
    from agent.runner import reply

    scripts, _, _ = mantle
    scripts["model-a"] = [fields(NOTHING), text("Hi! Tell me what is wrong with your water.")]
    ctx = _ctx()
    assert reply("hello", ctx, []) == "Hi! Tell me what is wrong with your water."
    assert ctx.saved is None


def test_chat_reply_that_claims_a_save_becomes_welcome(mantle):
    from agent.prompts import WELCOME
    from agent.runner import reply

    scripts, _, _ = mantle
    scripts["model-a"] = [fields(NOTHING), text("Your report is saved.")]
    ctx = _ctx()
    assert reply("hello", ctx, []) == WELCOME["en"]
    assert ctx.saved is None


def test_every_model_failing_falls_back_to_keywords(mantle, monkeypatch):
    import worker.app as w
    from common import db
    from common.hashing import phone_hash

    monkeypatch.setattr(w, "send_whatsapp", lambda to, body, media_url=None: "SM")
    scripts, _, _ = mantle
    scripts["model-a"] = [RuntimeError("down")]
    scripts["model-b"] = [RuntimeError("down")]
    w.handle({"From": PHONE, "Body": COMPLAINT})
    report = db.get_report(db.get_session(phone_hash(PHONE))["last_report_id"])
    assert report.extracted_by == "keywords" and report.colour == "yellow"


def test_runtime_converse_path(aws, monkeypatch):
    from botocore.stub import Stubber

    import agent.runner as runner

    monkeypatch.setattr(runner, "MODEL_ENDPOINT", "runtime")
    monkeypatch.setattr(runner, "MODEL_IDS", ["deepseek.v3-v1:0"])
    usage = {"usage": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2}, "metrics": {"latencyMs": 1}}
    responses = [
        {"output": {"message": {"role": "assistant", "content": [
            {"toolUse": {"toolUseId": "t1", "name": "ReportFields", "input": COMPLAINT_FIELDS}}]}},
         "stopReason": "tool_use", **usage},
        {"output": {"message": {"role": "assistant", "content": [{"text": "ok"}]}},
         "stopReason": "end_turn", **usage},
    ]
    real_model = runner.model

    def stubbed(model_id):
        m = real_model(model_id)
        stub = Stubber(m.client)
        for r in responses:
            stub.add_response("converse", r)
        stub.activate()
        return m

    monkeypatch.setattr(runner, "model", stubbed)
    ctx = _ctx()
    assert runner.reply(COMPLAINT, ctx, []).startswith("✅ Report saved")
    assert ctx.saved.extracted_by == "agent:deepseek.v3-v1:0"
