"""Handles one queued WhatsApp message: understand it, save it, reply. Owner: B.

Language: replies are in Hindi until the person picks another language. New
people get a menu (1 हिंदी, 2 English, 3 Hinglish) after their first reply;
"भाषा", "bhasha" or "language" shows it again. The choice is saved per phone
and also used for their alerts.

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
MENU_WORDS = {"language", "lang", "bhasha", "bhaasha", "भाषा", "भाषा बदलें", "change language", "bhasha badlo"}
LANGUAGE_WORDS = {
    "hindi": "hi", "हिंदी": "hi", "हिन्दी": "hi",
    "english": "en", "angrezi": "en", "अंग्रेज़ी": "en", "अंग्रेजी": "en",
    "hinglish": "hinglish", "roman hindi": "hinglish",
}
MENU_NUMBERS = {"1": "hi", "2": "en", "3": "hinglish", "१": "hi", "२": "en", "३": "hinglish"}


def handler(event, context):
    for record in event["Records"]:
        handle(json.loads(record["body"]))


def handle(msg: dict) -> str:
    sender = msg["From"]
    text = (msg.get("Body") or "").strip()
    ph = phone_hash(sender)
    state = db.get_session(ph)
    turns = state.get("turns", [])
    chosen = db.get_language(ph)
    lang = chosen or prompts.DEFAULT_LANG
    first_contact = chosen is None and not turns
    lat, lon = _float(msg.get("Latitude")), _float(msg.get("Longitude"))
    command = text.lower().strip(" .!")
    choice = LANGUAGE_WORDS.get(command) or (MENU_NUMBERS.get(command) if state.get("awaiting_language") else None)
    show_menu = False

    if choice:
        db.set_language(ph, choice)
        db.update_subscriber_lang(ph, choice)
        lang = choice
        answer = prompts.LANGUAGE_SET[lang]
    elif command in MENU_WORDS:
        answer, show_menu = prompts.LANGUAGE_MENU, True
    elif command in STOP_WORDS:
        db.delete_subscriber(ph)
        answer = prompts.UNSUBSCRIBED[lang]
    elif lat is not None and lon is not None:
        answer = _handle_pin(state, lat, lon, lang)
    else:
        answer = _handle_message(msg, text, ph, state, turns, lang)

    if first_contact and not choice and not show_menu:
        answer += "\n\n" + prompts.LANGUAGE_MENU
        show_menu = True
    # Only a reply right after the menu counts as a choice, so "2" can still mean "2 people sick".
    if show_menu:
        state["awaiting_language"] = True
    else:
        state.pop("awaiting_language", None)

    send_whatsapp(sender, answer)
    if text:
        turns.append({"role": "user", "text": text})
    turns.append({"role": "assistant", "text": answer})
    state.update(turns=turns)
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
        phone_hash=ph, lang=lang, msg_lang=fallback.detect_lang(text) if text else None,
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
        return prompts.WELCOME[ctx.lang]
    save_extracted(ctx, fields)
    return prompts.REPORT_SAVED[ctx.lang] + "\n\n" + prompts.ADVICE[ctx.lang]


def _float(value) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None
