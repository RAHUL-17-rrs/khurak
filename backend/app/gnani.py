"""Thin, dependency-light wrappers around Gnani's REST APIs.

* Prisma v3.0 (STT): POST https://api.vachana.ai/stt/v3   (multipart/form-data)
    fields: audio_file, model=prisma-v3.0, language_code (1-4 comma separated),
            format, topic, keyterms (JSON array)
* Timbre v3.0 (TTS): POST https://api.vachana.ai/api/v1/tts/inference   (JSON)
    fields: text, model=timbre-v3.0, voice, language, speed, audio_config

Mock mode (no API key) keeps the whole product runnable offline: TTS returns a
placeholder hum and STT returns the scripted text it was given as a hint. Every
mock result is flagged `mock: True` so it can never be mistaken for a real one.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass, field

import httpx

from . import audio
from .config import (
    GNANI_API_KEY, LIVE, STT_MODEL, STT_URL, TTS_CACHE_DIR, TTS_MODEL, TTS_URL,
)

TOPIC = (
    "Daily tuberculosis (TB) medicine check-in phone call between a health-centre voice "
    "agent and a patient. The patient says whether they took today's TB tablets and "
    "describes side effects such as vomiting, yellow eyes, orange urine, cough with blood, "
    "breathlessness, rash or blurred vision."
)

# Prisma v3.0 keyterm boosting (max 200). Drug names, symptom words and the short
# yes/no words that phone answers are made of, in all supported languages.
KEYTERMS: dict[str, list[str]] = {
    "common": ["TB", "टीबी", "Rifampicin", "Isoniazid", "Ethambutol", "Pyrazinamide", "108"],
    "hi-IN": ["दवा", "गोली", "हाँ", "नहीं", "ले ली", "पीलिया", "पीली", "उल्टी", "खून",
              "खांसी", "पेशाब", "लाल", "नारंगी", "सांस", "धुंधला", "दाने", "खुजली", "बंद कर दी"],
    "mr-IN": ["गोळी", "औषध", "होय", "हो", "नाही", "घेतली", "पिवळे", "उलटी", "रक्त", "खोकला",
              "लघवी", "लाल", "नारिंगी", "दम", "धूसर", "पुरळ", "बंद केली"],
    "bn-IN": ["ওষুধ", "ট্যাবলেট", "হ্যাঁ", "না", "খেয়েছি", "খাইনি", "হলুদ", "জন্ডিস", "বমি", "রক্ত",
              "কাশি", "প্রস্রাব", "লাল", "কমলা", "শ্বাসকষ্ট", "ঝাপসা", "চুলকানি", "বন্ধ করে দিয়েছি"],
    "kn-IN": ["ಮಾತ್ರೆ", "ಹೌದು", "ಇಲ್ಲ", "ತೆಗೆದುಕೊಂಡೆ", "ಹಳದಿ", "ವಾಂತಿ", "ರಕ್ತ", "ಕೆಮ್ಮು",
              "ಮೂತ್ರ", "ಕೆಂಪು", "ಉಸಿರು", "ಮಸುಕು", "ತುರಿಕೆ", "ನಿಲ್ಲಿಸಿದೆ"],
}


class GnaniError(RuntimeError):
    pass


class GnaniClientError(GnaniError):
    """4xx (except 429): bad key, no credits, bad request. Retrying will not help."""


def _check(r: httpx.Response, who: str) -> None:
    if r.status_code < 400:
        return
    msg = f"{who} HTTP {r.status_code}: {r.text[:300]}"
    if r.status_code == 429 or r.status_code >= 500:
        raise GnaniError(msg)
    raise GnaniClientError(msg)


@dataclass
class STTResult:
    transcript: str
    latency_ms: int
    mock: bool = False
    detected_language: str | None = None
    raw: dict = field(default_factory=dict)


def _headers() -> dict:
    return {"X-API-Key-ID": GNANI_API_KEY}


# Gnani programme keys allow ONE in-flight request at a time (HTTP 429 otherwise), so every
# call goes through this process-wide lock. Latency is measured inside the lock (network only).
_api_lock = threading.Lock()
stats = {"stt_calls": 0, "tts_calls": 0, "retries": 0}


def _post(who: str, url: str, timeout: float, **kw) -> tuple[httpx.Response, int]:
    last_err: Exception | None = None
    for attempt in range(6):
        with _api_lock:
            t0 = time.perf_counter()
            try:
                r = httpx.post(url, timeout=timeout, **kw)
                ms = int((time.perf_counter() - t0) * 1000)
                _check(r, who)
                return r, ms
            except GnaniClientError:
                raise
            except (httpx.HTTPError, GnaniError) as e:
                last_err = e
        stats["retries"] += 1
        time.sleep(min(8.0, 0.6 * 2 ** attempt))
    raise GnaniError(str(last_err))


def stt_language_code(lang: str) -> str:
    """Patients pick their language. Hinglish speakers get hi-IN + en-IN candidates."""
    return "hi-IN,en-IN" if lang == "hi-en" else lang


def keyterms_for(lang: str) -> list[str]:
    base = KEYTERMS["common"] + KEYTERMS.get("hi-IN" if lang == "hi-en" else lang, [])
    if lang == "hi-en":
        base += ["dawai", "tablet", "theek", "band kar di", "yellow", "blood", "vomiting"]
    return base[:200]


def transcribe(wav: bytes, lang: str, *, boost: bool = True, hint_text: str | None = None,
               previous_text: str | None = None, timeout: float = 45.0) -> STTResult:
    """Speech -> text with Prisma v3.0. `hint_text` is only used in mock mode."""
    if not LIVE:
        time.sleep(0.25)
        return STTResult(transcript=hint_text or "", latency_ms=250, mock=True)

    data = {
        "model": STT_MODEL,
        "language_code": stt_language_code(lang),
        "format": "codemix",
    }
    if STT_MODEL.startswith("prisma-v3"):
        data["topic"] = TOPIC
        if boost:
            data["keyterms"] = json.dumps(keyterms_for(lang), ensure_ascii=False)
        if previous_text:
            data["previous_text"] = previous_text[-600:]
    r, ms = _post("Prisma", STT_URL, timeout, headers=_headers(), data=data,
                  files={"audio_file": ("answer.wav", wav, "audio/wav")})
    stats["stt_calls"] += 1
    body = r.json()
    return STTResult(
        transcript=(body.get("transcript") or "").strip(),
        latency_ms=ms,
        detected_language=body.get("detected_language_code"),
        raw={k: v for k, v in body.items() if k != "transcript"},
    )


def synthesize(text: str, lang: str, voice: str, *, phone: bool = True, speed: float = 1.0,
               use_cache: bool = True) -> tuple[bytes, bool]:
    """Text -> WAV bytes with Timbre v3.0. Returns (wav_bytes, is_mock).

    phone=True asks Timbre for 8 kHz linear PCM WAV, i.e. what a phone line carries.
    Results are cached on disk by content hash, so templates cost credits only once.
    """
    tts_lang = "hi-en" if lang == "hi-en" else lang
    sr = 8000 if phone else 24000
    key = hashlib.sha1(f"{TTS_MODEL}|{voice}|{tts_lang}|{sr}|{speed}|{text}".encode()).hexdigest()[:20]
    cached = TTS_CACHE_DIR / f"{key}.wav"
    if use_cache and cached.exists():
        return cached.read_bytes(), False

    if not LIVE:
        return audio.placeholder_voice(text, sr), True

    payload = {
        "text": text,
        "model": TTS_MODEL,
        "voice": voice,
        "language": tts_lang,
        "speed": speed,
        "audio_config": {"sample_rate": sr, "num_channels": 1, "sample_width": 2,
                         "encoding": "linear_pcm", "container": "wav"},
    }
    r, _ = _post("Timbre", TTS_URL, 90, headers={**_headers(), "Content-Type": "application/json"}, json=payload)
    stats["tts_calls"] += 1
    wav = r.content
    if wav[:4] != b"RIFF":
        raise GnaniError(f"Timbre returned non-WAV payload ({r.headers.get('content-type')})")
    cached.write_bytes(wav)
    return wav, False


def status() -> dict:
    return {"mode": "live" if LIVE else "mock", "stt_model": STT_MODEL, "tts_model": TTS_MODEL,
            "key_present": bool(GNANI_API_KEY), "api_stats": stats}
