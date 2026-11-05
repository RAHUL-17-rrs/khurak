"""Day-1 de-risk: Timbre v3.0 speaks a line -> phone-degrade -> Prisma v3.0 transcribes it back."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import gnani, audio
from app.config import STORE_DIR

CASES = [
    ("hi-IN", "Prakash", "हाँ, मैंने आज दवा ले ली, लेकिन पेशाब लाल आ रहा है"),
    ("mr-IN", "Shivani", "हो, घेतली. पण दोन दिवसांपासून डोळे पिवळे दिसतायत"),
    ("bn-IN", "Riyaa", "হ্যাঁ, আজকের ওষুধ খেয়েছি, কিন্তু চোখ হলুদ হয়ে গেছে"),
    ("kn-IN", "Lakshmi", "ಹೌದು, ಮಾತ್ರೆ ತೆಗೆದುಕೊಂಡೆ, ಏನೂ ತೊಂದರೆ ಇಲ್ಲ"),
]
print("status:", gnani.status())
for lang, voice, text in CASES:
    t0 = time.time()
    wav, mock = gnani.synthesize(text, lang, voice, phone=False)
    x, sr = audio.read_wav_bytes(wav)
    print(f"\n[{lang}] TTS {voice}: {len(x)/sr:.1f}s @ {sr} Hz mock={mock} ({time.time()-t0:.1f}s)")
    phone = audio.to_phone_wav(wav)
    (STORE_DIR / f"smoke_{lang}.wav").write_bytes(phone)
    r = gnani.transcribe(phone, lang, hint_text=text)
    print(f"  said : {text}\n  heard: {r.transcript}\n  stt  : {r.latency_ms} ms lang={r.detected_language} raw={r.raw}")
