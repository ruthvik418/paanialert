"""Alert text sent to residents. Owner: B. A's cluster check calls advisory_text()."""
from __future__ import annotations

from agent.prompts import ADVICE


def advisory_text(report_count: int, sick_households: int, lang: str) -> str:
    sick_en = f", {sick_households} household{'s' if sick_households != 1 else ''} with illness" if sick_households else ""
    sick_hi = f", {sick_households} घरों में बीमारी" if sick_households else ""
    sick_hinglish = f", {sick_households} gharon mein bimari" if sick_households else ""
    lines = {
        "en": f"⚠️ PaaniAlert: {report_count} bad-water reports near you in the last 2 days{sick_en}.",
        "hi": f"⚠️ PaaniAlert: पिछले 2 दिनों में आपके पास खराब पानी की {report_count} शिकायतें{sick_hi}।",
        "hinglish": f"⚠️ PaaniAlert: pichhle 2 din mein aapke paas kharab paani ki {report_count} shikayatein{sick_hinglish}.",
    }
    lang = lang if lang in lines else "hinglish"
    return f"{lines[lang]}\n\n{ADVICE[lang]}\n\nReply STOP to stop these alerts."


def official_text(cluster_id: str, level: str, report_count: int, phones: int, sick: int,
                  lat: float, lon: float, dashboard_url: str) -> str:
    return (
        f"PaaniAlert {level.upper()}: {report_count} bad-water reports from {phones} phones, "
        f"{sick} household(s) with illness, in the last 48 hours.\n"
        f"Area centre: {lat:.4f}, {lon:.4f} (https://www.google.com/maps?q={lat:.5f},{lon:.5f})\n"
        f"Open the dashboard to acknowledge or close it: {dashboard_url}\n"
        f"Cluster ID: {cluster_id}"
    )
