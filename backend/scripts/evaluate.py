"""End-to-end evaluation: Timbre voice -> noise -> 8 kHz phone line -> Prisma -> classifier -> policy.

    python scripts/evaluate.py                 # full sweep (cached; re-runs are cheap)
    python scripts/evaluate.py --limit 5       # quick check
    python scripts/evaluate.py --text-only     # no API: ground-truth transcripts only

Writes store/eval/report.json, store/eval/eval_report.md and store/eval/calls.csv.
Only numbers that were actually measured are reported.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml
from rapidfuzz.distance import Levenshtein

from app import gnani, voices
from app.classifier import normalise
from app.translit import key_phrase
from app.config import DATA_DIR, EVAL_DIR
from app.dialogue import simulate

CACHE_F = EVAL_DIR / "stt_cache.json"


def strip_tags(t: str) -> str:
    return re.sub(r"\s*<[^>]+>\s*", " ", t).strip()


def plain(t: str) -> str:
    # script-agnostic: Prisma writing a Hinglish word in Devanagari is not counted as an error
    return key_phrase(re.sub(r"[^\w\s]", " ", normalise(t))).replace(" ", "")


def cer(ref: str, hyp: str) -> float:
    r, h = plain(ref), plain(hyp)
    return Levenshtein.distance(r, h) / max(1, len(r))


def load_items() -> list[dict]:
    scen = yaml.safe_load((DATA_DIR / "scenarios.yaml").read_text(encoding="utf-8"))
    pats = {p["id"]: p for p in yaml.safe_load((DATA_DIR / "patients.yaml").read_text(encoding="utf-8"))["patients"]}
    items = []
    for pid, sc in scen["demo"].items():
        p = pats[pid]
        if sc.get("answers"):
            items.append({"id": f"demo_{pid}", "lang": p["language"], "voice": p["voice"], "kind": "patient",
                          "answers": sc["answers"], "expected": sc["expected"]})
        else:
            items.append({"id": f"demo_{pid}", "lang": p["language"], "voice": p["family"]["voice"], "kind": "family",
                          "answers": {"family_check": sc["family_answer"]}, "expected": sc["expected"]})
    for e in scen["eval"]:
        items.append({**e, "kind": "patient"})
    return items, scen["noise_conditions"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--text-only", action="store_true")
    ap.add_argument("--no-ablation", action="store_true")
    args = ap.parse_args()

    items, conditions = load_items()
    if args.limit:
        items = items[: args.limit]
    live = gnani.status()["mode"] == "live" and not args.text_only
    cache = json.loads(CACHE_F.read_text(encoding="utf-8")) if CACHE_F.exists() else {}

    runs = [("text", None, True)]
    if live:
        runs += [(c["name"], c, True) for c in conditions]
        if not args.no_ablation:
            runs += [("crowd_10db_noboost", next(c for c in conditions if c["name"] == "crowd_10db"), False)]

    rows, utts = [], []
    t0 = time.time()
    for ri, (cond_name, cond, boost) in enumerate(runs):
        print(f"\n== condition {cond_name} ({ri + 1}/{len(runs)})")
        for it in items:
            heard = {}
            for stage, text in it["answers"].items():
                ref = strip_tags(text)
                if cond is None:
                    heard[stage] = ref
                    continue
                wav, clip, _ = voices.patient_clip(text, it["lang"], it["voice"], cond["kind"], cond["snr_db"])
                key = f"{clip}|{boost}|{gnani.keyterms_signature(it['lang']) if boost else 'none'}"
                if key not in cache:
                    r = gnani.transcribe(wav, it["lang"], boost=boost)
                    cache[key] = {"t": r.transcript, "ms": r.latency_ms}
                    CACHE_F.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
                hyp = cache[key]["t"]
                heard[stage] = hyp
                utts.append({"cond": cond_name, "lang": it["lang"], "id": it["id"], "stage": stage, "ref": ref,
                             "hyp": hyp, "cer": round(cer(ref, hyp), 4), "ms": cache[key]["ms"]})
            decision, trace = simulate(it["lang"], heard, kind=it["kind"])
            exp = it["expected"]
            row = {"cond": cond_name, "id": it["id"], "lang": it["lang"], "expected": exp["status"],
                   "expected_rule": exp["rule"], "got": decision.status, "rule": decision.rule,
                   "ok": decision.status == exp["status"], "rule_ok": decision.rule == exp["rule"],
                   "reasons": "+".join(decision.reasons),
                   "heard": " / ".join(f"{k}: {v}" for k, v in heard.items())}
            rows.append(row)
            flag = "ok " if row["ok"] else "XX "
            print(f"  {flag}{it['id']:9} {it['lang']} exp={exp['status']:5} got={decision.status:5} {decision.rule:4} "
                  f"| {row['heard'][:90]}")

    report = summarise(rows, utts, live, time.time() - t0)
    (EVAL_DIR / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(EVAL_DIR / "calls.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    (EVAL_DIR / "eval_report.md").write_text(markdown(report), encoding="utf-8")
    print("\n" + markdown(report))


def _metrics(rs: list[dict]) -> dict:
    n = len(rs)
    red = [r for r in rs if r["expected"] == "RED"]
    nongreen = [r for r in rs if r["expected"] != "GREEN"]
    return {
        "n": n,
        "status_acc": round(sum(r["ok"] for r in rs) / max(1, n), 4),
        "rule_acc": round(sum(r["rule_ok"] for r in rs) / max(1, n), 4),
        "red_recall": round(sum(r["got"] == "RED" for r in red) / max(1, len(red)), 4) if red else None,
        "red_n": len(red),
        "false_green": sum(r["got"] == "GREEN" for r in nongreen),
        "false_green_rate": round(sum(r["got"] == "GREEN" for r in nongreen) / max(1, len(nongreen)), 4),
        "red_to_green": sum(r["got"] == "GREEN" for r in red),
        "over_escalation": sum(r["expected"] == "GREEN" and r["got"] != "GREEN" for r in rs),
    }


def summarise(rows, utts, live, secs) -> dict:
    by_cond = defaultdict(list)
    for r in rows:
        by_cond[r["cond"]].append(r)
    by_lang = defaultdict(list)
    for r in rows:
        if r["cond"] not in ("text", "crowd_10db_noboost"):
            by_lang[r["lang"]].append(r)
    u_cond = defaultdict(list)
    for u in utts:
        u_cond[u["cond"]].append(u)
    audio_rows = [r for r in rows if r["cond"] not in ("text", "crowd_10db_noboost")]
    failures = [r for r in rows if not r["ok"]]
    return {
        "generated_at": time.strftime("%Y-%m-%d %H:%M"),
        "mode": "live" if live else "text-only",
        "models": {"stt": gnani.STT_MODEL, "tts": gnani.TTS_MODEL},
        "pipeline": "Timbre v3.0 synthetic voice -> noise @SNR -> 300-3400 Hz band-pass -> 8 kHz G.711 mu-law "
                    "-> Prisma v3.0 (keyterms + topic) -> lexicon/phonetic classifier -> deterministic policy",
        "n_scenarios": len({r["id"] for r in rows}),
        "n_calls": len(rows),
        "n_utterances": len(utts),
        "overall_audio": _metrics(audio_rows) if audio_rows else None,
        "by_condition": {k: {**_metrics(v),
                             "cer": round(sum(u["cer"] for u in u_cond[k]) / len(u_cond[k]), 4) if u_cond[k] else None,
                             "stt_ms_avg": int(sum(u["ms"] for u in u_cond[k]) / len(u_cond[k])) if u_cond[k] else None}
                         for k, v in by_cond.items()},
        "by_language": {k: _metrics(v) for k, v in by_lang.items()},
        "failures": failures,
        "seconds": int(secs),
    }


def pct(x):
    return "-" if x is None else f"{100 * x:.1f}%"


def markdown(r: dict) -> str:
    out = [f"# Khurak evaluation ({r['mode']}, {r['generated_at']})", "",
           f"Pipeline: {r['pipeline']}", "",
           f"{r['n_scenarios']} scripted synthetic calls x conditions = {r['n_calls']} call simulations, "
           f"{r['n_utterances']} Prisma transcriptions.", "",
           "| Condition | Calls | Status acc | Rule acc | Red-flag recall | False GREEN | Red->Green | CER | STT ms |",
           "|---|---|---|---|---|---|---|---|---|"]
    for k, m in r["by_condition"].items():
        out.append(f"| {k} | {m['n']} | {pct(m['status_acc'])} | {pct(m['rule_acc'])} | {pct(m['red_recall'])} "
                   f"| {m['false_green']} | {m['red_to_green']} | {pct(m['cer']) if m['cer'] is not None else '-'} "
                   f"| {m['stt_ms_avg'] or '-'} |")
    if r["by_language"]:
        out += ["", "| Language (all audio conditions) | Calls | Status acc | Red-flag recall | False GREEN |",
                "|---|---|---|---|---|"]
        for k, m in r["by_language"].items():
            out.append(f"| {k} | {m['n']} | {pct(m['status_acc'])} | {pct(m['red_recall'])} | {m['false_green']} |")
    out += ["", "CER = character error rate of Prisma vs the scripted line, on a script-agnostic phonetic key "
            "(punctuation/spaces ignored; Devanagari vs Latin spelling of the same word is not an error).",
            "False GREEN = call marked safe when ground truth was AMBER/RED (the unsafe error).", ""]
    if r["failures"]:
        out += ["## Every miss", "", "| Condition | Call | Expected | Got | What Prisma heard |", "|---|---|---|---|---|"]
        for f in r["failures"]:
            out.append(f"| {f['cond']} | {f['id']} | {f['expected']} {f['expected_rule']} | {f['got']} {f['rule']} "
                       f"| {f['heard'][:140]} |")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    main()
