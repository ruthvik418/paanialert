"""Field extraction on its own, for scoring models (scripts/pick_model.py, eval_extraction.py). Owner: B.

Uses the same forced structured-output call as the bot (runner.extract_fields).
"""
from __future__ import annotations

import logging

from agent.runner import ReportFields, candidates, extract_fields

log = logging.getLogger(__name__)


def extract(text: str, label: str | None = None) -> ReportFields:
    """Extract with the given model label ("provider:model"), or the first one that answers."""
    for candidate in [label] if label else candidates():
        try:
            return extract_fields(text, candidate)
        except Exception:
            log.warning("extraction with %s failed", candidate, exc_info=True)
    raise RuntimeError("no model could extract")
