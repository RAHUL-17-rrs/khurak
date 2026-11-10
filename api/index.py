"""Khurak live phone API for Vercel serverless (stateless).

The hosted demo replays a round recorded live against Gnani; this function makes the
Patient-phone page genuinely live: every answer goes to Gnani Prisma v3.0 and through the
same classifier + policy code as the full app.

Serverless has no memory between requests, so the call state (dialogue stage + memory)
travels with the browser, HMAC-signed so it cannot be edited client-side. Agent prompts
are pre-rendered Timbre audio served as static files, so this function never calls TTS.

Credit protection (public URL): audio answers are capped per IP and per instance, answers
are cut at 15 s, and KHURAK_LIVE=0 disables Prisma entirely (typed answers still work).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time
from collections import defaultdict, deque
from pathlib import Path

os.environ.setdefault("KHURAK_STORE", "/tmp/khurak")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

import yaml  # noqa: E402
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from app import gnani  # noqa: E402
from app.config import DATA_DIR, GNANI_API_KEY, LIVE  # noqa: E402
from app.dialogue import Dialogue  # noqa: E402
from app.policy import RULES  # noqa: E402
from app.prompts import PERSONALISED, prompt_lang  # noqa: E402

LIVE_ENABLED = LIVE and os.getenv("KHURAK_LIVE", "1") != "0"
SECRET = (os.getenv("KHURAK_STATE_SECRET") or hashlib.sha256(("khurak|" + GNANI_API_KEY).encode()).hexdigest()).encode()
PER_IP = int(os.getenv("KHURAK_LIVE_PER_IP", "40"))          # audio answers per IP per hour
PER_INSTANCE = int(os.getenv("KHURAK_LIVE_PER_INSTANCE", "400"))
MAX_BYTES = 2_500_000

PATIENTS = {p["id"]: p for p in yaml.safe_load((DATA_DIR / "patients.yaml").read_text(encoding="utf-8"))["patients"]}
SCEN = yaml.safe_load((DATA_DIR / "scenarios.yaml").read_text(encoding="utf-8"))

app = FastAPI(title="Khurak live phone (serverless)")
_hits: dict[str, deque] = defaultdict(deque)
_all: deque = deque()


# ----------------------------------------------------------------------------- helpers


def _sign(st: dict) -> str:
    raw = base64.urlsafe_b64encode(json.dumps(st, ensure_ascii=False).encode()).decode()
    sig = hmac.new(SECRET, raw.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{raw}.{sig}"


def _verify(token: str) -> dict:
    try:
        raw, sig = token.rsplit(".", 1)
    except ValueError:
        raise HTTPException(400, "bad call state")
    if not hmac.compare_digest(sig, hmac.new(SECRET, raw.encode(), hashlib.sha256).hexdigest()[:32]):
        raise HTTPException(400, "call state signature mismatch")
    return json.loads(base64.urlsafe_b64decode(raw.encode()))


def _rate_limit(ip: str) -> None:
    now = time.time()
    for q, limit in ((_hits[ip], PER_IP), (_all, PER_INSTANCE)):
        while q and now - q[0] > 3600:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(429, "Live speech limit reached for this hour (protects the demo's API credits). "
                                     "Typed answers still work.")
    _hits[ip].append(now)
    _all.append(now)


def _audio_url(key: str, lang: str, pid: str) -> str:
    pl = prompt_lang(lang)
    k = f"{key}__{pid}" if key in PERSONALISED else key.replace(":", "__")
    return f"/audio/prompts/{pl}/{k}.wav"


def _prompt_out(prompts, lang: str, pid: str, symptom: str | None = None) -> list[dict]:
    out = []
    for p in prompts:
        key = f"confirm_symptom:{p.vars['symptom']}" if p.key == "confirm_symptom" else p.key
        out.append({"key": key, "text": p.text, "english": p.english, "audio": _audio_url(key, lang, pid)})
    return out


def _dialogue(st: dict) -> Dialogue:
    return Dialogue.from_state(st["dlg"], use_evon=True)


# ----------------------------------------------------------------------------- routes


@app.get("/api/live/status")
def status():
    return {"live": LIVE_ENABLED, "stt_model": gnani.STT_MODEL, "tts_model": gnani.TTS_MODEL,
            "per_ip_per_hour": PER_IP, "max_answer_seconds": 15}


class Start(BaseModel):
    patient_id: str
    kind: str = "patient"


@app.post("/api/live/start")
def start(body: Start):
    p = PATIENTS.get(body.patient_id)
    if not p:
        raise HTTPException(404, "unknown patient")
    d = Dialogue(p["language"], p.get("name_local") or p["name"], body.kind)
    prompts = d.opening()
    st = {"pid": p["id"], "kind": body.kind, "turn": 0, "dlg": d.to_state(), "turns": [],
          "opening": [x.key for x in prompts], "audio_seq": [x["audio"] for x in _prompt_out(prompts, p["language"], p["id"])]}
    po = _prompt_out(prompts, p["language"], p["id"])
    return {"state": _sign(st), "stage": d.stage, "prompts": po, "closed": False}


@app.post("/api/live/answer")
async def answer(request: Request, state: str = Form(...), source: str = Form("live"),
                 text: str | None = Form(None), audio: UploadFile | None = File(None),
                 noise_kind: str | None = Form(None), snr_db: float | None = Form(None),
                 clip_url: str | None = Form(None)):
    st = _verify(state)
    p = PATIENTS[st["pid"]]
    d = _dialogue(st)
    if d.stage == "closed":
        raise HTTPException(409, "call already closed")
    stage = d.stage
    stt_ms, onset, transcript = 0, None, ""

    if source == "typed" or audio is None:
        transcript = (text or "").strip()
        source = "typed"
    else:
        if not LIVE_ENABLED:
            raise HTTPException(503, "Live speech is switched off on this deployment. Use a typed answer.")
        ip = (request.headers.get("x-forwarded-for") or "?").split(",")[0].strip()
        _rate_limit(ip)
        raw = await audio.read()
        if len(raw) > MAX_BYTES:
            raise HTTPException(413, "answer too long (max 15 s)")
        from app import voices
        from app.audio import onset_ms
        if source == "scripted":
            wav = raw                      # already a phone-line clip (Timbre voice + noise + 8 kHz mu-law)
        else:
            try:
                wav = voices.degrade_live(raw, noise_kind if noise_kind in ("street", "construction", "pressure_cooker", "crowd") else None, snr_db)
            except ValueError as e:
                raise HTTPException(400, f"could not read audio: {e}")
            onset = onset_ms(wav)
        prev = " ".join(t["transcript"] for t in st["turns"])[-600:] or None
        r = gnani.transcribe(wav, p["language"], previous_text=prev)
        transcript, stt_ms = r.transcript, r.latency_ms

    out = d.answer(transcript, onset_ms=onset)
    u = out.understanding
    st["turn"] += 1
    st["turns"].append({"stage": stage, "transcript": transcript, "dose": u.dose, "red_flags": u.red_flags,
                        "negated": u.negated, "benign": u.benign, "watch": u.watch, "confidence": u.confidence,
                        "evidence": u.evidence, "stt_ms": stt_ms, "source": source, "evon": out.evon,
                        "step_rule": out.step_rule, "patient_audio": clip_url if source == "scripted" else None,
                        "onset_ms": onset})
    if clip_url and source == "scripted":
        st["audio_seq"].append(clip_url)
    res = {"stage_answered": stage, "transcript": transcript, "stt_ms": stt_ms, "stt_mock": not LIVE_ENABLED,
           "understanding": u.to_dict(), "evon": out.evon, "step_rule": out.step_rule,
           "patient_audio": clip_url if source == "scripted" else None}

    if out.next_prompt:
        po = _prompt_out([out.next_prompt], p["language"], p["id"])
        st["audio_seq"] += [x["audio"] for x in po]
        st["dlg"] = d.to_state()
        return {**res, "state": _sign(st), "closed": False, "stage": d.stage, "prompts": po}

    dec = d.decision
    po = _prompt_out(d.closing(), p["language"], p["id"])
    st["audio_seq"] += [x["audio"] for x in po]
    st["dlg"] = d.to_state()
    trace = {"call_id": None, "patient": p["name"], "patient_id": p["id"], "language": p["language"],
             "kind": st["kind"], "day": SCEN.get("demo_day", 19), "turns": st["turns"],
             "policy_rule": f"{dec.rule}: {dec.rule_text}", "status": dec.status, "reasons": dec.reasons,
             "actions": [a["tool"] + "(" + a.get("reason", a.get("note", "")) + ")" for a in dec.actions]
             + [f"play_template({k}, {p['language']})" for k in dec.say],
             "memory": d.mem.to_dict(), "mode": "live" if LIVE_ENABLED else "mock",
             "latency_ms": {"stt_avg": int(sum(t["stt_ms"] for t in st["turns"]) / max(1, len(st["turns"]))),
                            "total": 0},
             "audio_sequence": st["audio_seq"]}
    return {**res, "state": _sign(st), "closed": True, "status": dec.status, "rule": dec.rule,
            "rule_text": dec.rule_text, "reasons": dec.reasons, "prompts": po, "trace": trace,
            "rules": {k: RULES[k] for k in (dec.rule,)}}
