"""The agent runner with the model replaced: Mantle (OpenAI-compatible) and Converse paths."""
import json
import logging

import pytest

PHONE = "whatsapp:+919876543210"
COMPLAINT = "Nal ka paani peela aa raha hai, badboo hai, 2 din se"
GOOD_ARGS = {"smell": "sewage", "colour": "yellow", "since_days": 2}


def text(content):
    return {"content": content}


def tool(arguments):
    """A save_report call; arguments is a dict, or a raw string to send malformed JSON."""
    raw = arguments if isinstance(arguments, str) else json.dumps(arguments)
    return {"tool_calls": [{"id": "call_1", "type": "function",
                            "function": {"name": "save_report", "arguments": raw}}]}


@pytest.fixture
def mantle(aws, monkeypatch):
    """Scripted replies per model id, served through a fake openai.AsyncOpenAI."""
    import boto3
    import openai
    from openai.types.chat import ChatCompletion

    import agent.runner as runner

    boto3.client("ssm", region_name="ap-south-1").put_parameter(
        Name="/paanialert/bedrock_api_key", Value="test-bedrock-key", Type="SecureString")
    monkeypatch.setattr(runner, "MODEL_ENDPOINT", "mantle")
    monkeypatch.setattr(runner, "MODEL_IDS", ["model-a", "model-b"])
    scripts: dict[str, list[dict]] = {}
    clients: list[dict] = []

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
            message = {"role": "assistant", "content": None, **scripts[request["model"]].pop(0)}
            return ChatCompletion.model_validate({
                "id": "chatcmpl-1", "object": "chat.completion", "created": 0, "model": request["model"],
                "choices": [{"index": 0, "message": message,
                             "finish_reason": "tool_calls" if message.get("tool_calls") else "stop"}],
            })

    monkeypatch.setattr(openai, "AsyncOpenAI", FakeClient)
    return scripts, clients


def _ctx():
    from agent.reports import TurnContext
    return TurnContext(phone_hash="hash-1", lang="en", text=COMPLAINT)


def test_mantle_saves_with_the_model_that_answered(mantle):
    from agent.runner import reply
    from common import db

    scripts, clients = mantle
    scripts["model-a"] = [tool(GOOD_ARGS), text("Your report is saved. Please send a location pin.")]
    ctx = _ctx()
    assert "saved" in reply(COMPLAINT, ctx, [])
    report = db.get_report(ctx.saved.report_id)
    assert report.colour == "yellow" and report.extracted_by == "agent:model-a"
    assert clients[0]["base_url"] == "https://bedrock-mantle.ap-south-1.api.aws/v1"
    assert clients[0]["api_key"] == "test-bedrock-key"


def test_false_saved_reply_moves_to_the_next_model(mantle, caplog):
    from agent.runner import reply

    scripts, _ = mantle
    scripts["model-a"] = [text("Your report has been saved, thank you.")]   # no tool call
    scripts["model-b"] = [tool(GOOD_ARGS), text("Saved. Please boil the water.")]
    ctx = _ctx()
    with caplog.at_level(logging.WARNING, logger="agent.runner"):
        reply(COMPLAINT, ctx, [])
    assert ctx.saved.extracted_by == "agent:model-b"
    assert "model model-a failed: reply says the report was saved" in caplog.text


def test_malformed_tool_call_moves_to_the_next_model(mantle, caplog):
    from agent.runner import reply
    from common import db

    scripts, _ = mantle
    # DeepSeek once sent reply text glued onto the JSON; Strands then calls the tool with no arguments.
    scripts["model-a"] = [tool('{"smell": "sewage", "colour": "yellow"} धन्यवाद'), text("Sorry, please say that again.")]
    scripts["model-b"] = [tool(GOOD_ARGS), text("Saved.")]
    ctx = _ctx()
    with caplog.at_level(logging.WARNING, logger="agent.runner"):
        reply(COMPLAINT, ctx, [])
    assert ctx.saved.extracted_by == "agent:model-b"
    assert len(db.recent_reports("2000-01-01T00:00:00Z")) == 1           # the empty call saved nothing
    assert "model model-a failed: save_report called with no fields" in caplog.text


def test_greeting_needs_no_save(mantle):
    from agent.runner import reply

    scripts, _ = mantle
    scripts["model-a"] = [text("Hi! Tell me what is wrong with your water.")]
    ctx = _ctx()
    assert "Tell me" in reply("hello", ctx, [])
    assert ctx.saved is None


def test_every_model_claiming_saved_falls_back_to_keywords(mantle, monkeypatch):
    """A model says "saved" without calling the tool: the complaint is still stored, by keywords."""
    import worker.app as w
    from common import db
    from common.hashing import phone_hash

    monkeypatch.setattr(w, "send_whatsapp", lambda to, body, media_url=None: "SM")
    scripts, _ = mantle
    scripts["model-a"] = [text("Your report is saved.")]
    scripts["model-b"] = [text("आपकी रिपोर्ट दर्ज हो गई है।")]
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
            {"toolUse": {"toolUseId": "t1", "name": "save_report", "input": GOOD_ARGS}}]}},
         "stopReason": "tool_use", **usage},
        {"output": {"message": {"role": "assistant", "content": [{"text": "Saved."}]}},
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
    assert runner.reply(COMPLAINT, ctx, []) == "Saved."
    assert ctx.saved.extracted_by == "agent:deepseek.v3-v1:0"
