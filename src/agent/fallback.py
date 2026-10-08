"""Keyword extraction for when Bedrock is unavailable. Owner: B.

Much weaker than the agent, but it keeps reports, clusters and alerts working
if the model is throttled or blocked. Reports saved this way are still real.
"""
from __future__ import annotations

import re
from typing import Any

_DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_HINGLISH = re.compile(
    r"\b(paani|pani|hai|hain|nahi|nahin|nhi|mein|me|ka|ki|ko|se|aa raha|aa rha|ghar|kal|din|bachch\w*)\b",
    re.I,
)

_SMELL = [
    ("chemical", r"chlorine|chemical|kerosene|petrol|dawai"),
    ("sewage", r"badboo|badbu|badbo|bad smell|smell|stink|sewage|gutter|naali|nali|बदबू|गंदी बू|दुर्गंध"),
]
_COLOUR = [
    ("yellow", r"peela|pila|peeli|yellow|पीला|पीली"),
    ("brown", r"bhura|brown|matmaila|मटमैला|भूरा"),
    ("black", r"\bkala\b|kaala|black|काला"),
    ("cloudy", r"gandla|gadla|cloudy|dirty|ganda|gandi|muddy|mitti|kachra|गंदा|गंदी|धुंधला|मिट्टी|कचरा"),
]
_TASTE = [
    ("salty", r"khara|namkeen|salty|खारा|नमकीन"),
    ("bad", r"taste|swad|kadwa|bitter|स्वाद|कड़वा"),
]
_SICK = re.compile(
    r"dast|loose motion|diarrh\w*|ulti|vomit\w*|bimar|beemar|sick|\bill\b|fever|bukhar|pet dard|stomach|"
    r"दस्त|उल्टी|बीमार|बुखार|पेट दर्द",
    re.I,
)
_NEGATION = re.compile(r"\b(nahi|nahin|nhi|no|not|nobody|koi nahi)\b|नहीं|कोई नहीं", re.I)
_SYMPTOMS = [
    ("diarrhoea", r"dast|loose motion|diarrh|दस्त"),
    ("vomiting", r"ulti|vomit|उल्टी"),
    ("fever", r"fever|bukhar|बुखार"),
    ("stomach pain", r"pet dard|stomach|पेट दर्द"),
]
_DAYS = re.compile(r"(\d+)\s*(din|day|days|दिन)", re.I)


def detect_lang(text: str) -> str:
    if _DEVANAGARI.search(text):
        return "hi"
    if len(_HINGLISH.findall(text)) >= 2:
        return "hinglish"
    return "en"


def _first(pairs: list[tuple[str, str]], text: str, default: str = "unknown") -> str:
    for value, pattern in pairs:
        if re.search(pattern, text, re.I):
            return value
    return default


def _sick_count(text: str) -> int | None:
    match = _SICK.search(text)
    if not match:
        return None
    # A negation within a few words of the symptom ("dast nahi hai", "no one is sick") means nobody.
    window = text[max(0, match.start() - 25): match.end() + 25]
    return 0 if _NEGATION.search(window) else 1


def _since_days(text: str) -> int | None:
    match = _DAYS.search(text)
    if match:
        return int(match.group(1))
    lowered = text.lower()
    if re.search(r"kal se|since yesterday|yesterday|कल से", lowered):
        return 1
    if re.search(r"hafte|hafta|week|हफ्ते", lowered):
        return 7
    if re.search(r"aaj se|today|आज से", lowered):
        return 0
    return None


def extract(text: str) -> dict[str, Any]:
    """Best-effort fields from a message, in the same shape the agent's save_report takes."""
    sick = _sick_count(text)
    symptoms = [name for name, pattern in _SYMPTOMS if re.search(pattern, text, re.I)] if sick else []
    return {
        "smell": _first(_SMELL, text),
        "colour": _first(_COLOUR, text),
        "taste": _first(_TASTE, text),
        "since_days": _since_days(text),
        "sick_count": sick,
        "symptoms": symptoms,
    }


def is_complaint(fields: dict[str, Any]) -> bool:
    return any(fields[k] != "unknown" for k in ("smell", "colour", "taste")) or bool(fields["sick_count"])
