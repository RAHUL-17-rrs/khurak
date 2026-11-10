"""Record a real round against Gnani and export a static snapshot for the hosted (Vercel) demo.

    python scripts/export_static.py            # needs GNANI_API_KEY; ~1-2 minutes

1. Seeds the synthetic world and runs today's round LIVE (Prisma + Timbre), recording every
   agent event with its timestamp -> the control room replays exactly what happened.
2. Snapshots every dashboard view (patients, timelines, calls + traces, alerts, briefing,
   evaluation, policy) as JSON.
3. Copies all audio (agent prompts, patient answers on the phone line, briefing) next to it,
   plus per-key prompt audio + scripted patient clips that the serverless live phone uses.

Output: frontend/public/demo/*.json and frontend/public/audio/** (served statically).
"""
from __future__ import annotations

import asyncio
import collections
import json
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import briefing, db, events, gnani, main, prompts, scheduler, voices  # noqa: E402
from app.config import AGENT_VOICE, BRIEF_DIR, CLIP_DIR, EVAL_DIR, REC_DIR, ROOT_DIR  # noqa: E402

PUB = ROOT_DIR / "frontend" / "public"
DEMO, AUD = PUB / "demo", PUB / "audio"


def dump(name: str, obj) -> None:
    f = DEMO / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(obj, ensure_ascii=False, default=str), encoding="utf-8")


def copy_audio(url: str | None) -> None:
    """/audio/rec/x.wav -> public/audio/rec/x.wav"""
    if not url or not url.startswith("/audio/"):
        return
    sub, name = url.split("/")[2], url.split("/")[-1]
    src = {"rec": REC_DIR, "clips": CLIP_DIR, "briefings": BRIEF_DIR}.get(sub)
    if src and (src / name).exists():
        (AUD / sub).mkdir(parents=True, exist_ok=True)
        shutil.copy2(src / name, AUD / sub / name)


def main_() -> None:
    if gnani.status()["mode"] != "live":
        sys.exit("Needs GNANI_API_KEY: the hosted demo replays a LIVE round.")
    for d in (DEMO, AUD):
        if d.exists():
            shutil.rmtree(d)
    DEMO.mkdir(parents=True)

    # ---- 1. live round with recorded events
    scheduler.seed(reset=True)
    day = scheduler.current_day()
    dump("patients_before.json", main.patients())
    events.recent = collections.deque(maxlen=10000)
    t0 = time.time()
    asyncio.run(scheduler.run_day(day, pace=1.0))
    evs = [e for e in events.recent if e["type"] not in ("reset",)]
    errors = [e for e in evs if e["type"] == "call_error"]
    if errors:
        sys.exit(f"round had errors, not exporting: {errors}")
    base = evs[0]["ts"]
    for e in evs:
        e["t"] = round(e["ts"] - base, 3)
    dump("round.json", {"day": day, "recorded_at": time.strftime("%Y-%m-%d %H:%M IST"),
                        "seconds": round(time.time() - t0, 1), "events": evs})
    print(f"round recorded: {len(evs)} events in {time.time() - t0:.0f}s")

    # ---- 2. snapshot every view
    st = main.status()
    st["recorded_at"] = time.strftime("%Y-%m-%d %H:%M IST")
    dump("status.json", st)
    pats = main.patients()
    dump("patients.json", pats)
    for p in pats:
        dump(f"patients/{p['id']}.json", main.patient(p["id"]))
    calls = main.list_calls(day)
    dump("calls.json", calls)
    for c in calls:
        full = main.get_call(c["id"])
        dump(f"calls/{c['id']}.json", full)
        for t in full.get("turns") or []:
            copy_audio(t.get("answer_audio"))
        for f in REC_DIR.glob(f"{c['id']}_*.wav"):
            copy_audio(f"/audio/rec/{f.name}")
    dump("alerts.json", main.alerts(resolved=0))
    b = briefing.build(day)
    copy_audio(b["audio"])
    dump("briefing.json", b)
    dump("policy.json", main.policy())
    if (EVAL_DIR / "report.json").exists():
        shutil.copy2(EVAL_DIR / "report.json", DEMO / "eval.json")

    # ---- 3. per-key prompt audio + scripted clips for the serverless live phone
    n = 0
    for lang, key, text in prompts.all_static():
        wav, _ = gnani.synthesize(text, lang, AGENT_VOICE, phone=True)
        out = AUD / "prompts" / lang / f"{key.replace(':', '__')}.wav"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(wav)
        n += 1
    for p in pats:
        pl = prompts.prompt_lang(p["language"])
        for key in prompts.PERSONALISED:
            wav, _ = gnani.synthesize(prompts.render(key, p["language"], name=p["name_local"]), pl, AGENT_VOICE, phone=True)
            (AUD / "prompts" / pl / f"{key}__{p['id']}.wav").write_bytes(wav)
            n += 1
    script = {}
    for p in pats:
        plan = scheduler.scripted_plan(p, day)
        lines = dict(plan.get("answers") or {})
        fam = scheduler.scripted_answer(p, day, "family_check", "family")
        entries = [(stg, txt, p["voice"]) for stg, txt in lines.items()] + [("family_check", fam, p["family"]["voice"])]
        script[p["id"]] = {}
        noise = p.get("noise") or {}
        for stg, txt, voice in entries:
            if not txt:
                continue
            wav, _, _ = voices.patient_clip(txt, p["language"], voice, noise.get("kind"), noise.get("snr_db"))
            out = AUD / "script" / p["id"] / f"{stg}.wav"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(wav)
            script[p["id"]][stg] = {"text": voices.strip_tags(txt), "audio": f"/audio/script/{p['id']}/{stg}.wav"}
    dump("script.json", script)
    size = sum(f.stat().st_size for f in PUB.rglob("*") if f.is_file()) / 1e6
    print(f"exported {n} prompt clips, scripts for {len(script)} patients, {size:.1f} MB under frontend/public")


if __name__ == "__main__":
    main_()
