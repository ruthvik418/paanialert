"""Handles one queued WhatsApp message: understand it, save it, reply. Owner: B.

Location pins are handled here, not by the model: a pin attaches to the
person's last report if it has no location yet, otherwise it is kept for their
next report.
"""
from __future__ import annotations

import json
import logging

from agent import fallback, prompts
from agent.media import save_media
from agent.reports import TurnContext, save_extracted
from agent.runner import AgentUnavailable, reply as agent_reply
from common import db
from common.geo import geohash6
from common.hashing import phone_hash
from common.twilio_send import send_whatsapp

log = logging.getLogger()
log.setLevel(logging.INFO)

STOP_WORDS = {"stop", "unsubscribe", "band karo", "बंद करो"}


def handler(event, context):
    for record in event["Records"]:
        handle(json.loads(record["body"]))


def handle(msg: dict) -> str:
    sender = msg["From"]
    text = (msg.get("Body") or "").strip()
    ph = phone_hash(sender)
    state = db.get_session(ph)
    turns = state.get("turns", [])
    lang = fallback.detect_lang(text) if text else state.get("lang", "hinglish")
    lat, lon = _float(msg.get("Latitude")), _float(msg.get("Longitude"))

    if text.lower() in STOP_WORDS:
        db.delete_subscriber(ph)
        answer = prompts.UNSUBSCRIBED[lang]
    elif lat is not None and lon is not None:
        answer = _handle_pin(state, lat, lon, lang)
    else:
        answer = _handle_message(msg, text, ph, state, turns, lang)

    send_whatsapp(sender, answer)
    if text:
        turns.append({"role": "user", "text": text})
    turns.append({"role": "assistant", "text": answer})
    state.update(turns=turns, lang=lang)
    db.put_session(ph, state)
    return answer


def _handle_pin(state: dict, lat: float, lon: float, lang: str) -> str:
    report = db.get_report(state["last_report_id"]) if state.get("last_report_id") else None
    if report and report.lat is None:
        report.lat, report.lon, report.geohash6 = lat, lon, geohash6(lat, lon)
        db.put_report(report)
        log.info("attached pin to report %s", report.report_id)
        return prompts.LOCATION_SAVED[lang] + "\n\n" + prompts.ADVICE[lang]
    state["pending_location"] = [lat, lon]
    return prompts.ASK_COMPLAINT[lang]


def _handle_message(msg: dict, text: str, ph: str, state: dict, turns: list, lang: str) -> str:
    pending = state.get("pending_location")
    photo_key, audio_key = save_media(msg, msg.get("MessageSid") or "media")
    ctx = TurnContext(
        phone_hash=ph, lang=lang,
        lat=pending[0] if pending else None, lon=pending[1] if pending else None,
        photo_key=photo_key, audio_key=audio_key,
    )

    if not text:
        if audio_key:
            return prompts.VOICE_PENDING[lang]
        text = "[photo of the water, no text]" if photo_key else ""

    try:
        answer = agent_reply(text, ctx, turns)
    except AgentUnavailable:
        answer = _keyword_reply(text, ctx)

    if ctx.saved:
        state["last_report_id"] = ctx.saved.report_id
        state.pop("pending_location", None)
        if ctx.saved.lat is None and "📍" not in answer:
            answer += "\n\n" + prompts.ASK_LOCATION[lang]
    return answer


def _keyword_reply(text: str, ctx: TurnContext) -> str:
    """Used only when no Bedrock model answers."""
    fields = fallback.extract(text)
    if not fallback.is_complaint(fields):
        return {
            "en": "Hi! I'm PaaniAlert. Tell me if your tap water smells, looks dirty or makes people sick, and I'll warn your neighbours early.",
            "hi": "नमस्ते! मैं PaaniAlert हूँ। अगर नल के पानी में बदबू है, गंदा है या लोग बीमार हो रहे हैं, तो बताइए।",
            "hinglish": "Namaste! Main PaaniAlert hoon. Agar nal ke paani mein badboo hai, ganda hai ya log bimar ho rahe hain, to batayiye.",
        }[ctx.lang]
    save_extracted(ctx, fields)
    thanks = {"en": "Thank you, your report is saved.", "hi": "धन्यवाद, आपकी शिकायत दर्ज हो गई।",
              "hinglish": "Shukriya, aapki report save ho gayi."}[ctx.lang]
    return thanks + "\n\n" + prompts.ADVICE[ctx.lang]


def _float(value) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None
