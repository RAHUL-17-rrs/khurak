"""Morning voice briefing for the health worker: who to see first, in her language.

The briefing text is assembled deterministically from today's alerts (no LLM), then
spoken with Timbre v3.0 at 24 kHz so it plays well as a WhatsApp-style voice note.
"""
from __future__ import annotations

from . import audio, db, gnani
from .config import AGENT_VOICE, BRIEF_DIR

REASON_HI = {
    "yellow_eyes": "आँखों में पीलापन", "blood_cough": "खांसी में खून", "persistent_vomit": "बार बार उल्टी",
    "breathless": "सांस फूलना", "vision": "धुंधला दिखना", "rash": "शरीर पर दाने",
    "stopped_treatment": "दवा बंद कर दी है", "missed_dose": "आज की खुराक छूट गई",
    "unclear_answer": "जवाब साफ़ नहीं था", "low_confidence": "जवाब साफ़ नहीं था",
    "family_reports_away_or_missed": "घर पर नहीं मिले, परिवार ने बताया कि दवा साथ नहीं है",
    "patient_unreachable_family_contacted": "फ़ोन नहीं उठाया, परिवार से बात हुई",
    "home_visit_needed": "तीन दिन से दवा की पुष्टि नहीं, घर जाना ज़रूरी है",
    "unspecified_problem": "कोई तकलीफ़ बताई है", "vomiting": "उल्टी हुई", "stomach_pain": "पेट दर्द",
    "tingling": "हाथ पैर में झुनझुनी", "joint_pain": "जोड़ों में दर्द",
}
REASON_EN = {
    "yellow_eyes": "yellow eyes", "blood_cough": "blood in cough", "persistent_vomit": "repeated vomiting",
    "breathless": "breathlessness", "vision": "blurred vision", "rash": "rash",
    "stopped_treatment": "has stopped treatment", "missed_dose": "missed today's dose",
    "unclear_answer": "answer was unclear", "low_confidence": "answer was unclear",
    "family_reports_away_or_missed": "away from home without medicines (family)",
    "patient_unreachable_family_contacted": "unreachable, family contacted",
    "home_visit_needed": "no confirmed dose for 3 days, home visit needed",
    "unspecified_problem": "reported a problem", "vomiting": "vomited", "stomach_pain": "stomach pain",
    "tingling": "tingling in hands/feet", "joint_pain": "joint pain",
}


def _reasons(reason: str, table: dict) -> str:
    parts = []
    for r in reason.split("+"):
        r = r.replace("evon:", "")
        parts.append(table.get(r, table.get(r.replace("possible_", ""), r.replace("_", " "))))
    return ", ".join(dict.fromkeys(parts))


def build(day: int) -> dict:
    worker = db.kv_get("worker", {"name": "Kavita Shinde"})
    alerts = db.q("""SELECT a.*, p.name, p.name_hi FROM alerts a JOIN patients p ON p.id=a.patient_id
                     WHERE a.day=? AND a.resolved=0 ORDER BY CASE a.level WHEN 'RED' THEN 0 ELSE 1 END, a.id""", day)
    per_patient: dict[str, dict] = {}
    for a in alerts:
        e = per_patient.setdefault(a["patient_id"], {"name": a["name"], "name_hi": a["name_hi"] or a["name"],
                                                     "level": a["level"], "reasons": []})
        if a["level"] == "RED":
            e["level"] = "RED"
        e["reasons"].append(a["reason"])
    reds = [e for e in per_patient.values() if e["level"] == "RED"]
    ambers = [e for e in per_patient.values() if e["level"] != "RED"]
    total = db.q1("SELECT COUNT(*) n FROM patients WHERE active=1")["n"]
    greens = db.q1("SELECT COUNT(*) n FROM daily_status WHERE day=? AND status='GREEN'", day)["n"]
    first = worker["name"].split()[0]
    first_hi = {"Kavita": "कविता"}.get(first, first)

    hi = [f"सुप्रभात {first_hi} जी। खुराक की आज की रिपोर्ट, दिन {day}।"]
    en = [f"Good morning {first}. Khurak's report for day {day}."]
    if reds:
        hi.append(f"{len(reds)} मरीज़ों को आज ही देखना ज़रूरी है।")
        en.append(f"{len(reds)} patients need to be seen today.")
        for e in reds:
            hi.append(f"{e['name_hi']}: {_reasons('+'.join(e['reasons']), REASON_HI)}।")
            en.append(f"{e['name']}: {_reasons('+'.join(e['reasons']), REASON_EN)}.")
    if ambers:
        hi.append(f"{len(ambers)} मरीज़ों से बात करनी है।")
        en.append(f"{len(ambers)} patients need a call or visit.")
        for e in ambers:
            hi.append(f"{e['name_hi']}: {_reasons('+'.join(e['reasons']), REASON_HI)}।")
            en.append(f"{e['name']}: {_reasons('+'.join(e['reasons']), REASON_EN)}.")
    hi.append(f"{greens} मरीज़ों ने दवा ले ली है और सब ठीक है। कुल {total} मरीज़।")
    en.append(f"{greens} patients took their dose with no problems. {total} patients in total.")
    hi_text, en_text = " ".join(hi), " ".join(en)

    wav, mock = gnani.synthesize(hi_text, "hi-IN", AGENT_VOICE, phone=False)
    name = f"briefing_day{day}_{abs(hash(hi_text)) % 10**8}.wav"
    (BRIEF_DIR / name).write_bytes(wav)
    return {"day": day, "text": hi_text, "english": en_text, "audio": f"/audio/briefings/{name}", "mock": mock,
            "red": len(reds), "amber": len(ambers), "green": greens, "total": total,
            "seconds": round(audio.duration_s(wav), 1)}
