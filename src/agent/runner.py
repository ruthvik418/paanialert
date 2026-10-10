"""Runs the Strands agent for one incoming message. Owner: B.

Order tried: the Bedrock models in MODEL_IDS, then Claude and Gemini through
their own APIs, but only if their key is stored in SSM (/paanialert/
anthropic_api_key, /paanialert/gemini_api_key). If nothing answers, the
caller falls back to keyword extraction (agent/fallback.py). So once AWS
unblocks Bedrock, it takes over again with no change.

If Bedrock is blocked on our account, set BEDROCK_ROLE_ARN to a role in a
teammate's account that allows bedrock:InvokeModel and trusts our account
(see docs/bedrock-access.md). Only the model calls go there; everything else
stays in our account.
"""
from __future__ import annotations

import logging
import os
import re
import time

import boto3
from strands import Agent, tool
from strands.models import BedrockModel

from agent.prompts import ADVICE, LANGUAGES, SYSTEM_PROMPT
from agent.reports import TurnContext, save_extracted

log = logging.getLogger(__name__)

# Llama 4 Maverick: officially supports Hindi, reads images (water photos, TDS meters), fast.
# DeepSeek V3.1: stronger text reasoning, no images. Override with the ModelIds stack parameter.
DEFAULT_MODEL_IDS = "us.meta.llama4-maverick-17b-instruct-v1:0,deepseek.v3-v1:0"
MODEL_IDS = [m.strip() for m in os.environ.get("MODEL_IDS", DEFAULT_MODEL_IDS).split(",") if m.strip()]
MODEL_ID = MODEL_IDS[0]
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "us-west-2")
BEDROCK_ROLE_ARN = os.environ.get("BEDROCK_ROLE_ARN", "")
# Open models on Bedrock handle tool calls more reliably without streaming.
STREAMING = os.environ.get("BEDROCK_STREAMING", "false").lower() == "true"
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

_UNSAFE_WORD = re.compile(r"\b(safe|surakshit)\b|सुरक्षित", re.I)
_session_cache: dict[str, object] = {}
_key_checks: dict[str, tuple[float, str | None]] = {}


class AgentUnavailable(Exception):
    pass


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


def model(model_id: str) -> BedrockModel:
    return BedrockModel(boto_session=_boto_session(), model_id=model_id, temperature=0.2,
                        max_tokens=600, streaming=STREAMING)


def _stored_key(name: str) -> str | None:
    """Our own API key for a non-AWS provider, from SSM. A missing key is re-checked every 5 minutes."""
    checked = _key_checks.get(name)
    if checked and checked[0] > time.time() - 300:
        return checked[1]
    try:
        from common.config import secret
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


def _tools(ctx: TurnContext):
    @tool
    def save_report(
        smell: str = "unknown",
        colour: str = "unknown",
        taste: str = "unknown",
        since_days: int | None = None,
        sick_count: int | None = None,
        symptoms: list[str] | None = None,
        source: str = "unknown",
        landmark: str | None = None,
        clears_quickly: bool | None = None,
    ) -> str:
        """Save the resident's water complaint. Call once, as soon as you know what is wrong.

        Args:
            smell: one of none, sewage, chemical, other, unknown
            colour: one of clear, yellow, brown, black, cloudy, unknown
            taste: one of normal, bad, salty, unknown
            since_days: how many days it has been happening, if said
            sick_count: people sick at home; 0 if they said nobody is sick; empty if not said
            symptoms: e.g. diarrhoea, vomiting, fever; empty if nobody is sick
            source: one of pipe, borewell, tanker, unknown
            landmark: a place they mentioned, if any
            clears_quickly: true if the water clears after a few minutes of running
        """
        if ctx.saved:
            return "Already saved for this message."
        report = save_extracted(ctx, {
            "smell": smell, "colour": colour, "taste": taste, "since_days": since_days,
            "sick_count": sick_count, "symptoms": symptoms or [], "source": source,
            "landmark": landmark, "clears_quickly": clears_quickly,
        })
        has_location = report.lat is not None
        return f"Saved. Location {'known' if has_location else 'missing: ask for a location pin'}."

    return [save_report]


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


def reply(text: str, ctx: TurnContext, turns: list[dict[str, str]]) -> str:
    notes = []
    if ctx.lat is not None:
        notes.append("[the location is already known]")
    if ctx.photo_key:
        notes.append("[the person attached a photo]")
    notes.append(f"[Reply in {LANGUAGES.get(ctx.lang, LANGUAGES['en'])}]")
    prompt = (text + " " + " ".join(notes)).strip()

    for label in candidates():
        try:
            agent = Agent(
                model=build(label),
                system_prompt=SYSTEM_PROMPT,
                tools=_tools(ctx),
                messages=_history(turns),
                callback_handler=None,
            )
            answer = str(agent(prompt)).strip()
            if answer:
                log.info("answered by %s", label)
                return guard(answer, ctx.lang)
        except Exception:
            log.exception("model %s failed", label)
    raise AgentUnavailable("no model answered")
