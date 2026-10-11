"""Handles one queued WhatsApp message: understand it, save it, reply. Owner: B.

Language: replies are in English until the person picks another language. New
people get a menu (1 English, 2 हिंदी, 3 Hinglish) after their first reply;
"भाषा", "bhasha" or "language" shows it again. The choice is saved per phone
and also used for their alerts.

Alerts: once a report has a location, the bot offers alerts for that area;
YES / haan adds the person to Subscribers, NO stops it asking, STOP removes them.

Duplicates: Twilio retries webhooks and SQS can deliver twice, so a MessageSid
that was already handled is skipped (ProcessedMessages table, 2-day TTL).

Location pins are handled here, not by the model: a pin attaches to the
person's last report if it has no location yet, otherwise it is kept for their
next report.

Voice: a voice note (WhatsApp) or recording (web app) is transcribed with
Amazon Transcribe (agent/voice.py) and then handled exactly like typed text.
The reply starts with "I heard: …", the report's text is the transcript
marked with 🎤, and input_type is "voice". If nothing usable comes back, the
person is asked to type (VOICE_PENDING) and nothing is saved.

The web report app (POST /app/report, api/app_report.py) calls handle() too,
with channel "app", From "app:<device id>" and its own send function. App
messages always carry text and a location together and have their own language
picker, so they skip the menu, commands, pins, contacts and alert offers.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Callable

from agent import fallback, prompts, voice
from agent.media import save_media
from agent.reports import TurnContext, save_extracted
from agent.runner import AgentUnavailable, reply as agent_reply
from common import db
from common.geo import geohash6
from common.hashing import mask_number, normalise_number, phone_hash
from common.places import area_name
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
MENU_NUMBERS = {"1": "en", "2": "hi", "3": "hinglish", "१": "en", "२": "hi", "३": "hinglish"}
YES_WORDS = {"yes", "y", "yeah", "ok", "okay", "haan", "haa", "ha", "han", "hn", "ji", "haan ji", "हाँ", "हां", "जी"}
NO_WORDS = {"no", "n", "nahi", "nahin", "nhi", "na", "नहीं", "ना"}
# Audio file extension (see agent/media.py and api/app_report.py) to Amazon Transcribe MediaFormat.
TRANSCRIBE_FORMATS = {"ogg": "ogg", "webm": "webm", "mp3": "mp3", "m4a": "m4a", "amr": "amr"}
MAX_RECEIVES = 3   # IncomingQueue's maxReceiveCount in template.yaml


def handler(event, context):
    for record in event["Records"]:
        msg = json.loads(record["body"])
        if msg.get("RequestId"):
            last_try = int((record.get("attributes") or {}).get("ApproximateReceiveCount") or 1) >= MAX_RECEIVES
            handle_app_request(msg, last_try)
        else:
            handle(msg)


def handle_app_request(msg: dict, last_try: bool = True) -> None:
    """A web voice report queued by POST /app/report. The result goes to AppRequests for GET /app/report/{id}."""
    request_id = msg["RequestId"]
    if (db.get_app_request(request_id) or {}).get("status") == "done":
        return   # SQS delivered it twice
    ph = phone_hash(msg["From"])
    before = db.get_session(ph).get("last_report_id")
    try:
        answer = handle(msg, send=lambda to, body: None)
    except Exception:
        if last_try:
            db.finish_app_request(request_id, "failed")
        raise
    if not answer:
        return   # the MessageSid was already handled
    after = db.get_session(ph).get("last_report_id")
    saved = bool(after) and after != before
    db.finish_app_request(request_id, "done", reply=answer, transcript=msg.get("Transcript"),
                          saved=saved, report_id=after if saved else None)
    log.info("app voice report done: saved=%s heard=%s", saved, bool(msg.get("Transcript")))


def handle(msg: dict, send: Callable[[str, str], object] | None = None) -> str:
    """Handle one message and send the answer with send(to, body); WhatsApp (send_whatsapp) by default."""
    sid = msg.get("MessageSid")
    if sid and not db.claim_message(sid):
        log.info("skipped duplicate message sid=%s", sid)
        return ""
    try:
        return _handle(msg, send or send_whatsapp)
    except Exception:
        if sid:
            db.release_message(sid)   # let the SQS retry handle it
        raise


def _handle(msg: dict, send: Callable[[str, str], object]) -> str:
    sender = msg["From"]
    app = msg.get("channel") == "app"
    text = (msg.get("Body") or "").strip()
    ph = phone_hash(sender)
    state = db.get_session(ph)
    turns = state.get("turns", [])
    chosen = db.get_language(ph)
    lang = chosen or prompts.DEFAULT_LANG
    first_contact = chosen is None and not turns and not app
    lat, lon = _float(msg.get("Latitude")), _float(msg.get("Longitude"))
    command = text.lower().strip(" .!")
    choice = LANGUAGE_WORDS.get(command) or (MENU_NUMBERS.get(command) if state.get("awaiting_language") else None)
    show_menu = False
    # Like the language menu, YES/NO only counts as the answer right after we asked.
    subscribe_cell = state.pop("awaiting_subscribe", None)

    if app:
        answer = _handle_message(msg, text, ph, state, turns, lang)
    elif subscribe_cell and command in YES_WORDS:
        db.put_subscriber(ph, sender, subscribe_cell, lang)
        log.info("subscribed one phone in cell %s", subscribe_cell)
        answer = prompts.SUBSCRIBED[lang]
    elif subscribe_cell and command in NO_WORDS:
        state["subscribe_declined"] = True
        answer = prompts.NOT_SUBSCRIBED[lang]
    elif choice:
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

    send(sender, answer)
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
        report.area = area_name(lat, lon)
        db.put_report(report)
        log.info("attached pin to report %s", report.report_id)
        return prompts.LOCATION_SAVED[lang] + "\n\n" + prompts.ADVICE[lang] + _offer_alerts(state, report, lang)
    state["pending_location"] = [lat, lon]
    return prompts.ASK_COMPLAINT[lang]


def _offer_alerts(state: dict, report, lang: str) -> str:
    """Once a report has a location, offer alerts for that area, unless they already said yes or no."""
    if report.geohash6 is None or state.get("subscribe_declined") or db.get_subscriber(report.phone_hash):
        return ""
    state["awaiting_subscribe"] = report.geohash6
    return "\n\n" + prompts.ASK_SUBSCRIBE[lang]


def _handle_message(msg: dict, text: str, ph: str, state: dict, turns: list, lang: str) -> str:
    app = msg.get("channel") == "app"
    if app:   # location, photo and recording come with the message, already checked by api/app_report.py
        pending = [_float(msg.get("Latitude")), _float(msg.get("Longitude"))]
        photo_key, audio_key = msg.get("PhotoKey") or None, msg.get("AudioKey") or None
    else:
        pending = state.get("pending_location")
        photo_key, audio_key = save_media(msg, msg.get("MessageSid") or "media")

    heard, msg_lang = None, fallback.detect_lang(text) if text else None
    if audio_key:
        result = _transcribe(audio_key)
        if result is None and not text:
            return prompts.VOICE_PENDING[lang]
        if result:
            heard, code = result
            msg["Transcript"] = heard   # handle_app_request returns it to the web page
            if msg.get("RequestId"):     # the web page ticks off "Listening" and shows "Reading your report"
                db.finish_app_request(msg["RequestId"], "reading")
            msg_lang = "hi" if code.startswith("hi") else "en"
            # Someone who speaks Hindi and hasn't picked a language yet is answered in Hindi.
            if msg_lang == "hi" and not app and db.get_language(ph) is None:
                lang = "hi"
            text = f"{heard}. {text}" if text else heard
    ctx = TurnContext(
        phone_hash=ph, lang=lang, msg_lang=msg_lang,
        lat=pending[0] if pending else None, lon=pending[1] if pending else None,
        photo_key=photo_key, audio_key=audio_key,
        text=(prompts.VOICE_MARK + text if heard else text) or None,
        profile_name=(msg.get("ProfileName") or "").strip()[:80] or None,
        phone_masked=None if app else mask_number(msg["From"]),
        channel="app" if app else "whatsapp",
        input_type="voice" if heard else "text",
    )

    if not text:
        text = "[photo of the water, no text]" if photo_key else ""

    try:
        answer = agent_reply(text, ctx, turns)
    except AgentUnavailable:
        answer = _keyword_reply(text, ctx)

    if ctx.saved and app:
        state["last_report_id"] = ctx.saved.report_id   # no contact to keep and no alerts to offer
    elif ctx.saved:
        db.put_contact(ph, normalise_number(msg["From"]))
        state["last_report_id"] = ctx.saved.report_id
        state.pop("pending_location", None)
        if ctx.saved.lat is None and "📍" not in answer:
            answer += "\n\n" + prompts.ASK_LOCATION[lang]
        else:
            answer += _offer_alerts(state, ctx.saved, lang)
    if heard:
        shown = heard if len(heard) <= prompts.HEARD_CHARS else heard[:prompts.HEARD_CHARS].rstrip() + "…"
        answer = prompts.HEARD[lang].format(text=shown) + "\n\n" + answer
    return answer


def _transcribe(audio_key: str) -> tuple[str, str] | None:
    """(transcript, language code) for a stored voice note; None if it can't be read. Never raises."""
    extension = audio_key.rsplit(".", 1)[-1].lower()
    media_format = TRANSCRIBE_FORMATS.get(extension)
    if not media_format:
        log.info("no transcription for .%s audio", extension)
        return None
    return voice.transcribe(os.environ["MEDIA_BUCKET"], audio_key, media_format)


def _keyword_reply(text: str, ctx: TurnContext) -> str:
    """Used only when no Bedrock model answers."""
    if not ctx.saved:   # a model may have saved the report, then failed before replying
        fields = fallback.extract(text)
        if not fallback.is_complaint(fields):
            return prompts.WELCOME[ctx.lang]
        save_extracted(ctx, fields, extracted_by="keywords")
    return prompts.REPORT_SAVED[ctx.lang] + "\n\n" + prompts.ADVICE[ctx.lang]


def _float(value) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None
