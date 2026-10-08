import { createContext, createElement, useContext, useEffect, useMemo, useState } from "react";

// English by default; the choice is remembered per browser. ?lang=hi in the URL opens in Hindi.
export const LANGS = { en: "English", hi: "हिंदी" };
const STORE = "paanialert-lang";

const STRINGS = {
  en: {
    officials: "Officials",
    public: "Public",
    language: "Language",
    jumpTo: "Jump to city",
    mapLabel: "Map of reports and clusters",
    place_indore: "Indore",
    place_delhi: "Delhi",

    pcEyebrow: "PaaniAlert · Officials",
    pcTitle: "Enter the dashboard key",
    pcHelp: "Ask your team lead for the key. It stays in this browser tab only.",
    pcLabel: "Dashboard key",
    pcWrong: "That key didn't work. Check it and try again.",
    pcOffline: "Couldn't reach the server. Check your connection.",
    pcChecking: "Checking…",
    pcOpen: "Open dashboard",
    pcPublic: "See the public cluster page",

    updated: "Updated {time}",
    loading: "Loading…",
    signOut: "Sign out",
    statOpenAlerts: "Open alerts",
    statReports: "Reports, 48 h",
    statSick: "With sickness",
    refreshError: "Couldn't refresh. Retrying in 30 seconds.",
    tabClusters: "Clusters ({n})",
    tabReports: "Reports ({n})",
    emptyClusters: "No clusters yet. They appear when several nearby phones report bad water within 48 hours.",
    emptyReports: "No reports in the last 48 hours. Reports sent on WhatsApp show up here within 30 seconds.",
    located: "📍 located",
    noLocation: "no location yet",
    photo: "photo",
    nReports: "{n} reports",
    nPhones: "{n} phones",
    nSickHouseholds: "{n} sick households",
    firstReport: "First report {ago}",
    alertSent: "alert sent {ago}",
    escalated: "escalated to health officer",
    acknowledge: "Acknowledge",
    markAs: "Mark as {status}?",
    yes: "Yes",
    cancel: "Cancel",

    pubTitle: "Bad-water warnings near you",
    pubHelp: "Areas where several residents reported bad drinking water in the last 48 hours. Boil drinking water if you live nearby.",
    pubEmpty: "No active warnings right now.",
    pubAck: "The ward engineer has acknowledged this.",
    pubNotified: "Engineer notified {ago}. No action recorded yet.",
    pubWatching: "Being watched.",
    pubFooter: "Report bad water on WhatsApp.",

    level_alert: "Alert", level_watch: "Watch", level_none: "None",
    status_open: "Open", status_acknowledged: "Acknowledged", status_fixed: "Fixed",
    status_false_alarm: "False alarm", status_expired: "Expired",

    justNow: "just now", minsAgo: "{n} min ago", hoursAgo: "{n} h ago", daysAgo: "{n} days ago",
    smell_sewage: "sewage smell", smell_chemical: "chemical smell", smell_other: "odd smell",
    colour_yellow: "yellow water", colour_brown: "brown water", colour_black: "black water", colour_cloudy: "dirty water",
    taste_salty: "salty taste", taste_bad: "bad taste",
    oneDay: "1 day", nDays: "{n} days",
    detailsUnclear: "Details unclear",
    sickNotAsked: "Sick: not asked", nobodySick: "Nobody sick", nSick: "{n} sick",
    symptom_diarrhoea: "diarrhoea", symptom_vomiting: "vomiting", symptom_fever: "fever",
    "symptom_stomach pain": "stomach pain",
  },
  hi: {
    officials: "अधिकारी",
    public: "सार्वजनिक",
    language: "भाषा",
    jumpTo: "शहर चुनें",
    mapLabel: "शिकायतों और क्लस्टरों का नक्शा",
    place_indore: "इंदौर",
    place_delhi: "दिल्ली",

    pcEyebrow: "PaaniAlert · अधिकारी",
    pcTitle: "डैशबोर्ड कुंजी डालें",
    pcHelp: "कुंजी अपनी टीम लीड से लें। यह सिर्फ़ इसी ब्राउज़र टैब में रहती है।",
    pcLabel: "डैशबोर्ड कुंजी",
    pcWrong: "यह कुंजी नहीं चली। जाँचकर फिर से कोशिश करें।",
    pcOffline: "सर्वर से नहीं जुड़ पाए। अपना इंटरनेट जाँचें।",
    pcChecking: "जाँच हो रही है…",
    pcOpen: "डैशबोर्ड खोलें",
    pcPublic: "सार्वजनिक पेज देखें",

    updated: "{time} पर अपडेट",
    loading: "लोड हो रहा है…",
    signOut: "साइन आउट",
    statOpenAlerts: "खुली चेतावनियाँ",
    statReports: "शिकायतें, 48 घंटे",
    statSick: "बीमारी के साथ",
    refreshError: "अपडेट नहीं हो पाया। 30 सेकंड में फिर कोशिश होगी।",
    tabClusters: "क्लस्टर ({n})",
    tabReports: "शिकायतें ({n})",
    emptyClusters: "अभी कोई क्लस्टर नहीं है। जब 48 घंटों में आसपास के कई फ़ोन खराब पानी की शिकायत करते हैं, तब यहाँ दिखते हैं।",
    emptyReports: "पिछले 48 घंटों में कोई शिकायत नहीं। WhatsApp पर भेजी गई शिकायतें 30 सेकंड में यहाँ दिखती हैं।",
    located: "📍 लोकेशन मिली",
    noLocation: "लोकेशन अभी नहीं",
    photo: "फ़ोटो",
    nReports: "{n} शिकायतें",
    nPhones: "{n} फ़ोन",
    nSickHouseholds: "{n} घरों में बीमारी",
    firstReport: "पहली शिकायत {ago}",
    alertSent: "चेतावनी भेजी गई {ago}",
    escalated: "स्वास्थ्य अधिकारी को भेजा गया",
    acknowledge: "देख लिया",
    markAs: "\"{status}\" दर्ज करें?",
    yes: "हाँ",
    cancel: "रद्द करें",

    pubTitle: "आपके पास खराब पानी की चेतावनियाँ",
    pubHelp: "वे इलाके जहाँ पिछले 48 घंटों में कई लोगों ने खराब पीने के पानी की शिकायत की है। आप पास में रहते हैं तो पीने का पानी उबालकर पिएं।",
    pubEmpty: "अभी कोई चेतावनी नहीं है।",
    pubAck: "वार्ड इंजीनियर ने इसे देख लिया है।",
    pubNotified: "इंजीनियर को {ago} सूचना दी गई। अभी कोई कार्रवाई दर्ज नहीं हुई।",
    pubWatching: "निगरानी में है।",
    pubFooter: "खराब पानी की शिकायत WhatsApp पर करें।",

    level_alert: "चेतावनी", level_watch: "निगरानी", level_none: "कोई नहीं",
    status_open: "खुला", status_acknowledged: "देख लिया", status_fixed: "ठीक किया गया",
    status_false_alarm: "गलत अलार्म", status_expired: "समाप्त",

    justNow: "अभी", minsAgo: "{n} मिनट पहले", hoursAgo: "{n} घंटे पहले", daysAgo: "{n} दिन पहले",
    smell_sewage: "सीवर जैसी बदबू", smell_chemical: "रसायन जैसी गंध", smell_other: "अजीब गंध",
    colour_yellow: "पीला पानी", colour_brown: "मटमैला पानी", colour_black: "काला पानी", colour_cloudy: "गंदा पानी",
    taste_salty: "खारा स्वाद", taste_bad: "खराब स्वाद",
    oneDay: "1 दिन से", nDays: "{n} दिन से",
    detailsUnclear: "जानकारी साफ़ नहीं",
    sickNotAsked: "बीमारी: पूछा नहीं गया", nobodySick: "कोई बीमार नहीं", nSick: "{n} बीमार",
    symptom_diarrhoea: "दस्त", symptom_vomiting: "उल्टी", symptom_fever: "बुखार",
    "symptom_stomach pain": "पेट दर्द",
  },
};

function initialLang() {
  try {
    const fromUrl = new URLSearchParams(window.location.search).get("lang");
    if (fromUrl && fromUrl in LANGS) return fromUrl;
    const saved = localStorage.getItem(STORE);
    if (saved && saved in LANGS) return saved;
  } catch { /* storage blocked: use the default */ }
  return "en";
}

function fill(text, vars) {
  return vars ? text.replace(/\{(\w+)\}/g, (_, k) => (vars[k] ?? "")) : text;
}

const LangContext = createContext(null);

export function LangProvider({ children }) {
  const [lang, setLang] = useState(initialLang);
  useEffect(() => {
    document.documentElement.lang = lang;
    try { localStorage.setItem(STORE, lang); } catch { /* private mode */ }
  }, [lang]);
  const value = useMemo(() => ({
    lang,
    setLang,
    t: (key, vars) => fill(STRINGS[lang][key] ?? STRINGS.en[key] ?? key, vars),
  }), [lang]);
  return createElement(LangContext.Provider, { value }, children);
}

export const useLang = () => useContext(LangContext);
