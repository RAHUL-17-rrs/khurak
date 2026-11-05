"""Daily round + cross-day rules, and seeding of the synthetic world.

Cross-day rules (policy.RULES X1-X3):
  X1 no answer -> retry in 2 h (max 2 attempts)
  X2 two unanswered attempts -> call the family contact
  X3 three consecutive days without a confirmed dose -> AMBER "home visit needed"

The demo compresses time: a "2 hour" retry happens a few seconds later, clearly labelled.
"""
from __future__ import annotations

import asyncio
import random
import re
import threading

import yaml

from . import db, orchestrator, voices
from .config import DATA_DIR, DEMO_DAY, HOME_VISIT_DAYS, MAX_RETRIES
from .events import emit
from .policy import AMBER

_run_lock = threading.Lock()
state = {"running": False, "day": None, "progress": 0, "total": 0}


def load_yaml(name: str) -> dict:
    return yaml.safe_load((DATA_DIR / name).read_text(encoding="utf-8"))


SCEN = load_yaml("scenarios.yaml")

# What patients say on ordinary (non-scripted) days, per language.
ORDINARY = {
    "hi-IN": [{"ask_dose": "हाँ, ले ली।", "ask_symptoms": "नहीं, सब ठीक है।"},
              {"ask_dose": "जी, सुबह ले ली थी।", "ask_symptoms": "कोई तकलीफ़ नहीं।"}],
    "hi-en": [{"ask_dose": "Haan, le li.", "ask_symptoms": "Nahi, sab theek hai."}],
    "mr-IN": [{"ask_dose": "हो, घेतली.", "ask_symptoms": "नाही, काही त्रास नाही."}],
    "bn-IN": [{"ask_dose": "হ্যাঁ, খেয়েছি।", "ask_symptoms": "না, কোনো অসুবিধা নেই।"}],
    "kn-IN": [{"ask_dose": "ಹೌದು, ತೆಗೆದುಕೊಂಡೆ.", "ask_symptoms": "ಏನೂ ತೊಂದರೆ ಇಲ್ಲ."}],
}


def current_day() -> int:
    return int(db.kv_get("current_day", DEMO_DAY))


def scripted_plan(p: dict, day: int) -> dict:
    """What this synthetic patient will do on this day."""
    if day == int(SCEN.get("demo_day", DEMO_DAY)) and p["id"] in SCEN["demo"]:
        return SCEN["demo"][p["id"]]
    rng = random.Random(f"{p['id']}-{day}")
    return {"answers": rng.choice(ORDINARY.get(p["language"], ORDINARY["hi-IN"]))}


def scripted_answer(p: dict, day: int, stage: str, kind: str = "patient") -> str | None:
    plan = scripted_plan(p, day)
    if kind == "family":
        return plan.get("family_answer") or {
            "hi-IN": "हाँ, वो ठीक हैं, दवा ले रहे हैं।", "hi-en": "Haan, woh theek hai, dawai le raha hai.",
            "mr-IN": "हो, ते ठीक आहेत, गोळ्या घेतात.", "bn-IN": "হ্যাঁ, উনি ভালো আছেন, ওষুধ খাচ্ছেন।",
            "kn-IN": "ಹೌದು, ಅವರು ಚೆನ್ನಾಗಿದ್ದಾರೆ, ಮಾತ್ರೆ ತೆಗೆದುಕೊಳ್ಳುತ್ತಿದ್ದಾರೆ."}.get(p["language"])
    return (plan.get("answers") or {}).get(stage)


def scripted_turn(call_id: str, p: dict, day: int, stage: str, kind: str = "patient") -> dict:
    """Synthesize the patient's scripted line (Timbre, own voice, noise, phone line) and send it to Prisma."""
    text = scripted_answer(p, day, stage, kind)
    if text is None:
        # patient stays silent / says nothing useful for this question
        return orchestrator.take_turn(call_id, text="", source="scripted")
    voice = p["family"].get("voice", "Avinash") if kind == "family" else p["voice"]
    noise = p.get("noise") or {}
    wav, name, _mock = voices.patient_clip(text, p["language"], voice, noise.get("kind"), noise.get("snr_db"))
    return orchestrator.take_turn(call_id, wav=wav, source="scripted", hint_text=voices.strip_tags(text),
                                  patient_audio_url=f"/audio/clips/{name}")


# ----------------------------------------------------------------------------- autopilot round


def run_patient_day(p: dict, day: int, pace: float = 1.0) -> dict:
    """Full day for one patient, including retries and the family call."""
    plan = scripted_plan(p, day)
    unanswered = int(plan.get("no_answer_attempts", 0))
    for attempt in range(1, MAX_RETRIES + 1):
        cid = orchestrator.create_call(p["id"], day, attempt, "patient", source="autopilot")
        _sleep(1.2 * pace)
        if attempt <= unanswered:
            orchestrator.mark_no_answer(cid)
            if attempt < MAX_RETRIES:
                emit("retry_scheduled", patient_id=p["id"], name=p["name"], rule="X1",
                     note="Retry in 2 hours (compressed for demo)")
                _sleep(1.5 * pace)
                continue
            # X2: two attempts failed -> family contact
            emit("family_call", patient_id=p["id"], name=p["name"], rule="X2",
                 family=p["family"].get("name"), relation=p["family"].get("relation"))
            _sleep(1.0 * pace)
            fid = orchestrator.create_call(p["id"], day, 1, "family", source="autopilot")
            _sleep(1.0 * pace)
            res = _converse(fid, p, day, "family", pace)
            check_home_visit(p, day)
            return res
        res = _converse(cid, p, day, "patient", pace)
        check_home_visit(p, day)
        return res
    return {}


def _converse(call_id: str, p: dict, day: int, kind: str, pace: float) -> dict:
    out = orchestrator.answer_call(call_id)
    _sleep(_speech_secs(out.get("agent_text", "")) * pace)
    for _ in range(6):
        stage = orchestrator.get_session(call_id).dialogue.stage
        out = scripted_turn(call_id, p, day, stage, kind)
        _sleep(_speech_secs(out.get("agent_text", "")) * pace * 0.6)
        if out.get("closed"):
            return out
    return out


def _speech_secs(text: str) -> float:
    return min(4.0, 0.6 + len(text) / 40)


def _sleep(secs: float) -> None:
    if secs > 0:
        threading.Event().wait(secs)


def check_home_visit(p: dict, day: int) -> None:
    """X3: N consecutive days without a confirmed dose."""
    rows = db.q("SELECT day, status, note FROM daily_status WHERE patient_id=? AND day>? AND day<=? ORDER BY day",
                p["id"], day - HOME_VISIT_DAYS, day)
    unconfirmed = [r for r in rows if r["status"] == "NO_ANSWER" or "missed" in (r["note"] or "")
                   or "away" in (r["note"] or "") or "stopped" in (r["note"] or "")]
    if len(rows) == HOME_VISIT_DAYS and len(unconfirmed) == HOME_VISIT_DAYS:
        if not db.q1("SELECT id FROM alerts WHERE patient_id=? AND day=? AND reason='home_visit_needed'", p["id"], day):
            orchestrator.raise_alert(p["id"], None, day, AMBER, "X3", "home_visit_needed",
                                     f"No confirmed dose for {HOME_VISIT_DAYS} consecutive days")


async def run_day(day: int | None = None, pace: float = 1.0, patient_ids: list[str] | None = None) -> None:
    if not _run_lock.acquire(blocking=False):
        raise RuntimeError("a round is already running")
    try:
        day = day or current_day()
        pats = [db.patient_row(r) for r in db.q("SELECT * FROM patients WHERE active=1 ORDER BY call_time")]
        if patient_ids:
            pats = [p for p in pats if p["id"] in patient_ids]
        state.update(running=True, day=day, progress=0, total=len(pats))
        emit("round_started", day=day, total=len(pats))
        sem = asyncio.Semaphore(3)

        async def one(p):
            async with sem:
                try:
                    await asyncio.to_thread(run_patient_day, p, day, pace)
                except Exception as e:  # keep the round going; surface the error
                    for c in db.q("SELECT id FROM calls WHERE patient_id=? AND day=? AND state IN "
                                  "('DIALING','IN_PROGRESS')", p["id"], day):
                        orchestrator.abandon(c["id"])
                        db.ex("UPDATE calls SET state='ERROR' WHERE id=?", c["id"])
                    emit("call_error", patient_id=p["id"], name=p["name"], error=str(e)[:300])
                state["progress"] += 1

        await asyncio.gather(*(one(p) for p in pats))
        emit("round_finished", day=day, summary=day_summary(day))
    finally:
        state["running"] = False
        _run_lock.release()


def day_summary(day: int) -> dict:
    rows = db.q("SELECT status, COUNT(*) n FROM daily_status WHERE day=? GROUP BY status", day)
    return {r["status"]: r["n"] for r in rows}


# ----------------------------------------------------------------------------- seeding


def seed(reset: bool = True) -> None:
    """Load synthetic patients and 18 days of synthetic adherence history."""
    if reset:
        db.reset()
    data = load_yaml("patients.yaml")
    db.kv_set("worker", data["worker"])
    for p in data["patients"]:
        db.ex("""INSERT OR REPLACE INTO patients(id, name, age, gender, city, language, voice, call_time, phone_masked,
                 family_json, regimen, story, noise_json, name_local, name_hi, start_day, active)
                 VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,1)""",
              p["id"], p["name"], p["age"], p["gender"], p["city"], p["language"], p["voice"], p["call_time"],
              p["phone_masked"], db.j(p["family"]), p["regimen"], p["story"], db.j(p.get("noise")),
              p.get("name_local"), p.get("name_hi"))
    demo_day = int(SCEN.get("demo_day", DEMO_DAY))
    for p in data["patients"]:
        rng = random.Random(p["id"])
        for d in range(1, demo_day):
            status, note = "GREEN", "dose_taken"
            r = rng.random()
            if p["id"] == "P4" and d >= demo_day - 2:
                status, note = ("NO_ANSWER", "no_answer") if d == demo_day - 1 else ("AMBER", "missed_dose")
            elif p["id"] == "P1":
                pass  # "fine for 18 days"
            elif r < 0.06:
                status, note = "AMBER", "missed_dose"
            elif r < 0.12:
                status, note = "GREEN", "orange_urine"
            cid = f"c{d:03d}_{p['id']}_seed"
            db.ex("""INSERT INTO calls(id, patient_id, day, attempt, kind, state, stage, status, rule, reasons_json,
                     source, mode, started_at, ended_at, seeded) VALUES(?,?,?,1,'patient','CLOSED','closed',?,?,?,
                     'seed','seed',?,?,1)""",
                  cid, p["id"], d, status, {"GREEN": "R8", "AMBER": "R6", "NO_ANSWER": "X1"}[status],
                  db.j([note]), db.now(), db.now())
            db.ex("INSERT OR REPLACE INTO daily_status(patient_id, day, status, note, call_id) VALUES(?,?,?,?,?)",
                  p["id"], d, status, note, cid)
            if status == "AMBER":
                db.ex("""INSERT INTO alerts(patient_id, call_id, day, level, rule, reason, quote, created_at, resolved,
                         resolved_at, resolution) VALUES(?,?,?,?,?,?,?,?,1,?,?)""",
                      p["id"], cid, d, "AMBER", "R6", note, "(seeded history)", db.now(), db.now(),
                      "Called patient - resolved")
    db.kv_set("current_day", demo_day)
    emit("reset", day=demo_day)


def ensure_seeded() -> None:
    if not db.q1("SELECT id FROM patients LIMIT 1"):
        seed()


def strip(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()
