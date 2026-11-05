"""Pre-generate (and cache) every agent prompt + every demo patient answer with Timbre v3.0.

After this runs once, live demos need zero TTS round-trips: calls start instantly and the
demo cannot break because of the network.   Usage:  python scripts/build_prompts.py
"""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml
from app import gnani, prompts, voices
from app.config import AGENT_VOICE, DATA_DIR

t0 = time.time()
static = prompts.all_static()
pats = yaml.safe_load((DATA_DIR / "patients.yaml").read_text(encoding="utf-8"))["patients"]
scen = yaml.safe_load((DATA_DIR / "scenarios.yaml").read_text(encoding="utf-8"))
jobs = [(lang, key, text) for lang, key, text in static]
for p in pats:
    lang = prompts.prompt_lang(p["language"])
    for key in prompts.PERSONALISED:
        jobs.append((lang, f"{key}:{p['id']}", prompts.render(key, p["language"], name=p["name_local"])))
print(f"{len(jobs)} agent prompts, voice={AGENT_VOICE}, mode={gnani.status()['mode']}")
for i, (lang, key, text) in enumerate(jobs, 1):
    wav, mock = gnani.synthesize(text, lang, AGENT_VOICE, phone=True)
    print(f"  [{i:3}/{len(jobs)}] {lang} {key:32} {'MOCK' if mock else 'ok'}")

print("demo patient answers")
for pid, sc in scen["demo"].items():
    p = next(x for x in pats if x["id"] == pid)
    noise = p.get("noise") or {}
    lines = list((sc.get("answers") or {}).values())
    if sc.get("family_answer"):
        voices.patient_clip(sc["family_answer"], p["language"], p["family"]["voice"], noise.get("kind"), noise.get("snr_db"))
    for text in lines:
        _, name, mock = voices.patient_clip(text, p["language"], p["voice"], noise.get("kind"), noise.get("snr_db"))
        print(f"  {pid} {name} {'MOCK' if mock else 'ok'}  {voices.strip_tags(text)[:50]}")
print(f"done in {time.time()-t0:.0f}s  api={gnani.stats}")
