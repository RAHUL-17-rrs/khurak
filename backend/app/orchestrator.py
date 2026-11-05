"""Live call orchestration: Prisma STT -> classifier -> policy -> tools, with DB + SSE events.

One `CallSession` per active call (in memory). Every turn is persisted with its audio,
transcript, understanding, Evon opinion and latency, and every call ends with a decision
trace that names the rule that fired and the evidence words behind it.
"""
from __future__ import annotations

import threading
import time
import uuid

from . import db, gnani, voices
from .config import LIVE, MAX_ANSWER_SECONDS, REC_DIR
from .dialogue import Dialogue
from .events import emit
from .policy import AMBER, RED

_sessions: dict[str, "CallSession"] = {}
_lock = threading.Lock()


class CallError(RuntimeError):
    pass


class CallSession:
    def __init__(self, call_id: str, patient: dict, day: int, kind: str):
        self.call_id, self.patient, self.day, self.kind = call_id, patient, day, kind
        self.dialogue = Dialogue(patient["language"], patient.get("name_local") or patient["name"], kind)
        self.turn_idx = 0
        self.trace: dict = {"call_id": call_id, "patient": patient["name"], "patient_id": patient["id"],
                            "language": patient["language"], "kind": kind, "day": day, "turns": [],
                            "mode": "live" if LIVE else "mock"}
        self.t_start = time.perf_counter()
        self.stt_ms: list[int] = []


def _patient(pid: str) -> dict:
    r = db.q1("SELECT * FROM patients WHERE id=?", pid)
    if not r:
        raise CallError(f"unknown patient {pid}")
    return db.patient_row(r)


def get_session(call_id: str) -> CallSession:
    s = _sessions.get(call_id)
    if not s:
        raise CallError("call is not active (finished, or server restarted)")
    return s


# ----------------------------------------------------------------------------- lifecycle


def create_call(pid: str, day: int, attempt: int = 1, kind: str = "patient", source: str = "manual",
                state: str = "DIALING") -> str:
    call_id = f"c{day:03d}_{pid}_{kind[0]}{attempt}_{uuid.uuid4().hex[:4]}"
    db.ex("""INSERT INTO calls(id, patient_id, day, attempt, kind, state, stage, source, mode, started_at)
             VALUES(?,?,?,?,?,?,?,?,?,?)""", call_id, pid, day, attempt, kind, state, "dialing", source,
          "live" if LIVE else "mock", db.now())
    p = _patient(pid)
    emit("call_dialing", call_id=call_id, patient_id=pid, name=p["name"], kind=kind, attempt=attempt, day=day,
         who=(p["family"].get("name") if kind == "family" else p["name"]))
    return call_id


def answer_call(call_id: str) -> dict:
    """Phone picked up: play greeting + first question."""
    c = db.q1("SELECT * FROM calls WHERE id=?", call_id)
    if not c:
        raise CallError("unknown call")
    p = _patient(c["patient_id"])
    s = CallSession(call_id, p, c["day"], c["kind"])
    with _lock:
        _sessions[call_id] = s
    prompts = s.dialogue.opening()
    url, mock = voices.agent_audio([x.text for x in prompts], p["language"], f"{call_id}_a0.wav")
    db.ex("UPDATE calls SET state='IN_PROGRESS', stage=? WHERE id=?", s.dialogue.stage, call_id)
    out = {"call_id": call_id, "stage": s.dialogue.stage, "agent_audio": url, "tts_mock": mock,
           "agent_text": " ".join(x.text for x in prompts), "agent_english": " ".join(x.english for x in prompts),
           "prompts": [x.to_dict() for x in prompts], "closed": False}
    s.trace["opening"] = [x.key for x in prompts]
    emit("agent_speaking", call_id=call_id, patient_id=p["id"], text=out["agent_text"],
         english=out["agent_english"], audio=url, stage=s.dialogue.stage)
    return out


def take_turn(call_id: str, *, wav: bytes | None = None, text: str | None = None, source: str = "live",
              hint_text: str | None = None, patient_audio_url: str | None = None) -> dict:
    """Process one patient answer (audio -> Prisma, or typed text) and return what happens next."""
    s = get_session(call_id)
    stage = s.dialogue.stage
    s.turn_idx += 1
    p = s.patient
    emit("listening_done", call_id=call_id, patient_id=p["id"], stage=stage)

    stt_ms, stt_mock, stt_meta = 0, False, {}
    if text is not None:
        transcript = text.strip()
    else:
        if wav is None:
            raise CallError("no audio or text")
        name = f"{call_id}_p{s.turn_idx}.wav"
        (REC_DIR / name).write_bytes(wav)
        patient_audio_url = patient_audio_url or f"/audio/rec/{name}"
        prev = " ".join(t["transcript"] for t in s.trace["turns"])[-600:] or None
        r = gnani.transcribe(wav, p["language"], hint_text=hint_text, previous_text=prev)
        transcript, stt_ms, stt_mock, stt_meta = r.transcript, r.latency_ms, r.mock, r.raw
        s.stt_ms.append(stt_ms)
    emit("transcribed", call_id=call_id, patient_id=p["id"], stage=stage, text=transcript,
         stt_ms=stt_ms, mock=stt_mock, audio=patient_audio_url)

    out = s.dialogue.answer(transcript)
    u = out.understanding
    turn = {"stage": stage, "transcript": transcript, "dose": u.dose, "red_flags": u.red_flags,
            "negated": u.negated, "benign": u.benign, "watch": u.watch, "confidence": u.confidence,
            "evidence": u.evidence, "stt_ms": stt_ms, "source": source, "evon": out.evon,
            "step_rule": out.step_rule, "patient_audio": patient_audio_url}
    s.trace["turns"].append(turn)
    db.ex("""INSERT INTO turns(call_id, idx, stage, prompt_json, answer_audio, transcript, understanding_json,
             evon_json, stt_ms, stt_mock, source, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
          call_id, s.turn_idx, stage, db.j(s.trace.get("opening") if s.turn_idx == 1 else None),
          patient_audio_url, transcript, db.j(u.to_dict()), db.j(out.evon), stt_ms, int(stt_mock), source, db.now())
    emit("understood", call_id=call_id, patient_id=p["id"], stage=stage, dose=u.dose, red_flags=u.red_flags,
         negated=u.negated, benign=u.benign, watch=u.watch, confidence=u.confidence, evidence=u.evidence,
         evon=out.evon, step_rule=out.step_rule)

    result = {"call_id": call_id, "stage_answered": stage, "transcript": transcript, "stt_ms": stt_ms,
              "stt_mock": stt_mock, "stt_meta": stt_meta, "understanding": u.to_dict(), "evon": out.evon,
              "patient_audio": patient_audio_url, "step_rule": out.step_rule}

    if out.next_prompt:
        url, mock = voices.agent_audio([out.next_prompt.text], p["language"], f"{call_id}_a{s.turn_idx}.wav")
        db.ex("UPDATE calls SET stage=? WHERE id=?", s.dialogue.stage, call_id)
        emit("agent_speaking", call_id=call_id, patient_id=p["id"], text=out.next_prompt.text,
             english=out.next_prompt.english, audio=url, stage=s.dialogue.stage, rule=out.step_rule)
        result.update(closed=False, stage=s.dialogue.stage, agent_audio=url, tts_mock=mock,
                      agent_text=out.next_prompt.text, agent_english=out.next_prompt.english)
        return result

    return {**result, **_finish(s)}


def _finish(s: CallSession) -> dict:
    d = s.dialogue.decision
    p = s.patient
    closing = s.dialogue.closing()
    url, mock = voices.agent_audio([x.text for x in closing], p["language"], f"{s.call_id}_close.wav")
    total_ms = int((time.perf_counter() - s.t_start) * 1000)
    s.trace.update(policy_rule=f"{d.rule}: {d.rule_text}", status=d.status, reasons=d.reasons,
                   actions=[a["tool"] + "(" + a.get("reason", a.get("note", "")) + ")" for a in d.actions]
                   + [f"play_template({k}, {p['language']})" for k in d.say],
                   memory=s.dialogue.mem.to_dict(),
                   latency_ms={"stt_avg": int(sum(s.stt_ms) / len(s.stt_ms)) if s.stt_ms else 0, "total": total_ms})
    db.ex("""UPDATE calls SET state='CLOSED', stage='closed', status=?, rule=?, rule_text=?, reasons_json=?,
             actions_json=?, memory_json=?, trace_json=?, ended_at=? WHERE id=?""",
          d.status, d.rule, d.rule_text, db.j(d.reasons), db.j(d.actions), db.j(s.dialogue.mem.to_dict()),
          db.j(s.trace), db.now(), s.call_id)
    execute_actions(s.call_id, p["id"], s.day, d)
    emit("decided", call_id=s.call_id, patient_id=p["id"], name=p["name"], status=d.status, rule=d.rule,
         rule_text=d.rule_text, reasons=d.reasons, actions=s.trace["actions"], closing_text=" ".join(x.text for x in closing),
         closing_english=" ".join(x.english for x in closing), audio=url, kind=s.kind)
    with _lock:
        _sessions.pop(s.call_id, None)
    return {"closed": True, "status": d.status, "rule": d.rule, "rule_text": d.rule_text, "reasons": d.reasons,
            "agent_audio": url, "tts_mock": mock, "agent_text": " ".join(x.text for x in closing),
            "agent_english": " ".join(x.english for x in closing), "trace": s.trace}


# ----------------------------------------------------------------------------- tools


def execute_actions(call_id: str, pid: str, day: int, d) -> None:
    """The agent's tools. Deterministic side effects only."""
    for a in d.actions:
        if a["tool"] in ("escalate_red", "flag_worker"):
            level = RED if a["tool"] == "escalate_red" else AMBER
            raise_alert(pid, call_id, day, level, d.rule, a.get("reason", ""), a.get("quote", ""))
    log_status(pid, day, d.status, ",".join(d.reasons), call_id)


def raise_alert(pid: str, call_id: str | None, day: int, level: str, rule: str, reason: str, quote: str) -> int:
    aid = db.ex("""INSERT INTO alerts(patient_id, call_id, day, level, rule, reason, quote, created_at)
                   VALUES(?,?,?,?,?,?,?,?)""", pid, call_id, day, level, rule, reason, quote, db.now())
    p = _patient(pid)
    emit("alert", alert_id=aid, patient_id=pid, name=p["name"], level=level, rule=rule, reason=reason, quote=quote,
         call_id=call_id)
    return aid


SEVERITY = {"GREEN": 0, "NO_ANSWER": 1, "AMBER": 2, "RED": 3}


def log_status(pid: str, day: int, status: str, note: str, call_id: str | None) -> None:
    """Adherence calendar. A day's status can only get worse within the day (never mask a red)."""
    cur = db.q1("SELECT status FROM daily_status WHERE patient_id=? AND day=?", pid, day)
    if cur and SEVERITY.get(cur["status"], 0) > SEVERITY.get(status, 0) and cur["status"] != "NO_ANSWER":
        return
    db.ex("""INSERT INTO daily_status(patient_id, day, status, note, call_id) VALUES(?,?,?,?,?)
             ON CONFLICT(patient_id, day) DO UPDATE SET status=excluded.status, note=excluded.note,
             call_id=excluded.call_id""", pid, day, status, note, call_id)


def mark_no_answer(call_id: str) -> None:
    c = db.q1("SELECT * FROM calls WHERE id=?", call_id)
    db.ex("UPDATE calls SET state='NO_ANSWER', stage='closed', status='NO_ANSWER', rule='X1', "
          "rule_text=?, ended_at=? WHERE id=?", "No answer", db.now(), call_id)
    log_status(c["patient_id"], c["day"], "NO_ANSWER", "no_answer", call_id)
    emit("no_answer", call_id=call_id, patient_id=c["patient_id"], attempt=c["attempt"], kind=c["kind"])


def abandon(call_id: str) -> None:
    with _lock:
        _sessions.pop(call_id, None)
    db.ex("UPDATE calls SET state='ABANDONED', stage='closed' WHERE id=? AND state!='CLOSED'", call_id)
