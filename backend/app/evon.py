"""Gnani Evon v3.3 (open 30B-A3B Indic LLM) - optional, and OUT of the decision path.

Evon is published as open weights (huggingface.co/gnani/gnani-evon-v3.3-30B-A3B), not on
Gnani's hosted API, so Khurak talks to any OpenAI-compatible server that hosts it:
llama.cpp `llama-server`, vLLM, LM Studio, Ollama... (see deploy/evon_kaggle.py for a free
Kaggle-GPU recipe). Configure with EVON_BASE_URL / EVON_MODEL / EVON_API_KEY.

Two jobs, both safe by construction:
1. second_opinion(): a "second listener" that re-reads each patient transcript. The policy
   engine only uses it to ADD a human review (rule R6c); it can never lower a status, and
   it never produces words the patient hears.
2. case_note(): a short narrative for the health worker summarising a patient's recent calls.
"""
from __future__ import annotations

import json
import os
import re
import time

import httpx

from . import config  # noqa: F401  (loads .env before reading EVON_* vars)

EVON_BASE_URL = os.getenv("EVON_BASE_URL", "").rstrip("/")
EVON_MODEL = os.getenv("EVON_MODEL", "gnani-evon-v3.3")
EVON_API_KEY = os.getenv("EVON_API_KEY", "")
EVON_TIMEOUT = float(os.getenv("EVON_TIMEOUT", "20"))

RED_FLAG_NAMES = ["yellow_eyes", "blood_cough", "persistent_vomit", "breathless", "vision", "rash"]

_state = {"ok": None, "checked": 0.0, "error": ""}


def enabled() -> bool:
    return bool(EVON_BASE_URL)


def health(force: bool = False) -> dict:
    if not enabled():
        return {"enabled": False, "online": False, "model": EVON_MODEL,
                "note": "Set EVON_BASE_URL to an OpenAI-compatible server hosting Evon"}
    if force or time.time() - _state["checked"] > 60:
        try:
            r = httpx.get(f"{EVON_BASE_URL}/v1/models", headers=_headers(), timeout=5)
            _state.update(ok=r.status_code < 400, error="" if r.status_code < 400 else r.text[:200])
        except httpx.HTTPError as e:
            _state.update(ok=False, error=str(e)[:200])
        _state["checked"] = time.time()
    return {"enabled": True, "online": bool(_state["ok"]), "model": EVON_MODEL,
            "base_url": EVON_BASE_URL, "error": _state["error"]}


def _headers() -> dict:
    return {"Authorization": f"Bearer {EVON_API_KEY}"} if EVON_API_KEY else {}


def _chat(messages: list[dict], max_tokens: int = 300, temperature: float = 0.0) -> str | None:
    if not enabled() or _state["ok"] is False and time.time() - _state["checked"] < 60:
        return None
    try:
        r = httpx.post(f"{EVON_BASE_URL}/v1/chat/completions", headers=_headers(), timeout=EVON_TIMEOUT,
                       json={"model": EVON_MODEL, "messages": messages, "max_tokens": max_tokens,
                             "temperature": temperature, "repetition_penalty": 1.1,
                             # Evon reasons by default; short structured answers want it off
                             "chat_template_kwargs": {"enable_thinking": False}})
        r.raise_for_status()
        _state.update(ok=True, checked=time.time())
        text = r.json()["choices"][0]["message"]["content"] or ""
        return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    except (httpx.HTTPError, KeyError, ValueError) as e:
        _state.update(ok=False, checked=time.time(), error=str(e)[:200])
        return None


SECOND_OPINION_SYS = (
    "You review transcripts of a daily tuberculosis medicine check-in phone call in Indian "
    "languages (Hindi, Marathi, Bengali, Kannada, Hinglish). The transcript comes from speech "
    "recognition and may contain errors. Reply with ONLY a JSON object:\n"
    '{"dose": "TAKEN|MISSED|STOPPED|UNCLEAR", "red_flags": [..], "concern": "<snake_case or empty>", '
    '"english": "<faithful English translation>"}\n'
    f"red_flags may only contain: {', '.join(RED_FLAG_NAMES)}. Include a red flag only if the "
    "patient says they HAVE it (not if they deny it). concern = any other worrying thing a health "
    "worker should hear about (e.g. suicidal_thoughts, cannot_afford_travel, pregnancy, alcohol, "
    "severe_pain), else empty. Never give medical advice."
)


def second_opinion(transcript: str, lang: str, question_en: str) -> dict | None:
    if not transcript.strip():
        return None
    out = _chat([
        {"role": "system", "content": SECOND_OPINION_SYS},
        {"role": "user", "content": f"Language: {lang}\nAgent asked: {question_en}\nPatient said: {transcript}"},
    ], max_tokens=250)
    if not out:
        return None
    m = re.search(r"\{.*\}", out, flags=re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    data["red_flags"] = [r for r in data.get("red_flags", []) if r in RED_FLAG_NAMES]
    data["concern"] = re.sub(r"[^a-z_]", "", str(data.get("concern", "")).lower())[:40]
    return data


def concerns_beyond_rules(opinion: dict | None, rule_red: list[str], rule_negated: list[str]) -> list[dict]:
    """Escalation-only merge: what did Evon hear that the rules did not?"""
    if not opinion:
        return []
    out = []
    for r in opinion.get("red_flags", []):
        if r not in rule_red:
            out.append({"concern": f"possible_{r}", "source": "evon",
                        "note": "Evon heard a possible danger sign the rules did not; human to verify"})
    if opinion.get("concern"):
        out.append({"concern": opinion["concern"], "source": "evon"})
    return out


def case_note(patient: dict, history: list[dict]) -> str | None:
    lines = [f"Day {h['day']}: {h['status']} ({h.get('rule') or '-'}) - " + " / ".join(h.get("quotes", []))[:300]
             for h in history[-10:]]
    return _chat([
        {"role": "system", "content": (
            "You write 3-4 sentence case notes for an Indian TB health worker (ASHA/ANM). Plain English, "
            "factual, no diagnosis, no medical advice, no invented facts. Mention adherence pattern, side "
            "effects reported (quote the patient's own words briefly) and what needs follow-up.")},
        {"role": "user", "content": (
            f"Patient: {patient['name']}, {patient['age']}, {patient['city']}, language {patient['language']}, "
            f"treatment day {patient.get('treatment_day')}.\nRecent calls:\n" + "\n".join(lines))},
    ], max_tokens=220, temperature=0.2)
