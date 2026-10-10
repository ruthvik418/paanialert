"""Provider order: Bedrock first, then Claude / Gemini only when their key is stored."""
import agent.runner as runner


def test_only_bedrock_without_keys(monkeypatch):
    monkeypatch.setattr(runner, "_stored_key", lambda name: None)
    assert all(label.startswith("bedrock:") for label in runner.candidates())


def test_keys_add_claude_then_gemini_after_bedrock(monkeypatch):
    monkeypatch.setattr(runner, "_stored_key", lambda name: "test-key")
    labels = runner.candidates()
    assert labels[: len(runner.MODEL_IDS)] == [f"bedrock:{m}" for m in runner.MODEL_IDS]
    assert labels[-2:] == [f"anthropic:{runner.CLAUDE_MODEL}", f"gemini:{runner.GEMINI_MODEL}"]


def test_build_makes_the_right_model_objects(monkeypatch):
    from strands.models.anthropic import AnthropicModel
    from strands.models.gemini import GeminiModel

    monkeypatch.setattr(runner, "_stored_key", lambda name: "test-key")
    assert isinstance(runner.build("gemini:gemini-2.5-flash"), GeminiModel)
    assert isinstance(runner.build("anthropic:claude-haiku-5-5"), AnthropicModel)
