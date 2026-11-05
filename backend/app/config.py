"""Central configuration. Everything is read from environment / .env."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BACKEND_DIR.parent
load_dotenv(ROOT_DIR / ".env")
load_dotenv(BACKEND_DIR / ".env")

GNANI_API_KEY: str = os.getenv("GNANI_API_KEY", "").strip()

# "live"  -> real Gnani Prisma + Timbre calls
# "mock"  -> no network; scripted transcripts + placeholder audio (clearly labelled)
MODE: str = os.getenv("KHURAK_MODE", "live" if GNANI_API_KEY else "mock").lower()
LIVE: bool = MODE == "live" and bool(GNANI_API_KEY)

STT_URL = os.getenv("GNANI_STT_URL", "https://api.vachana.ai/stt/v3")
TTS_URL = os.getenv("GNANI_TTS_URL", "https://api.vachana.ai/api/v1/tts/inference")
STT_MODEL = os.getenv("GNANI_STT_MODEL", "prisma-v3.0")
TTS_MODEL = os.getenv("GNANI_TTS_MODEL", "timbre-v3.0")
AGENT_VOICE = os.getenv("KHURAK_AGENT_VOICE", "Shivani")

DATA_DIR = BACKEND_DIR / "data"
STORE_DIR = Path(os.getenv("KHURAK_STORE", BACKEND_DIR / "store"))
PROMPT_DIR = STORE_DIR / "prompts"       # cached Timbre agent prompts
CLIP_DIR = STORE_DIR / "clips"           # synthetic patient answers (phone-degraded)
REC_DIR = STORE_DIR / "recordings"       # per-call turn audio
BRIEF_DIR = STORE_DIR / "briefings"
TTS_CACHE_DIR = STORE_DIR / "tts_cache"
EVAL_DIR = STORE_DIR / "eval"
DB_PATH = STORE_DIR / "khurak.db"
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"

for d in (STORE_DIR, PROMPT_DIR, CLIP_DIR, REC_DIR, BRIEF_DIR, TTS_CACHE_DIR, EVAL_DIR):
    d.mkdir(parents=True, exist_ok=True)

PHONE_SR = 8000
MAX_ANSWER_SECONDS = 15
RETRY_DELAY_HOURS = 2
MAX_RETRIES = 2
HOME_VISIT_DAYS = 3
DEMO_DAY = int(os.getenv("KHURAK_DEMO_DAY", "19"))
