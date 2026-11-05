"""Audio production for calls.

* Agent prompts: Timbre v3.0, one warm voice, 8 kHz phone quality, cached forever.
* Synthetic patient answers: Timbre v3.0 in the patient's own voice (with audio tags such as
  <coughs>), mixed with background noise at a target SNR, then pushed through a simulated
  phone line (300-3400 Hz band-pass, 8 kHz, G.711 mu-law). Fully synthetic, fully reproducible.
"""
from __future__ import annotations

import hashlib
import re

import numpy as np

from . import audio, gnani
from .config import AGENT_VOICE, CLIP_DIR, REC_DIR
from .prompts import prompt_lang


def strip_tags(text: str) -> str:
    return re.sub(r"\s*<[^>]+>\s*", " ", text).strip()


def agent_audio(texts: list[str], lang: str, out_name: str) -> tuple[str, bool]:
    """Render prompts (cached per sentence) and join them with short pauses -> /audio/rec/<name>."""
    parts, mock = [], False
    for t in texts:
        wav, m = gnani.synthesize(t, prompt_lang(lang), AGENT_VOICE, phone=True)
        mock |= m
        x, sr = audio.read_wav_bytes(wav)
        x = audio.resample(x, sr, 8000)
        parts += [x, np.zeros(int(0.35 * 8000), np.float32)]
    y = np.concatenate(parts) if parts else np.zeros(800, np.float32)
    audio.write_wav(REC_DIR / out_name, y, 8000)
    return f"/audio/rec/{out_name}", mock


def patient_clip(text: str, lang: str, voice: str, noise_kind: str | None = None,
                 snr_db: float | None = None) -> tuple[bytes, str, bool]:
    """Synthetic patient answer as an 8 kHz phone-line WAV. Returns (wav, cache_name, is_mock)."""
    tts_lang = "hi-en" if lang == "hi-en" else lang
    key = hashlib.sha1(f"{text}|{tts_lang}|{voice}|{noise_kind}|{snr_db}".encode()).hexdigest()[:16]
    name = f"clip_{key}.wav"
    path = CLIP_DIR / name
    raw, mock = gnani.synthesize(text, tts_lang, voice, phone=False)
    if path.exists() and not mock:
        return path.read_bytes(), name, False
    x, sr = audio.read_wav_bytes(raw)
    x = audio.resample(x, sr, 16000)
    x = np.concatenate([np.zeros(3200, np.float32), audio.normalize(x, 0.8), np.zeros(3200, np.float32)])
    if noise_kind and snr_db is not None and not mock:
        x = audio.mix_noise(x, audio.synth_noise(noise_kind, seconds=len(x) / 16000 + 1), snr_db)
    y, _ = audio.phone_degrade(x, 16000)
    wav = audio.wav_bytes(y, 8000)
    if not mock:
        path.write_bytes(wav)
    return wav, name, mock


def degrade_live(wav: bytes, noise_kind: str | None = None, snr_db: float | None = None) -> bytes:
    """Browser-mic answer -> optional noise -> phone line."""
    x, sr = audio.read_wav_bytes(wav)
    x = audio.resample(x, sr, 16000)[: 16000 * 15]
    x = audio.normalize(x, 0.8)
    if noise_kind and snr_db is not None:
        x = audio.mix_noise(x, audio.synth_noise(noise_kind, seconds=len(x) / 16000 + 1), snr_db)
    y, _ = audio.phone_degrade(x, 16000)
    return audio.wav_bytes(y, 8000)
