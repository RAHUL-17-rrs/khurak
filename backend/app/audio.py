"""Audio utilities: WAV I/O, phone-line simulation (300-3400 Hz, 8 kHz, G.711 mu-law),
noise mixing at a target SNR, and procedural (fully synthetic) background noise.

Only numpy/scipy + stdlib `wave` are used, so no ffmpeg is required anywhere.
"""
from __future__ import annotations

import io
import wave
from math import gcd
from pathlib import Path

import numpy as np
from scipy.signal import butter, resample_poly, sosfilt

from .config import DATA_DIR, PHONE_SR

# ----------------------------------------------------------------------------- I/O


def read_wav_bytes(data: bytes) -> tuple[np.ndarray, int]:
    """Decode a PCM WAV (8/16/32-bit int, or mu-law) into mono float32 in [-1, 1]."""
    if data[:4] != b"RIFF":
        raise ValueError("not a WAV file")
    fmt_tag = int.from_bytes(data[20:22], "little")
    if fmt_tag in (3, 7):  # float or mu-law: parse manually
        return _read_wav_manual(data)
    with wave.open(io.BytesIO(data)) as w:
        sr, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    if width == 2:
        x = np.frombuffer(raw, "<i2").astype(np.float32) / 32768.0
    elif width == 1:
        x = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128) / 128.0
    elif width == 4:
        x = np.frombuffer(raw, "<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"unsupported sample width {width}")
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


def _read_wav_manual(data: bytes) -> tuple[np.ndarray, int]:
    pos, fmt, sr, ch, bits, payload = 12, None, 8000, 1, 16, b""
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], int.from_bytes(data[pos + 4:pos + 8], "little")
        body = data[pos + 8:pos + 8 + size]
        if cid == b"fmt ":
            fmt = int.from_bytes(body[0:2], "little")
            ch = int.from_bytes(body[2:4], "little")
            sr = int.from_bytes(body[4:8], "little")
            bits = int.from_bytes(body[14:16], "little")
        elif cid == b"data":
            payload = body
        pos += 8 + size + (size & 1)
    if fmt == 7:
        x = ulaw_decode(np.frombuffer(payload, np.uint8))
    elif fmt == 3:
        x = np.frombuffer(payload, "<f4" if bits == 32 else "<f8").astype(np.float32)
    else:
        raise ValueError("unsupported WAV format")
    if ch > 1:
        x = x.reshape(-1, ch).mean(axis=1)
    return x, sr


def read_wav(path: str | Path) -> tuple[np.ndarray, int]:
    return read_wav_bytes(Path(path).read_bytes())


def wav_bytes(x: np.ndarray, sr: int) -> bytes:
    pcm = (np.clip(x, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    return buf.getvalue()


def write_wav(path: str | Path, x: np.ndarray, sr: int) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(wav_bytes(x, sr))
    return path


def duration_s(data: bytes) -> float:
    x, sr = read_wav_bytes(data)
    return len(x) / sr


# ----------------------------------------------------------------------------- DSP


def resample(x: np.ndarray, sr_from: int, sr_to: int) -> np.ndarray:
    if sr_from == sr_to:
        return x.astype(np.float32)
    g = gcd(sr_from, sr_to)
    return resample_poly(x, sr_to // g, sr_from // g).astype(np.float32)


MU = 255.0


def ulaw_encode(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, -1, 1)
    y = np.sign(x) * np.log1p(MU * np.abs(x)) / np.log1p(MU)
    return ((y + 1) / 2 * 255 + 0.5).astype(np.uint8)


def ulaw_decode(u: np.ndarray) -> np.ndarray:
    y = u.astype(np.float32) / 255 * 2 - 1
    return (np.sign(y) * ((1 + MU) ** np.abs(y) - 1) / MU).astype(np.float32)


def phone_degrade(x: np.ndarray, sr: int) -> tuple[np.ndarray, int]:
    """What a real PSTN/GSM line does: band-limit 300-3400 Hz, 8 kHz, 8-bit mu-law."""
    if sr < 8000:
        x, sr = resample(x, sr, 16000), 16000
    sos = butter(6, [300, 3400], btype="band", fs=sr, output="sos")
    y = sosfilt(sos, x).astype(np.float32)
    y = resample(y, sr, PHONE_SR)
    y = ulaw_decode(ulaw_encode(y))
    return y, PHONE_SR


def normalize(x: np.ndarray, peak: float = 0.9) -> np.ndarray:
    m = float(np.max(np.abs(x))) if len(x) else 0.0
    return (x / m * peak).astype(np.float32) if m > 1e-6 else x.astype(np.float32)


def trim_silence(x: np.ndarray, sr: int, thresh: float = 0.01) -> np.ndarray:
    idx = np.where(np.abs(x) > thresh)[0]
    if len(idx) == 0:
        return x
    pad = int(0.15 * sr)
    return x[max(0, idx[0] - pad): min(len(x), idx[-1] + pad)]


def onset_ms(data: bytes, frame_ms: int = 20) -> int:
    """Silence before speech starts: first 20 ms frame whose energy exceeds 15% of the loudest frame."""
    x, sr = read_wav_bytes(data)
    n = max(1, int(sr * frame_ms / 1000))
    if len(x) < n:
        return 0
    frames = x[: len(x) // n * n].reshape(-1, n)
    e = np.sqrt((frames.astype(np.float64) ** 2).mean(axis=1))
    peak = float(e.max())
    if peak < 1e-4:
        return 0
    idx = int(np.argmax(e > 0.15 * peak))
    return idx * frame_ms


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(x.astype(np.float64) ** 2) + 1e-12))


def mix_noise(speech: np.ndarray, noise: np.ndarray, snr_db: float) -> np.ndarray:
    """Add noise so that 10*log10(P_speech / P_noise) == snr_db."""
    if len(noise) < len(speech):
        noise = np.tile(noise, int(np.ceil(len(speech) / len(noise))))
    noise = noise[: len(speech)]
    p_s, p_n = rms(speech) ** 2, rms(noise) ** 2
    scale = np.sqrt(p_s / (p_n * 10 ** (snr_db / 10)))
    out = speech + noise * scale
    m = float(np.max(np.abs(out)))
    return (out / m * 0.95).astype(np.float32) if m > 0.99 else out.astype(np.float32)


def to_phone_wav(data: bytes, max_seconds: float | None = None) -> bytes:
    """Any incoming WAV (browser mic, Timbre output) -> 8 kHz mono phone-quality WAV."""
    x, sr = read_wav_bytes(data)
    if max_seconds:
        x = x[: int(max_seconds * sr)]
    x = trim_silence(normalize(x), sr)
    y, sr2 = phone_degrade(x, sr)
    return wav_bytes(y, sr2)


# ----------------------------------------------------------------------------- synthetic noise
#
# Real-world noise beds generated procedurally (no recordings, no licensing).
# If you record your own (street, TV, pressure cooker...) drop 16 kHz+ WAVs into
# backend/data/noise/<name>.wav and they will be used instead.

NOISE_SR = 16000
NOISE_KINDS = ["street", "construction", "pressure_cooker", "crowd"]


def _pink(n: int, rng: np.random.Generator) -> np.ndarray:
    f = np.fft.rfftfreq(n)
    spec = (rng.normal(size=len(f)) + 1j * rng.normal(size=len(f))) / np.maximum(f, 1 / n) ** 0.5
    return np.fft.irfft(spec, n).astype(np.float32)


def _brown(n: int, rng: np.random.Generator) -> np.ndarray:
    y = np.cumsum(rng.normal(size=n)).astype(np.float32)
    y -= np.convolve(y, np.ones(800) / 800, mode="same")
    return y


def synth_noise(kind: str, seconds: float = 20.0, seed: int = 7) -> np.ndarray:
    custom = DATA_DIR / "noise" / f"{kind}.wav"
    if custom.exists():
        x, sr = read_wav(custom)
        return normalize(resample(x, sr, NOISE_SR), 0.5)

    rng = np.random.default_rng(seed)
    n = int(seconds * NOISE_SR)
    t = np.arange(n) / NOISE_SR
    if kind == "street":
        # engine rumble + tyre hiss + occasional two-tone horns
        y = 0.6 * normalize(_brown(n, rng)) + 0.25 * normalize(_pink(n, rng))
        for start in rng.uniform(0, seconds - 1.5, size=int(seconds / 4)):
            i0, i1 = int(start * NOISE_SR), int((start + rng.uniform(0.3, 0.9)) * NOISE_SR)
            tt = t[i0:i1]
            f = rng.choice([420, 480, 520])
            horn = np.sign(np.sin(2 * np.pi * f * tt)) * 0.5 + 0.5 * np.sin(2 * np.pi * f * 1.26 * tt)
            y[i0:i1] += 0.6 * horn * np.hanning(len(tt))
    elif kind == "construction":
        # broadband drill bursts + rhythmic hammer impacts
        y = 0.2 * normalize(_pink(n, rng))
        drill = np.sin(2 * np.pi * 95 * t) * (1 + 0.5 * np.sin(2 * np.pi * 6 * t))
        gate = (np.sin(2 * np.pi * 0.15 * t) > 0.1).astype(np.float32)
        y += 0.5 * drill * gate + 0.3 * gate * normalize(rng.normal(size=n).astype(np.float32))
        for k in np.arange(0.2, seconds, 0.55):
            i0 = int(k * NOISE_SR)
            L = min(int(0.08 * NOISE_SR), n - i0)
            y[i0:i0 + L] += 0.9 * rng.normal(size=L) * np.exp(-np.arange(L) / (0.012 * NOISE_SR))
    elif kind == "pressure_cooker":
        # kitchen hiss + the unmistakable whistle (harmonic, slightly wobbling)
        y = 0.25 * normalize(_pink(n, rng))
        for start in np.arange(1.0, seconds, 6.0):
            i0, i1 = int(start * NOISE_SR), min(n, int((start + 2.5) * NOISE_SR))
            tt = t[i0:i1] - t[i0]
            f0 = 2300 + 60 * np.sin(2 * np.pi * 3 * tt)
            ph = 2 * np.pi * np.cumsum(f0) / NOISE_SR
            env = np.minimum(1, tt / 0.3) * np.minimum(1, (tt[-1] - tt) / 0.3)
            y[i0:i1] += env * (0.7 * np.sin(ph) + 0.25 * np.sin(2 * ph)) + env * 0.2 * rng.normal(size=len(tt))
    elif kind == "crowd":
        # babble-like: many band-limited amplitude-modulated voices
        y = np.zeros(n, np.float32)
        sos = butter(4, [200, 3000], btype="band", fs=NOISE_SR, output="sos")
        for _ in range(8):
            v = sosfilt(sos, rng.normal(size=n)).astype(np.float32)
            env = np.abs(np.sin(2 * np.pi * rng.uniform(2, 5) * t + rng.uniform(0, 6)))
            y += v * env
    else:
        y = _pink(n, rng)
    return normalize(y.astype(np.float32), 0.5)


# ----------------------------------------------------------------------------- placeholders


def placeholder_voice(text: str, sr: int = PHONE_SR) -> bytes:
    """Mock-mode stand-in for TTS: a soft syllabic hum whose length tracks the text.
    Clearly not speech - it only exists so the UI flow works without an API key."""
    secs = min(6.0, 0.6 + 0.055 * len(text))
    t = np.arange(int(secs * sr)) / sr
    syll = 0.5 + 0.5 * np.sin(2 * np.pi * 4.0 * t)
    x = 0.25 * syll * (np.sin(2 * np.pi * 220 * t) + 0.5 * np.sin(2 * np.pi * 330 * t))
    fade = np.minimum(1, np.minimum(t / 0.05, (secs - t) / 0.05))
    return wav_bytes((x * fade).astype(np.float32), sr)
