"""Field extraction without tools, for the 50-message accuracy test. Owner: B."""
from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel, Field
from strands import Agent

from agent.prompts import EXTRACT_PROMPT
from agent.runner import build, candidates

log = logging.getLogger(__name__)


class ExtractedReport(BaseModel):
    smell: Literal["none", "sewage", "chemical", "other", "unknown"] = "unknown"
    colour: Literal["clear", "yellow", "brown", "black", "cloudy", "unknown"] = "unknown"
    taste: Literal["normal", "bad", "salty", "unknown"] = "unknown"
    since_days: int | None = Field(default=None, description="Days it has been happening, if said")
    sick_count: int | None = Field(default=None, description="0 if they say nobody is sick; empty if not said")
    symptoms: list[str] = Field(default_factory=list)
    source: Literal["pipe", "borewell", "tanker", "unknown"] = "unknown"


def extract(text: str, label: str | None = None) -> ExtractedReport:
    """Extract with the given model label ("provider:model"), or the first one that answers."""
    for candidate in [label] if label else candidates():
        try:
            agent = Agent(model=build(candidate), callback_handler=None)
            return agent.structured_output(ExtractedReport, EXTRACT_PROMPT + text)
        except Exception:
            log.warning("extraction with %s failed", candidate, exc_info=True)
    raise RuntimeError("no model could extract")
