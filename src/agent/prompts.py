"""What the agent is told, and every fixed message the bot sends. Owner: B.

Replies are in English unless the person picks another language from the menu
(see worker/app.py). Every message dict has "hi", "en" and "hinglish".
"""

DEFAULT_LANG = "en"

LANGUAGES = {
    "hi": "Hindi in Devanagari script",
    "en": "English",
    "hinglish": "Hinglish (Hindi written in Roman letters)",
}

ADVICE = {
    "en": "Please boil drinking water for at least 1 minute. Give ORS for loose motions. Blood in stool or signs of dehydration: call 108.",
    "hi": "पीने का पानी कम से कम 1 मिनट उबालकर पिएं। दस्त हो तो ORS दें। मल में खून या पानी की कमी के लक्षण हों तो 108 पर कॉल करें।",
    "hinglish": "Peene ka paani kam se kam 1 minute ubaal kar piyein. Dast ho to ORS dein. Potty mein khoon ya dehydration ho to 108 par call karein.",
}

ASK_LOCATION = {
    "en": "📍 Please share your location so we can check your area: tap Attach (📎) → Location.",
    "hi": "📍 कृपया अपनी लोकेशन भेजें ताकि हम आपके इलाके की जाँच कर सकें: Attach (📎) → Location।",
    "hinglish": "📍 Apni location bhejiye taaki hum aapka area check kar sakein: Attach (📎) → Location.",
}

ASK_COMPLAINT = {
    "en": "📍 Got your location, thank you. What is wrong with the water? Smell, colour, and is anyone sick?",
    "hi": "📍 लोकेशन मिल गई, धन्यवाद। पानी में क्या समस्या है? बदबू, रंग, और क्या कोई बीमार है?",
    "hinglish": "📍 Location mil gayi, shukriya. Paani mein kya problem hai? Badboo, rang, aur kya koi bimar hai?",
}

LOCATION_SAVED = {
    "en": "📍 Location saved with your report. Thank you, this helps warn your neighbours early.",
    "hi": "📍 आपकी शिकायत के साथ लोकेशन सेव हो गई। धन्यवाद, इससे पड़ोसियों को समय पर चेतावनी मिलेगी।",
    "hinglish": "📍 Aapki report ke saath location save ho gayi. Shukriya, isse padosiyon ko time par warning milegi.",
}

UNSUBSCRIBED = {
    "en": "You won't get PaaniAlert warnings any more. Send any message to report bad water again.",
    "hi": "अब आपको PaaniAlert की चेतावनियाँ नहीं मिलेंगी। खराब पानी की शिकायत के लिए कभी भी मैसेज करें।",
    "hinglish": "Ab aapko PaaniAlert warnings nahi milengi. Kharab paani report karne ke liye kabhi bhi message karein.",
}

LANGUAGE_MENU = (
    "Choose your language / भाषा चुनें:\n"
    "1️⃣ English\n"
    "2️⃣ हिंदी\n"
    "3️⃣ Hinglish (Roman Hindi)\n"
    "Reply with a number / नंबर भेजें."
)

LANGUAGE_SET = {
    "en": "Done, we'll reply in English from now on. Send \"language\" any time to change it.",
    "hi": "ठीक है, अब से हम हिंदी में जवाब देंगे। भाषा बदलने के लिए कभी भी \"भाषा\" लिखें।",
    "hinglish": "Theek hai, ab se Hinglish mein jawab denge. Bhasha badalne ke liye kabhi bhi \"bhasha\" likhein.",
}

WELCOME = {
    "en": "Hi! I'm PaaniAlert. Tell me if your tap water smells, looks dirty or is making people sick, and we'll warn your neighbours early.",
    "hi": "नमस्ते! मैं PaaniAlert हूँ। अगर नल के पानी में बदबू है, पानी गंदा है या उससे कोई बीमार हो रहा है, तो मुझे बताइए। हम आपके पड़ोसियों को समय पर चेतावनी देंगे।",
    "hinglish": "Namaste! Main PaaniAlert hoon. Agar nal ke paani mein badboo hai, paani ganda hai ya usse koi bimar ho raha hai, to batayiye. Hum padosiyon ko time par warning denge.",
}

EXTRACTION_PROMPT = """You read one WhatsApp message from a resident in India about their drinking water and fill in the report fields.
Messages are in Hindi (Devanagari), Hinglish (Roman Hindi, often with typos) or English.
Fill only what the message says. Use "unknown" for text fields and null for numbers that are not said. Never guess.
If the message is not about water (a greeting, a question, thanks), leave every field unknown or null."""

CHAT_PROMPT = """You are PaaniAlert, a WhatsApp assistant that helps residents in India report unsafe drinking water so outbreaks are caught early.
This message is not a water complaint. Reply in under 40 words, plain and kind, no markdown, in the language named at the end of the message.
Answer briefly if it's a question about PaaniAlert, then invite them to say what is wrong with their water (smell, colour, anyone sick).
Never say or suggest the water is safe. Never diagnose an illness. Never say a report was saved."""

# One line confirming what was understood, built from the extracted fields.
CONFIRM = {
    "en": "✅ Report saved: {summary}.",
    "hi": "✅ शिकायत दर्ज: {summary}।",
    "hinglish": "✅ Report save ho gayi: {summary}.",
}

FIELD_LABELS = {
    "smell": {
        "sewage": {"en": "sewage smell", "hi": "बदबू", "hinglish": "badboo"},
        "chemical": {"en": "chemical smell", "hi": "दवा जैसी गंध", "hinglish": "chemical jaisi gandh"},
        "other": {"en": "strange smell", "hi": "अजीब गंध", "hinglish": "ajeeb gandh"},
        "none": {"en": "no smell", "hi": "कोई गंध नहीं", "hinglish": "koi gandh nahi"},
    },
    "colour": {
        "yellow": {"en": "yellow water", "hi": "पीला पानी", "hinglish": "peela paani"},
        "brown": {"en": "brown water", "hi": "भूरा पानी", "hinglish": "bhura paani"},
        "black": {"en": "black water", "hi": "काला पानी", "hinglish": "kaala paani"},
        "cloudy": {"en": "dirty or cloudy water", "hi": "गंदा पानी", "hinglish": "ganda paani"},
        "clear": {"en": "clear water", "hi": "साफ़ दिखता पानी", "hinglish": "saaf dikhta paani"},
    },
    "taste": {
        "salty": {"en": "salty taste", "hi": "खारा स्वाद", "hinglish": "khara swad"},
        "bad": {"en": "bad taste", "hi": "खराब स्वाद", "hinglish": "kharab swad"},
        "normal": {"en": "normal taste", "hi": "स्वाद ठीक", "hinglish": "swad theek"},
    },
    "since_days": {
        0: {"en": "since today", "hi": "आज से", "hinglish": "aaj se"},
        1: {"en": "since yesterday", "hi": "कल से", "hinglish": "kal se"},
        "n": {"en": "for {n} days", "hi": "{n} दिन से", "hinglish": "{n} din se"},
    },
    "sick_count": {
        0: {"en": "nobody sick", "hi": "कोई बीमार नहीं", "hinglish": "koi bimar nahi"},
        "n": {"en": "{n} sick at home", "hi": "घर में {n} बीमार", "hinglish": "ghar mein {n} bimar"},
    },
}

REPORT_SAVED = {
    "en": "Thank you, your report is saved.",
    "hi": "धन्यवाद, आपकी शिकायत दर्ज हो गई।",
    "hinglish": "Shukriya, aapki report save ho gayi.",
}

ASK_SUBSCRIBE = {
    "en": "🔔 Want a warning if more bad water is reported near you? Reply YES. (Reply STOP any time to stop.)",
    "hi": "🔔 आपके पास और खराब पानी की शिकायत आने पर चेतावनी चाहिए? YES या हाँ लिखें। (बंद करने के लिए कभी भी STOP लिखें।)",
    "hinglish": "🔔 Aapke paas aur kharab paani ki shikayat aane par warning chahiye? YES ya haan likhein. (Band karne ke liye kabhi bhi STOP likhein.)",
}

SUBSCRIBED = {
    "en": "✅ Done. We'll message you if bad water is reported near you. Reply STOP any time.",
    "hi": "✅ हो गया। आपके पास खराब पानी की शिकायत आने पर हम आपको मैसेज करेंगे। बंद करने के लिए कभी भी STOP लिखें।",
    "hinglish": "✅ Ho gaya. Aapke paas kharab paani ki shikayat aane par hum aapko message karenge. Band karne ke liye kabhi bhi STOP likhein.",
}

NOT_SUBSCRIBED = {
    "en": "Okay, no alerts. You can still report bad water any time.",
    "hi": "ठीक है, कोई चेतावनी नहीं भेजेंगे। आप कभी भी खराब पानी की शिकायत कर सकते हैं।",
    "hinglish": "Theek hai, koi alert nahi bhejenge. Aap kabhi bhi kharab paani report kar sakte hain.",
}

VOICE_PENDING = {
    "en": "Got your voice note. Voice is coming soon; for now please type a few words: smell, colour, anyone sick?",
    "hi": "आपका वॉइस नोट मिला। अभी कृपया कुछ शब्द लिखकर भेजें: बदबू, रंग, कोई बीमार?",
    "hinglish": "Voice note mila. Abhi ke liye kuch shabd likh kar bhejiye: badboo, rang, koi bimar?",
}
