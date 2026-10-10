"""Reads one incoming message with a model, saves the report, and builds the reply. Owner: B.

Extraction and conversation are separate:
1. A model fills ReportFields through Strands structured output (a forced tool
   call), so it can't chat its way past saving.
2. Code decides whether that's a complaint, saves it with save_extracted, and
   builds the reply from prompts.py: what was understood, ADVICE, and
   ASK_LOCATION if there's no pin.
3. Anything else (greetings, questions) gets a short model reply, or WELCOME.

Order tried: the Bedrock models in MODEL_IDS, then Claude and Gemini through
their own APIs, but only if their key is stored in SSM (/paanialert/
anthropic_api_key, /paanialert/gemini_api_key). A model that errors or returns
no fields is skipped for the next one. If none works, the caller falls back to
keyword extraction (agent/fallback.py), so a complaint is never lost.

MODEL_ENDPOINT picks how Bedrock models are called:
- mantle (default): the OpenAI-compatible bedrock-mantle endpoint in
  MANTLE_REGION, authenticated with short-lived tokens signed from the worker's
  IAM role (bedrock-mantle:CreateInference, CallWithBearerToken). This is what
  the Bedrock console playground uses, and it works on our account.
- runtime: bedrock-runtime Converse in BEDROCK_REGION, optionally through
  BEDROCK_ROLE_ARN in another account (see docs/bedrock-access.md).
"""
from __future__ import annotations

import logging
import os
import re
import time

import boto3
from pydantic import BaseModel, Field
from strands import Agent
from strands.models import BedrockModel
from strands.models.openai import OpenAIModel

from agent.prompts import (ADVICE, ASK_LOCATION, CHAT_PROMPT, CONFIRM, EXTRACTION_PROMPT, FIELD_LABELS,
                           LANGUAGES, WELCOME)
from agent.reports import TurnContext, save_extracted
from common.config import secret
from common.models import Colour, Smell, Source, Taste

log = logging.getLogger(__name__)

MODEL_ENDPOINT = os.environ.get("MODEL_ENDPOINT", "mantle").strip().lower()
# Mantle: Qwen3 235B saved the most of our 50 test messages; Qwen3 VL also reads images, for when
# photos are sent to the model. Override with the ModelIds stack parameter.
DEFAULT_MODEL_IDS = {
    "mantle": "qwen.qwen3-235b-a22b-2507,qwen.qwen3-vl-235b-a22b-instruct",
    "runtime": "us.meta.llama4-maverick-17b-instruct-v1:0,deepseek.v3-v1:0",
}[MODEL_ENDPOINT]
MODEL_IDS = [m.strip() for m in os.environ.get("MODEL_IDS", DEFAULT_MODEL_IDS).split(",") if m.strip()]
MODEL_ID = MODEL_IDS[0]
MANTLE_REGION = os.environ.get("MANTLE_REGION", "ap-south-1")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "us-west-2")
BEDROCK_ROLE_ARN = os.environ.get("BEDROCK_ROLE_ARN", "")
# Open models on Bedrock handle tool calls more reliably without streaming.
STREAMING = os.environ.get("BEDROCK_STREAMING", "false").lower() == "true"
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

_UNSAFE_WORD = re.compile(r"\b(safe|surakshit)\b|सुरक्षित", re.I)
# A chat reply must not tell the person a report was saved: only code saves reports now.
_CLAIMS_SAVED = re.compile(
    r"\b(saved|recorded|registered|logged|save (ho|kar)\w*|darj|note kar\w*)\b|दर्ज|सेव|नोट कर", re.I
)
_session_cache: dict[str, object] = {}
_key_checks: dict[str, tuple[float, str | None]] = {}


class AgentUnavailable(Exception):
    pass


class ReportFields(BaseModel):
    """The water complaint in one resident's message. Unknown or null for anything the message doesn't say.

    Every field is required (but may be unknown/null): when a model's tool-call JSON doesn't parse, Strands
    passes {} and this must fail validation, not read as "nothing wrong".
    """

    smell: Smell = Field(..., description=(
        "sewage for any bad or foul smell (badboo, badbu, naali/gutter jaisi, बदबू, दुर्गंध, stink); "
        "chemical for chlorine, medicine (dawai, दवा), kerosene or petrol; other for a strange smell that is "
        "none of those; none only if they say there is no smell"))
    colour: Colour = Field(..., description=(
        "yellow (peela, पीला); brown (bhura, matmaila, भूरा, मटमैला); black (kala, काला); "
        "cloudy for dirty, muddy or with particles (ganda, gandla, mitti, kachra, गंदा, कचरा, cloudy); "
        "clear only if they say it looks clean (saaf, साफ, rang theek)"))
    taste: Taste = Field(..., description=(
        "salty (khara, namkeen, खारा); bad for bitter or any other bad taste (kadwa, swad kharab); "
        "normal only if they say the taste is fine"))
    since_days: int | None = Field(..., ge=0, description=(
        "How many days it has been happening: 0 for today, this morning or 'aaj subah se'; 1 for "
        "yesterday or 'kal se'; 7 for a week or 'hafte se'; the number for 'N din se' / 'N days'. "
        "null if they don't say when it started"))
    sick_count: int | None = Field(..., ge=0, description=(
        "People at home who are sick: the number they give, or 1 if someone is sick and no number is "
        "given. 0 only if they say nobody is sick (koi bimar nahi, dast nahi hai, nobody is sick). "
        "null if sickness isn't mentioned at all"))
    symptoms: list[str] = Field(..., description=(
        "In English, e.g. diarrhoea, vomiting, fever, stomach pain; empty if nobody is sick"))
    source: Source = Field(..., description="pipe for tap or supply water (nal, supply), borewell, tanker")
    landmark: str | None = Field(..., description="A place they name, if any")
    clears_quickly: bool | None = Field(..., description="true if the water clears after running a few minutes")

    def is_complaint(self) -> bool:
        return any(v != "unknown" for v in (self.smell, self.colour, self.taste)) or (self.sick_count or 0) > 0


def _boto_session() -> boto3.Session:
    if not BEDROCK_ROLE_ARN:
        return boto3.Session(region_name=BEDROCK_REGION)
    cached = _session_cache.get("session")
    if cached and _session_cache.get("expires", 0) > time.time() + 300:
        return cached  # type: ignore[return-value]
    creds = boto3.client("sts").assume_role(
        RoleArn=BEDROCK_ROLE_ARN, RoleSessionName="paanialert-worker"
    )["Credentials"]
    session = boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
        region_name=BEDROCK_REGION,
    )
    _session_cache.update(session=session, expires=creds["Expiration"].timestamp())
    return session


def model(model_id: str) -> BedrockModel | OpenAIModel:
    if MODEL_ENDPOINT == "mantle":
        # A short-lived bearer token is signed from the worker's own IAM role on every request, so
        # there is no stored key. No retries and a short timeout: a slow model is skipped for the
        # next one, and the whole turn must fit in the worker's 120 s.
        return OpenAIModel(
            client_args={"timeout": 15, "max_retries": 0},
            bedrock_mantle_config={"region": MANTLE_REGION},
            model_id=model_id, stream=STREAMING, params={"temperature": 0.2, "max_tokens": 600},
        )
    return BedrockModel(boto_session=_boto_session(), model_id=model_id, temperature=0.2,
                        max_tokens=600, streaming=STREAMING)


def _stored_key(name: str) -> str | None:
    """Our own API key for a non-AWS provider, from SSM. A missing key is re-checked every 5 minutes."""
    checked = _key_checks.get(name)
    if checked and checked[0] > time.time() - 300:
        return checked[1]
    try:
        value = secret(name)
    except Exception:
        value = None
    _key_checks[name] = (time.time(), value)
    return value


def candidates() -> list[str]:
    """Model labels ("provider:model") in the order to try them."""
    found = [f"bedrock:{m}" for m in MODEL_IDS]
    if _stored_key("anthropic_api_key"):
        found.append(f"anthropic:{CLAUDE_MODEL}")
    if _stored_key("gemini_api_key"):
        found.append(f"gemini:{GEMINI_MODEL}")
    return found


def build(label: str):
    provider, model_id = label.split(":", 1)
    if provider == "bedrock":
        return model(model_id)
    if provider == "anthropic":
        from strands.models.anthropic import AnthropicModel
        return AnthropicModel(client_args={"api_key": _stored_key("anthropic_api_key")},
                              model_id=model_id, max_tokens=600, params={"temperature": 0.2})
    from strands.models.gemini import GeminiModel
    return GeminiModel(client_args={"api_key": _stored_key("gemini_api_key")},
                       model_id=model_id, params={"temperature": 0.2, "max_output_tokens": 600})


def _history(turns: list[dict[str, str]]) -> list[dict]:
    """Rebuild a clean user/assistant alternation for the model from stored turns."""
    messages: list[dict] = []
    for turn in turns:
        role = turn.get("role")
        if role not in ("user", "assistant") or not turn.get("text"):
            continue
        if not messages and role != "user":
            continue
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"][0]["text"] += "\n" + turn["text"]
        else:
            messages.append({"role": role, "content": [{"text": turn["text"]}]})
    if messages and messages[-1]["role"] == "user":
        messages.pop()  # the new message is added by the call itself
    return messages


def guard(text: str, lang: str) -> str:
    """Last line of defence: never let a reply call the water safe."""
    if not _UNSAFE_WORD.search(text):
        return text
    kept = [s for s in re.split(r"(?<=[.!?।])\s+", text) if not _UNSAFE_WORD.search(s)]
    return (" ".join(kept) + " " + ADVICE.get(lang, ADVICE["en"])).strip()


def extract_fields(text: str, label: str) -> ReportFields:
    """One forced structured-output call: the model must fill ReportFields."""
    agent = Agent(model=build(label), system_prompt=EXTRACTION_PROMPT, callback_handler=None)
    result = agent(text, structured_output_model=ReportFields)
    if not isinstance(result.structured_output, ReportFields):
        raise ValueError("no structured output")
    return result.structured_output


def confirmation(fields: ReportFields, lang: str) -> str:
    """One line saying what was understood, e.g. "✅ Report saved: yellow water, sewage smell, for 2 days."."""
    parts = [FIELD_LABELS[name][getattr(fields, name)][lang]
             for name in ("colour", "smell", "taste") if getattr(fields, name) in FIELD_LABELS[name]]
    for name in ("since_days", "sick_count"):
        n = getattr(fields, name)
        if n is not None:
            labels = FIELD_LABELS[name]
            parts.append(labels[n][lang] if n in labels else labels["n"][lang].format(n=n))
    return CONFIRM[lang].format(summary=", ".join(parts))


def _chat(label: str, prompt: str, turns: list[dict[str, str]], lang: str) -> str:
    """A short reply to a message that isn't a complaint; WELCOME if the model can't give a clean one."""
    try:
        agent = Agent(model=build(label), system_prompt=CHAT_PROMPT, messages=_history(turns), callback_handler=None)
        answer = str(agent(prompt)).strip()
    except Exception as exc:
        log.warning("chat reply from %s failed: %s: %s", label, type(exc).__name__, str(exc)[:300])
        return WELCOME[lang]
    if not answer or _CLAIMS_SAVED.search(answer):
        return WELCOME[lang]
    return guard(answer, lang)


def reply(text: str, ctx: TurnContext, turns: list[dict[str, str]]) -> str:
    lang = ctx.lang if ctx.lang in LANGUAGES else "en"
    for label in candidates():
        try:
            fields = extract_fields(text, label)
            break
        except Exception as exc:
            log.warning("model %s failed: %s: %s", label, type(exc).__name__, str(exc)[:300])
    else:
        raise AgentUnavailable("no model answered")

    if not fields.is_complaint():
        log.info("answered by %s (not a complaint)", label)
        return _chat(label, f"{text} [Reply in {LANGUAGES[lang]}]", turns, lang)

    model_id = label.split(":", 1)[1]
    report = save_extracted(ctx, fields.model_dump(), extracted_by=f"agent:{model_id}")
    log.info("answered by %s and saved a report", label)
    parts = [confirmation(fields, lang), ADVICE[lang]]
    if report.lat is None:
        parts.append(ASK_LOCATION[lang])
    return "\n\n".join(parts)
