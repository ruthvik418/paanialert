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

_NUMBER_WORDS = {
    "ek": 1, "one": 1, "एक": 1, "do": 2, "two": 2, "दो": 2, "teen": 3, "three": 3, "तीन": 3,
    "char": 4, "chaar": 4, "four": 4, "चार": 4, "paanch": 5, "panch": 5, "five": 5, "पांच": 5, "पाँच": 5,
}
_NUM = r"(\d+|" + "|".join(_NUMBER_WORDS) + r")"

_SMELL = [
    ("none", r"\bno smell|smell nahi|badboo nahi|badbu nahi|बदबू नहीं|गंध नहीं"),
    ("chemical", r"chlorine|chemical|kerosene|petrol|dawai|\bdawa\b|दवा"),
    ("sewage", r"badboo|badbu|badbo|bdboo|bdbu|bad smell|stink|sewage|gutter|naali|nali|बदबू|गंदी बू|दुर्गंध"),
    ("other", r"smell|gandh|गंध"),
]
_COLOUR = [
    ("yellow", r"peela|pila|peeli|yellow|पीला|पीली"),
    ("brown", r"bhura|brown|matmaila|मटमैला|भूरा"),
    ("black", r"\bkala\b|kaala|black|काला"),
    ("cloudy", r"gandla|gadla|cloudy|dirty|ganda|gandi|\bgnda\b|muddy|mitti|kachra|गंदा|गंदी|धुंधला|मिट्टी|कचरा"),
    ("clear", r"\bsaaf\b|\bclear\b|\bclean\b|rang theek|साफ"),
]
_TASTE = [
    ("salty", r"\bkhara\b|namkeen|salty|खारा|नमकीन"),
    ("bad", r"taste|swad|kadwa|bitter|kharab|स्वाद|कड़वा"),
]
_SICK = re.compile(
    r"dast|lo+se motion|diarrh\w*|ulti|vomit\w*|bimar|beemar|sick|\bill\b|fever|bukhar|pet dard|stomach|"
    r"दस्त|उल्टी|बीमार|बुखार|पेट दर्द",
    re.I,
)
_NEGATION = re.compile(r"\b(nahi|nahin|nhi|no|not|nobody|koi nahi)\b|नहीं|कोई नहीं", re.I)
_SYMPTOMS = [
    ("diarrhoea", r"dast|lo+se motion|diarrh|दस्त"),
    ("vomiting", r"ulti|vomit|उल्टी"),
    ("fever", r"fever|bukhar|बुखार"),
    ("stomach pain", r"pet dard|stomach|पेट दर्द"),
]
_DAYS = re.compile(_NUM + r"\s*(din|day|days|दिन)", re.I)
_PEOPLE = re.compile(_NUM + r"\s*(log|logon|logo|people|persons|kids|children|bachch\w*|लोग|लोगों|बच्चे|बच्चों)", re.I)


def _number(token: str) -> int:
    return int(token) if token.isdigit() else _NUMBER_WORDS[token.lower()]


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
    if _NEGATION.search(window):
        return 0
    people = _PEOPLE.search(text)
    return _number(people.group(1)) if people else 1


def _since_days(text: str) -> int | None:
    match = _DAYS.search(text)
    if match:
        return _number(match.group(1))
    lowered = text.lower()
    if re.search(r"kal se|since yesterday|yesterday|कल से", lowered):
        return 1
    if re.search(r"hafte|hafta|week|हफ्ते", lowered):
        return 7
    if re.search(r"aaj|today|subah se|this morning|आज", lowered):
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
