"""Khurak API. Run:  uvicorn app.main:app --reload --port 8000   (from backend/)"""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import briefing, db, events, evon, gnani, orchestrator, scheduler, voices
from .audio import NOISE_KINDS
from .config import (BRIEF_DIR, CLIP_DIR, EVAL_DIR, FRONTEND_DIST, MAX_ANSWER_SECONDS, REC_DIR)
from .policy import RULES
from .prompts import ENGLISH, LANG_NAMES, TEMPLATES


@asynccontextmanager
async def lifespan(app: FastAPI):
    events.bind_loop(asyncio.get_running_loop())
    scheduler.ensure_seeded()
    yield


app = FastAPI(title="Khurak", version="1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/audio/rec", StaticFiles(directory=REC_DIR), name="rec")
app.mount("/audio/clips", StaticFiles(directory=CLIP_DIR), name="clips")
app.mount("/audio/briefings", StaticFiles(directory=BRIEF_DIR), name="briefings")


@app.exception_handler(orchestrator.CallError)
async def _call_error(_: Request, e: orchestrator.CallError):
    return JSONResponse({"detail": str(e)}, status_code=409)


@app.exception_handler(gnani.GnaniError)
async def _gnani_error(_: Request, e: gnani.GnaniError):
    return JSONResponse({"detail": f"Gnani API error: {e}"}, status_code=502)


# ----------------------------------------------------------------------------- status


@app.get("/api/status")
def status():
    return {**gnani.status(), "evon": evon.health(), "day": scheduler.current_day(),
            "round": scheduler.state, "worker": db.kv_get("worker"), "languages": LANG_NAMES,
            "noise_kinds": NOISE_KINDS, "max_answer_seconds": MAX_ANSWER_SECONDS}


@app.get("/api/policy")
def policy():
    return {"rules": RULES, "templates": TEMPLATES, "english": ENGLISH}


# ----------------------------------------------------------------------------- patients


def _today_status(pid: str, day: int) -> dict | None:
    return db.q1("SELECT status, note, call_id FROM daily_status WHERE patient_id=? AND day=?", pid, day)


@app.get("/api/patients")
def patients():
    day = scheduler.current_day()
    out = []
    for r in db.q("SELECT * FROM patients WHERE active=1 ORDER BY call_time"):
        p = db.patient_row(r)
        cal = db.q("SELECT status FROM daily_status WHERE patient_id=? AND day<=? ORDER BY day", p["id"], day)
        taken = sum(1 for c in cal if c["status"] in ("GREEN", "RED"))
        p.update(today=_today_status(p["id"], day), treatment_day=day - p["start_day"] + 1,
                 adherence=round(100 * taken / max(1, len(cal))),
                 open_alerts=db.q1("SELECT COUNT(*) n FROM alerts WHERE patient_id=? AND resolved=0", p["id"])["n"],
                 strip=[c["status"] for c in cal][-30:])
        out.append(p)
    return out


@app.get("/api/patients/{pid}")
def patient(pid: str):
    r = db.q1("SELECT * FROM patients WHERE id=?", pid)
    if not r:
        raise HTTPException(404, "patient not found")
    p = db.patient_row(r)
    day = scheduler.current_day()
    calls = [db.call_row(c) for c in db.q("SELECT * FROM calls WHERE patient_id=? ORDER BY day DESC, started_at DESC", pid)]
    for c in calls:
        c["turns"] = [db.turn_row(t) for t in db.q("SELECT * FROM turns WHERE call_id=? ORDER BY idx", c["id"])]
    return {**p, "treatment_day": day - p["start_day"] + 1, "day": day,
            "calendar": db.q("SELECT day, status, note, call_id FROM daily_status WHERE patient_id=? ORDER BY day", pid),
            "calls": calls,
            "alerts": db.q("SELECT * FROM alerts WHERE patient_id=? ORDER BY id DESC", pid)}


@app.post("/api/patients/{pid}/case-note")
def case_note(pid: str):
    p = patient(pid)
    hist = [{"day": c["day"], "status": c["status"], "rule": c["rule"],
             "quotes": [t["transcript"] for t in c["turns"]]} for c in reversed(p["calls"]) if c["status"]]
    note = evon.case_note(p, hist)
    if not note:
        raise HTTPException(503, "Evon is not connected (set EVON_BASE_URL). Rules-only mode is unaffected.")
    return {"note": note, "model": evon.EVON_MODEL}


# ----------------------------------------------------------------------------- daily round


class RunDay(BaseModel):
    day: int | None = None
    pace: float = 1.0
    patient_ids: list[str] | None = None


@app.post("/api/day/run")
async def run_day(body: RunDay):
    if scheduler.state["running"]:
        raise HTTPException(409, "a round is already running")
    day = body.day or scheduler.current_day()
    asyncio.create_task(scheduler.run_day(day, max(0.0, min(body.pace, 3.0)), body.patient_ids))
    return {"started": True, "day": day}


@app.post("/api/day/next")
def next_day():
    d = scheduler.current_day() + 1
    db.kv_set("current_day", d)
    events.emit("day_changed", day=d)
    return {"day": d}


@app.post("/api/reset")
def reset():
    if scheduler.state["running"]:
        raise HTTPException(409, "a round is running")
    scheduler.seed(reset=True)
    return {"ok": True, "day": scheduler.current_day()}


# ----------------------------------------------------------------------------- calls


class StartCall(BaseModel):
    patient_id: str
    kind: str = "patient"


@app.post("/api/calls/start")
def start_call(body: StartCall):
    day = scheduler.current_day()
    n = db.q1("SELECT COUNT(*) n FROM calls WHERE patient_id=? AND day=? AND kind=? AND seeded=0",
              body.patient_id, day, body.kind)["n"]
    cid = orchestrator.create_call(body.patient_id, day, n + 1, body.kind, source="phone")
    return orchestrator.answer_call(cid)


@app.post("/api/calls/{call_id}/answer")
async def answer(call_id: str, audio: UploadFile | None = File(None), text: str | None = Form(None),
                 source: str = Form("live"), noise_kind: str | None = Form(None),
                 snr_db: float | None = Form(None)):
    s = orchestrator.get_session(call_id)
    if source == "scripted":
        p, stage = s.patient, s.dialogue.stage
        return await asyncio.to_thread(scheduler.scripted_turn, call_id, p, s.day, stage, s.kind)
    if text is not None and audio is None:
        return await asyncio.to_thread(orchestrator.take_turn, call_id, text=text, source="typed")
    if audio is None:
        raise HTTPException(400, "send `audio` (WAV) or `text`")
    raw = await audio.read()
    if len(raw) > 6_000_000:
        raise HTTPException(413, "answer too long")
    try:
        wav = voices.degrade_live(raw, noise_kind if noise_kind in NOISE_KINDS else None, snr_db)
    except ValueError as e:
        raise HTTPException(400, f"could not read audio: {e}")
    return await asyncio.to_thread(orchestrator.take_turn, call_id, wav=wav, source="live")


@app.get("/api/calls/{call_id}/scripted")
def scripted_preview(call_id: str):
    s = orchestrator.get_session(call_id)
    t = scheduler.scripted_answer(s.patient, s.day, s.dialogue.stage, s.kind)
    return {"stage": s.dialogue.stage, "text": voices.strip_tags(t) if t else None}


@app.post("/api/calls/{call_id}/no-answer")
def no_answer(call_id: str):
    orchestrator.abandon(call_id)
    orchestrator.mark_no_answer(call_id)
    c = db.q1("SELECT * FROM calls WHERE id=?", call_id)
    attempts = db.q1("SELECT COUNT(*) n FROM calls WHERE patient_id=? AND day=? AND kind='patient' AND "
                     "state='NO_ANSWER'", c["patient_id"], c["day"])["n"]
    nxt = "call_family" if attempts >= 2 else "retry_in_2h"
    events.emit("retry_scheduled" if nxt == "retry_in_2h" else "family_call", patient_id=c["patient_id"],
                rule="X1" if nxt == "retry_in_2h" else "X2")
    return {"ok": True, "unanswered_today": attempts, "next": nxt}


@app.post("/api/calls/{call_id}/hangup")
def hangup(call_id: str):
    orchestrator.abandon(call_id)
    return {"ok": True}


@app.get("/api/calls/{call_id}")
def get_call(call_id: str):
    c = db.q1("SELECT * FROM calls WHERE id=?", call_id)
    if not c:
        raise HTTPException(404, "call not found")
    c = db.call_row(c)
    c["turns"] = [db.turn_row(t) for t in db.q("SELECT * FROM turns WHERE call_id=? ORDER BY idx", call_id)]
    c["patient"] = db.patient_row(db.q1("SELECT * FROM patients WHERE id=?", c["patient_id"]))
    return c


@app.get("/api/calls")
def list_calls(day: int | None = None):
    day = day or scheduler.current_day()
    rows = db.q("""SELECT c.*, p.name, p.language FROM calls c JOIN patients p ON p.id=c.patient_id
                   WHERE c.day=? AND c.seeded=0 ORDER BY c.started_at""", day)
    return [db.call_row(r) for r in rows]


# ----------------------------------------------------------------------------- alerts + briefing


@app.get("/api/alerts")
def alerts(level: str | None = None, day: int | None = None, resolved: int = 0):
    sql = """SELECT a.*, p.name, p.language, p.city, p.age FROM alerts a JOIN patients p ON p.id=a.patient_id
             WHERE a.resolved=?"""
    args: list = [resolved]
    if level:
        sql += " AND a.level=?"
        args.append(level.upper())
    if day:
        sql += " AND a.day=?"
        args.append(day)
    sql += " ORDER BY CASE a.level WHEN 'RED' THEN 0 ELSE 1 END, a.id DESC"
    return db.q(sql, *args)


class Resolve(BaseModel):
    note: str = "Visited / called"


@app.post("/api/alerts/{aid}/resolve")
def resolve(aid: int, body: Resolve):
    db.ex("UPDATE alerts SET resolved=1, resolved_at=?, resolution=? WHERE id=?", db.now(), body.note, aid)
    events.emit("alert_resolved", alert_id=aid)
    return {"ok": True}


@app.get("/api/briefing")
def get_briefing(day: int | None = None):
    return briefing.build(day or scheduler.current_day())


# ----------------------------------------------------------------------------- evaluation


@app.get("/api/eval")
def eval_report():
    f = EVAL_DIR / "report.json"
    if not f.exists():
        raise HTTPException(404, "no evaluation yet: run `python scripts/evaluate.py`")
    return json.loads(f.read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------- SSE


@app.get("/api/events")
async def sse(request: Request):
    q = events.subscribe()

    async def gen():
        try:
            yield f"data: {json.dumps({'type': 'hello', 'recent': list(events.recent)[-60:]}, ensure_ascii=False, default=str)}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {msg}\n\n"
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            events.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ----------------------------------------------------------------------------- frontend (single-port deploy)

if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        f = FRONTEND_DIST / full_path
        if full_path and f.is_file():
            return FileResponse(f)
        return FileResponse(FRONTEND_DIST / "index.html")
