"""Model order: only Amazon Bedrock models, in ModelIds order (keyword fallback is in agent/fallback.py)."""
import pytest

import agent.runner as runner


def test_only_bedrock_models_in_order():
    assert runner.candidates() == [f"bedrock:{m}" for m in runner.MODEL_IDS]


def test_other_providers_are_refused():
    with pytest.raises(ValueError):
        runner.build("gemini:gemini-2.5-flash")
