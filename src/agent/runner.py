"""Runs the Strands agent on Amazon Bedrock for one incoming message. Owner: B.

Models are tried in MODEL_IDS order (comma-separated). A model counts as failed,
and the next one is tried, if it errors, makes a malformed save_report call, or
answers a complaint without saving it. If every model fails, the caller falls
back to keyword extraction (agent/fallback.py), so a complaint is never lost.

MODEL_ENDPOINT picks how models are called:
- mantle (default): the OpenAI-compatible bedrock-mantle endpoint in
  MANTLE_REGION, with the Bedrock API key in SSM /paanialert/bedrock_api_key.
  This is what the Bedrock console playground uses, and it works on our account.
- runtime: bedrock-runtime Converse in BEDROCK_REGION, optionally through
  BEDROCK_ROLE_ARN in another account (see docs/bedrock-access.md).
"""
from __future__ import annotations

import logging
import os
import re
import time

import boto3
from strands import Agent, tool
from strands.models import BedrockModel
from strands.models.openai import OpenAIModel

from agent import fallback
from agent.prompts import ADVICE, LANGUAGES, SYSTEM_PROMPT
from agent.reports import TurnContext, save_extracted
from common.config import secret

log = logging.getLogger(__name__)

MODEL_ENDPOINT = os.environ.get("MODEL_ENDPOINT", "mantle").strip().lower()
# Mantle: DeepSeek V3.1 was the fastest to pass our Hindi/Hinglish tool-call probe, then Qwen3 235B.
# Qwen3 VL also reads images, for when photos are sent to the model. Override with the ModelIds stack parameter.
DEFAULT_MODEL_IDS = {
    "mantle": "deepseek.v3.1,qwen.qwen3-235b-a22b-2507,qwen.qwen3-vl-235b-a22b-instruct",
    "runtime": "us.meta.llama4-maverick-17b-instruct-v1:0,deepseek.v3-v1:0",
}[MODEL_ENDPOINT]
MODEL_IDS = [m.strip() for m in os.environ.get("MODEL_IDS", DEFAULT_MODEL_IDS).split(",") if m.strip()]
MODEL_ID = MODEL_IDS[0]
MANTLE_REGION = os.environ.get("MANTLE_REGION", "ap-south-1")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "us-west-2")
BEDROCK_ROLE_ARN = os.environ.get("BEDROCK_ROLE_ARN", "")
# Open models on Bedrock handle tool calls more reliably without streaming.
STREAMING = os.environ.get("BEDROCK_STREAMING", "false").lower() == "true"

_UNSAFE_WORD = re.compile(r"\b(safe|surakshit)\b|सुरक्षित", re.I)
# A reply that tells the person their report is in, e.g. "Your report is saved" / "रिपोर्ट दर्ज हो गई".
_CLAIMS_SAVED = re.compile(
    r"\b(saved|recorded|registered|logged|save (ho|kar)\w*|darj|note kar\w*)\b|दर्ज|सेव|नोट कर", re.I
)
_session_cache: dict[str, object] = {}


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


def model(model_id: str) -> BedrockModel | OpenAIModel:
    if MODEL_ENDPOINT == "mantle":
        # No retries and a short timeout: a turn is ~2 requests per model, and three models must
        # fit in the worker's 120 s. A slow model is skipped for the next one instead.
        return OpenAIModel(
            client_args={"api_key": secret("bedrock_api_key"), "timeout": 15, "max_retries": 0,
                         "base_url": f"https://bedrock-mantle.{MANTLE_REGION}.api.aws/v1"},
            model_id=model_id, stream=STREAMING, params={"temperature": 0.2, "max_tokens": 600},
        )
    return BedrockModel(boto_session=_boto_session(), model_id=model_id, temperature=0.2,
                        max_tokens=600, streaming=STREAMING)


def _tools(ctx: TurnContext, model_id: str, problems: list[str]):
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
        fields = {
            "smell": smell, "colour": colour, "taste": taste, "since_days": since_days,
            "sick_count": sick_count, "symptoms": symptoms or [], "source": source,
            "landmark": landmark, "clears_quickly": clears_quickly,
        }
        # Strands calls the tool with no arguments when the model's JSON doesn't parse.
        if not fallback.is_complaint(fields) and since_days is None and source == "unknown" and not landmark:
            problems.append("save_report called with no fields (malformed tool call)")
            return "Error: no fields were received. Call save_report again with what the resident said."
        report = save_extracted(ctx, fields, extracted_by=f"agent:{model_id}")
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


def _tool_errors(messages: list[dict]) -> list[str]:
    """Tool results Strands marked as errors, e.g. arguments that failed the schema."""
    return [
        " ".join(c.get("text", "") for c in block["toolResult"].get("content", []))[:200] or "tool error"
        for m in messages for block in m.get("content", [])
        if "toolResult" in block and block["toolResult"].get("status") == "error"
    ]


def _problem(answer: str, text: str, ctx: TurnContext, problems: list[str]) -> str | None:
    """Why this model's turn can't be trusted, or None if it can."""
    if not answer:
        return "empty reply"
    if ctx.saved:
        return None
    if problems:
        return "; ".join(problems)
    if _CLAIMS_SAVED.search(answer):
        return "reply says the report was saved, but save_report was not called"
    if fallback.is_complaint(fallback.extract(text)):
        return "message is a complaint, but save_report was not called"
    return None


def reply(text: str, ctx: TurnContext, turns: list[dict[str, str]]) -> str:
    notes = []
    if ctx.lat is not None:
        notes.append("[the location is already known]")
    if ctx.photo_key:
        notes.append("[the person attached a photo]")
    notes.append(f"[Reply in {LANGUAGES.get(ctx.lang, LANGUAGES['en'])}]")
    prompt = (text + " " + " ".join(notes)).strip()

    for model_id in MODEL_IDS:
        problems: list[str] = []
        try:
            agent = Agent(
                model=model(model_id),
                system_prompt=SYSTEM_PROMPT,
                tools=_tools(ctx, model_id, problems),
                messages=_history(turns),
                callback_handler=None,
            )
            answer = str(agent(prompt)).strip()
            problems += _tool_errors(agent.messages)
        except Exception as exc:
            log.warning("model %s failed: %s: %s", model_id, type(exc).__name__, str(exc)[:300])
            continue
        problem = _problem(answer, text, ctx, problems)
        if problem is None:
            log.info("model %s answered%s", model_id, " and saved a report" if ctx.saved else "")
            return guard(answer, ctx.lang)
        log.warning("model %s failed: %s", model_id, problem)
    raise AgentUnavailable("no Bedrock model answered")
