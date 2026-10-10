"""Alert text sent to residents. Owner: B. A's cluster check calls advisory_text(), the API all_clear_text(),
and officials' manual warnings use warning_text() / warning_lifted_text()."""
from __future__ import annotations

import re

from agent.prompts import ADVICE

NOTE_MAX = 200
# Anything that looks like a link: with a scheme, starting www., or a bare domain like bit.ly/x.
_LINK = re.compile(r"(https?://|www\.)\S*|\b[\w-]+(\.[\w-]+)*\.(com|in|org|net|gov|io|co|ly|me|info|xyz|link|app|site)\b\S*", re.I)


def advisory_text(report_count: int, sick_households: int, lang: str, whatsapp: bool = True) -> str:
    """The automatic Alert. WhatsApp ends with how to stop; an app push (whatsapp=False) doesn't."""
    sick_en = f", {sick_households} household{'s' if sick_households != 1 else ''} with illness" if sick_households else ""
    sick_hi = f", {sick_households} घरों में बीमारी" if sick_households else ""
    sick_hinglish = f", {sick_households} gharon mein bimari" if sick_households else ""
    lines = {
        "en": f"⚠️ PaaniAlert: {report_count} bad-water reports near you in the last 2 days{sick_en}.",
        "hi": f"⚠️ PaaniAlert: पिछले 2 दिनों में आपके पास खराब पानी की {report_count} शिकायतें{sick_hi}।",
        "hinglish": f"⚠️ PaaniAlert: pichhle 2 din mein aapke paas kharab paani ki {report_count} shikayatein{sick_hinglish}.",
    }
    lang = lang if lang in lines else "en"
    return f"{lines[lang]}\n\n{ADVICE[lang]}" + (f"\n\n{STOP[lang]}" if whatsapp else "")


def all_clear_text(lang: str, whatsapp: bool = True) -> str:
    """Sent when officials mark a cluster fixed, to subscribers in its area who got the advisory."""
    lines = {
        "en": "✅ PaaniAlert: officials have marked the water problem near you as fixed. "
              "If your water still looks, smells or tastes bad, message us here again.",
        "hi": "✅ PaaniAlert: अधिकारियों ने आपके पास पानी की समस्या को ठीक बताया है। "
              "अगर पानी अब भी गंदा दिखे, बदबू आए या स्वाद खराब लगे, तो हमें यहाँ फिर से बताएं।",
        "hinglish": "✅ PaaniAlert: officials ne aapke paas paani ki problem ko theek bataya hai. "
                    "Agar paani ab bhi ganda dikhe, badboo aaye ya swaad kharab lage, to humein yahan phir se batayein.",
    }
    lang = lang if lang in lines else "en"
    return lines[lang] + (f"\n\n{STOP[lang]}" if whatsapp else "")


STOP = {
    "en": "Reply STOP to stop these alerts.",
    "hi": "ये चेतावनियाँ बंद करने के लिए STOP लिखें।",
    "hinglish": "Ye alerts band karne ke liye STOP likhein.",
}


def official_text(cluster_id: str, level: str, report_count: int, phones: int, sick: int,
                  lat: float, lon: float, dashboard_url: str) -> str:
    return (
        f"PaaniAlert {level.upper()}: {report_count} bad-water reports from {phones} phones, "
        f"{sick} household(s) with illness, in the last 48 hours.\n"
        f"Area centre: {lat:.4f}, {lon:.4f} (https://www.google.com/maps?q={lat:.5f},{lon:.5f})\n"
        f"Open the dashboard to acknowledge or close it: {dashboard_url}\n"
        f"Cluster ID: {cluster_id}"
    )


def clean_note(note: str | None) -> str | None:
    """An official's free-text note, safe to forward: no links, one line, at most 200 characters."""
    if not note:
        return None
    text = _LINK.sub("", str(note))
    text = " ".join("".join(ch if ch.isprintable() else " " for ch in text).split())
    return text[:NOTE_MAX].strip() or None


WARNING = {
    "boil": {
        "en": "⚠️ PaaniAlert warning from officials: boil drinking water. Tap water in your area may be unsafe. "
              "Boil it for at least 1 minute before drinking or cooking.",
        "hi": "⚠️ PaaniAlert, अधिकारियों की चेतावनी: पीने का पानी उबालें। आपके इलाके का नल का पानी असुरक्षित हो सकता है। "
              "पीने या खाना बनाने से पहले कम से कम 1 मिनट उबालें।",
        "hinglish": "⚠️ PaaniAlert, officials ki warning: peene ka paani ubaalein. Aapke area ka nal ka paani unsafe ho sakta hai. "
                    "Peene ya khana banane se pehle kam se kam 1 minute ubaalein.",
    },
    "do_not_use": {
        "en": "🚫 PaaniAlert warning from officials: do not drink or cook with tap water in your area until further notice. "
              "Boiling may not make it safe. Use bottled water or water from a safe tanker.",
        "hi": "🚫 PaaniAlert, अधिकारियों की चेतावनी: अगली सूचना तक अपने इलाके के नल का पानी पीने या खाना बनाने में इस्तेमाल न करें। "
              "उबालने से भी यह सुरक्षित नहीं हो सकता। बोतल का पानी या सुरक्षित टैंकर का पानी इस्तेमाल करें।",
        "hinglish": "🚫 PaaniAlert, officials ki warning: agli soochna tak apne area ka nal ka paani peene ya khana banane mein "
                    "use na karein. Ubaalne se bhi ye safe nahi ho sakta. Bottle ka paani ya safe tanker ka paani use karein.",
    },
}

WARNING_LIFTED = {
    "boil": {
        "en": "✅ PaaniAlert: officials have lifted the boil-water warning for your area.",
        "hi": "✅ PaaniAlert: अधिकारियों ने आपके इलाके के लिए पानी उबालने की चेतावनी हटा दी है।",
        "hinglish": "✅ PaaniAlert: officials ne aapke area ke liye paani ubaalne ki warning hata di hai.",
    },
    "do_not_use": {
        "en": "✅ PaaniAlert: officials have lifted the do-not-use warning for tap water in your area.",
        "hi": "✅ PaaniAlert: अधिकारियों ने आपके इलाके के नल के पानी पर लगी रोक की चेतावनी हटा दी है।",
        "hinglish": "✅ PaaniAlert: officials ne aapke area ke nal ke paani par lagi rok ki warning hata di hai.",
    },
}

LIFTED_TAIL = {
    "en": "If your water still looks, smells or tastes bad, report it again.",
    "hi": "अगर पानी अब भी गंदा दिखे, बदबू आए या स्वाद खराब लगे, तो फिर से शिकायत करें।",
    "hinglish": "Agar paani ab bhi ganda dikhe, badboo aaye ya swaad kharab lage, to phir se shikayat karein.",
}

NOTE_LABEL = {"en": "Note from officials", "hi": "अधिकारियों का संदेश", "hinglish": "Officials ka sandesh"}


def warning_text(kind: str, note: str | None, lang: str, whatsapp: bool = True) -> str:
    """An officials' warning for one recipient. WhatsApp messages end with how to stop them; pushes don't."""
    lang = lang if lang in LIFTED_TAIL else "en"
    parts = [WARNING[kind][lang]]
    if note:
        parts.append(f"{NOTE_LABEL[lang]}: {note}")
    if kind == "boil":
        parts.append(ADVICE[lang])
    if whatsapp:
        parts.append(STOP[lang])
    return "\n\n".join(parts)


def warning_lifted_text(kind: str, lang: str, whatsapp: bool = True) -> str:
    lang = lang if lang in LIFTED_TAIL else "en"
    parts = [WARNING_LIFTED[kind][lang], LIFTED_TAIL[lang]]
    if whatsapp:
        parts.append(STOP[lang])
    return "\n\n".join(parts)
