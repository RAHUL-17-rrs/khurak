# Khurak (खुराक, "dose")

**A voice agent that calls every TB patient every day in their own language, understands the answer on a noisy phone line, and decides the next step: reassure, ask again, call family, or alert the health worker.**

Built on **Gnani Prisma v3.0** (speech-to-text) and **Gnani Timbre v3.0** (text-to-speech), with optional **Gnani Evon v3.3** as a safety second-listener, for the *Great Indian AI Internship Challenge*.

> All patients, names, phone numbers and voices in this repository are **synthetic**. This is a prototype, not a medical device; every spoken template needs clinician review before real use.

---

## Why

- India carries ~25% of the world's TB cases and ~32% of MDR-TB (WHO Global TB Report).
- Treatment is 6+ months of daily pills. Patients feel better and stop, or get scared by harmless side effects (orange urine from rifampicin) and stop, or don't report dangerous ones (yellow eyes, blood in cough) in time.
- India's digital adherence system, 99DOTS, is a **missed call**. Against urine tests it showed 70% sensitivity, 61% specificity and a 21% negative predictive value. A missed call cannot say *"I'm scared of the orange urine"* or *"my eyes are yellow."*

**Voice can.** Khurak closes that gap.

## What it does

| Situation | Khurak |
|---|---|
| Took the dose, no problems | 🟢 thanks, logs |
| Harmless expected side effect (orange urine, mild nausea) | 🟢 plays an **approved reassurance template** |
| "I feel fine, I stopped the pills" | 🟡 "complete the course" + flags the worker |
| Missed dose | 🟡 acknowledges + flags |
| Unclear answer | asks **one** follow-up, then 🟡 (**never green when unsure**) |
| **Hesitant "yes"** ("हम्म… शायद ले ली थी", "বোধহয় খেয়েছি", or a 2.5 s pause before answering) | asks **one probe**: "did you miss any dose in the last 3 days?" An unsure yes is never recorded as-is |
| Danger sign (yellow eyes/skin, blood in cough, repeated vomiting, breathlessness, blurred vision, rash) | 🔴 **escalates immediately** with the patient's exact words, advises hospital / 108 |
| Danger word **with negation** ("आँखें पीली **नहीं** हैं") | asks a **confirmation** question, never guesses |
| "Should I stop the medicine?" (a question) | not mistaken for "I stopped"; answered by the reassurance template, or 🟡 flagged if nothing explains the worry |
| "सुनाई नहीं दिया" / "ಕೇಳಿಸಲಿಲ್ಲ" (*I couldn't hear you*) | **replays the question** (max 2 per call). Before this fix, "सुनाई **नहीं** दिया" was read as "नहीं" = missed dose |
| "मैं ठीक नहीं हूँ" / "শরীর ভালো নেই" (*I'm not well*) | 🟡 flagged as `unwell` with the patient's words, not as a vague low-confidence answer |
| No answer | retries (max 2), then **calls the family contact** |
| 3 days without a confirmed dose | 🟡 **home visit needed** |
| Every morning | a **spoken briefing** for the health worker in Hindi |

**Languages:** Hindi, Marathi, Bengali, Kannada, and code-mixed Hinglish. The patient chooses; the agent never guesses the language (Hindi and Marathi share a script).

## Results (measured, not claimed)

`backend/scripts/evaluate.py` runs **52 scripted synthetic calls** through the full production path:
Timbre v3.0 voice (all 13 Timbre v3.0 speakers, with audio tags like `<coughs>`) → background noise at a target SNR → **300–3400 Hz band-pass → 8 kHz → G.711 μ-law** (a real phone line) → **Prisma v3.0** → classifier → policy. **550 real Prisma transcriptions.**

| Line condition | Status accuracy | **Red-flag recall** | False GREEN | Prisma CER | STT latency |
|---|---|---|---|---|---|
| Clean phone line | 100% | **100%** | 0 | 7.6% | 671 ms |
| Street traffic, 15 dB SNR | 100% | **100%** | 0 | 4.6% | 748 ms |
| Crowd babble, 10 dB SNR | 98.1% | **100%** | 0 | 11.5% | 708 ms |
| Construction, **5 dB SNR** | 98.1% | **100%** | 1 | 6.3% | 775 ms |
| Crowd 10 dB, **keyterm boost OFF** | 96.2% | 93.8% | 0 | 14.0% | 750 ms |

- **No danger sign was ever marked green**, at any noise level.
- **Prisma v3.0 keyterm boosting matters:** with keyterms off, a Marathi "खोकल्यातून रक्त" (blood in cough) became "थोक यातून रख" and red-flag recall fell from 100% to 93.8%.
- **Keyterms fixed a real unsafe miss.** The first evaluation run had one false green: in crowd noise, Prisma heard Kannada "ತೆಗೆದುಕೊಂಡಿಲ್ಲ" (*didn't take*) as "ತೆಗೆದುಕೊಂಡೆ" (*took*). Adding the negative dose forms of every language to Prisma's keyterms fixed it; Kannada is now 100% with zero false greens.
- **The one remaining false green** is published: at 5 dB construction noise Prisma dropped the Marathi hesitation word "बहुतेक" (*probably*) from "बहुतेक घेतली", so the hesitation probe never fired. In live calls a long pause before answering is a second hesitation signal; the evaluation does not measure that, so this stays counted as a miss.
- Every miss is listed in the in-app Evaluation page. Honest caveat: the scenarios were also used while developing the lexicon, so they are a development set, not a held-out test.

## How it decides (design)

```
Timbre v3.0 template ──► patient on an 8 kHz line ──► Prisma v3.0 (keyterms + topic + previous turn)
                                                              │
                         classifier: lexicon + fuzzy + script-agnostic phonetic keys + negation + question-awareness
                                                              │
                         policy table (deterministic, first match wins) ──► tools: escalate / flag / reassure /
                                                              │                    retry / call family / log / brief
                         Evon v3.3 second listener (optional) ┘  can only ADD concern, never lower a status
```

**Safety invariants (unit-tested in `backend/tests/`):**
1. Any un-negated red flag → RED. Nothing downstream can downgrade it.
2. Never GREEN unless the dose was understood as taken with confidence.
3. A negated danger word is confirmed with one yes/no question, never silently dropped.
4. Questions ("दवा बंद कर दूँ क्या?") are not statements.
5. Patients only hear fixed templates. No generated text ever reaches a patient.
6. The LLM (Evon) can only escalate to human review; it can never lower a status.
7. "Should I stop the medicine?" is always answered: by a reassurance template, or by flagging the health worker (R3a).
8. A hesitant "yes" is never recorded as GREEN without one probe question. Self-reported adherence overstates the truth, which is exactly where 99DOTS loses accuracy.

**Engineering details worth a look:**
- **Script-agnostic phonetic matching** (`app/translit.py`). Prisma's `codemix` output can switch script *mid-phrase* ("मैंने **dawai band** कर दी"). Devanagari and Latin are keyed phonetically (schwa deletion, nasal and vowel folding), so "बंद कर दी", "band kar di" and "band कर दी" all match.
- **Longest-phrase-wins span masking**, so "नहीं ली" (missed) is never also read as "ली" (taken).
- **Fuzzy limits for short words**, so "hoon" (*am*) never becomes "khoon" (*blood*). This was a real bug the tests caught.
- **Gnani keys allow one in-flight request.** All API calls go through a process-wide lock with backoff on 429. Latency is measured inside the lock, so it reflects the network round-trip, not queueing.
- **Every Timbre prompt is pre-generated and cached** (`scripts/build_prompts.py`), so calls start instantly and the demo can't break on the network.
- **Every decision has a trace**: transcript, evidence words, confidence, the rule ID that fired, the actions, and latency. Open "Why?" on any card.

## Hosted demo (Vercel)

The full app needs a long-running server (SQLite, background rounds, live events). Vercel is serverless, so the hosted build splits the work honestly:

- **Control room, worker dashboard, timelines and briefing** replay a round **recorded live against Gnani** by `backend/scripts/export_static.py`: real Timbre audio, real Prisma transcripts and real decisions, replayed at their real timing.
- **The Patient phone is fully live.** `api/index.py` is a stateless serverless function. Each answer (scripted clip, your mic with optional noise, or typed) goes to Prisma v3.0 and through the same classifier and policy code. The call state travels with the browser, **HMAC-signed** so it can't be edited. Agent prompts are pre-rendered Timbre audio, so the function never needs TTS.
- **Credit protection:** audio answers are capped per IP and per instance per hour and cut at 15 s, and `KHURAK_LIVE=0` switches Prisma off (typed answers keep working).

```bash
cd backend && python scripts/export_static.py   # record a live round + snapshot (needs the key)
cd .. && vercel deploy --prod --env GNANI_API_KEY=...   # vercel.json does the rest
```

## Related work, and what Khurak learned from it

Before the final push I read the closest public projects:

| Project | What it does | What Khurak took from it, or does differently |
|---|---|---|
| [99DOTS](https://www.99dots.org/) | India's missed-call TB adherence system | The baseline: a missed call carries no information. Khurak listens to the answer |
| [Tell](https://github.com/qiqiiiii77/tell) (AssemblyAI) | English medication-adherence agent that won't record a "yes" the patient didn't sound sure of | **Adopted the idea** as rule R5b: hesitation words in 5 languages plus a long pause before answering trigger a probe question |
| [DischargeSaathi](https://github.com/Praharshithakarnam/DischargeSaathi) (Gnani) | Post-discharge follow-up with a concern queue | Similar human-review queue; Khurak adds TB-specific red flags, negation confirmation, family escalation and a noise-tested evaluation |
| [CallLens](https://github.com/dragyo7/calllens-stress-lab) (Gnani) | Prisma benchmark under G.711 telephony degradation | Same phone-line simulation idea. Khurak measures the **end decision** (red-flag recall, false green), not only character error rate, and runs a keyterm ablation |
| [Naadi](https://github.com/yashasprabhu29/Naadi-Emergency-CPR-Copilot) (Gnani) | Deterministic emergency detection for call-takers | Same "no LLM decides" principle; credit caps like theirs protect the public demo |

## Gnani models used

| Model | How Khurak uses it |
|---|---|
| **Prisma v3.0** (REST `/stt/v3`) | Every patient answer, at 8 kHz μ-law. `keyterms` (TB drugs, symptoms, yes/no words per language), `topic`, `previous_text` (earlier turns), `format=codemix`, multi-candidate `language_code=hi-IN,en-IN` for Hinglish |
| **Timbre v3.0** (REST `/api/v1/tts/inference`) | The agent's voice (Shivani) in 4 languages at 8 kHz phone quality; all 13 voices used as distinct synthetic patients and family members; audio tags (`<coughs>`, `<sigh>`, `<pauses>`); the 24 kHz morning briefing voice note |
| **Evon v3.3** (open weights, optional) | Second listener on each transcript (escalation-only) and health-worker case notes. Runs on any OpenAI-compatible server; see `deploy/evon_kaggle.py` for a free Kaggle 2×T4 recipe |

## Run it

Requirements: Python 3.11+, Node 20+. No ffmpeg needed (the browser records WAV directly).

```bash
cp .env.example .env            # paste your key from app.gnani.ai/voice into GNANI_API_KEY
```

**Windows (PowerShell):** `./run.ps1`  **macOS/Linux:** `./run.sh`

That creates the venv, installs everything, builds the UI and serves it all at **http://127.0.0.1:8765**.

Without a key, Khurak runs in clearly labelled **mock mode**: placeholder audio, and the scripted text stands in for STT.

Useful scripts (from `backend/`):

```bash
python scripts/smoke_test.py       # Timbre -> phone line -> Prisma round trip in 4 languages
python scripts/build_prompts.py    # pre-generate and cache every prompt + demo answer
python scripts/evaluate.py         # the full noise sweep -> store/eval/eval_report.md
python -m pytest -q tests          # 79 safety and scenario tests
```

Dev mode with hot reload: `uvicorn app.main:app --reload --port 8765` in `backend/`, plus `npm run dev` in `frontend/` (proxies to the API).

**Deploy:** `docker build -t khurak . && docker run -p 8765:8765 -e GNANI_API_KEY=... khurak` (works on Render, Railway, Fly).

## The app

| Page | What you see |
|---|---|
| **Control room** | "Run today's calls": 8 patients called live (3 at a time), cards animate Dialing → Speaking → Listening → Deciding → 🔴🟡🟢. 🎧 *Listen in* on any call. Live decision log. |
| **Patient phone** | A phone rings. Answer with the **scripted synthetic voice**, **your own voice** (with street / construction / pressure-cooker noise mixed at a chosen SNR), or by typing. See what Prisma heard and why the agent acted. |
| **Health worker** | Prioritised work list with the patient's exact words, ▶ hear the patient, "Why?" trace, mark visited, and **▶ morning voice briefing** in Hindi. |
| **Patient timeline** | 30-day adherence calendar, every call with audio, Evon case note. |
| **Evaluation** | The measured numbers above, the keyterm ablation, and every miss. |
| **How it decides** | The policy table, the invariants, and every template in every language with English glosses. |

## Repository

```
backend/app/        config · gnani (Prisma/Timbre REST) · audio (phone line, noise) · prompts (all speech)
                    classifier · translit (phonetic keys) · policy (rules) · dialogue (state machine)
                    orchestrator (live calls + tools) · scheduler (round, retries, family, X3) · briefing · evon · main (API + SSE)
backend/data/       patients.yaml · scenarios.yaml (demo + 40 eval calls) · lexicon/{hi,mr,bn,kn,en}.yaml
backend/scripts/    smoke_test · build_prompts · evaluate
backend/tests/      safety invariants + every scenario
frontend/src/       React + Vite + Tailwind: control room, phone, worker, timeline, evaluation, how-it-works
deploy/             evon_kaggle.py (free GPU hosting for Evon)
docs/               demo script · posts · submission text · interview prep
```

## Limitations and the path to production

- Telephony is simulated in the browser, but the audio path is real phone quality. Next step: Exotel or Twilio media streams plus Prisma's realtime WebSocket.
- Synthetic voices are cleaner than real patients. Next step: consented scripted human recordings in the evaluation.
- Lexicons for Bengali and Kannada need native-speaker review. Templates need clinician review.
- Production would integrate Ni-kshay patient lists and run a consented PHC pilot under India's DPDP Act.

## Sources

- Gnani: [Prisma v3.0](https://docs.gnani.ai/api/STT/models/prisma-v3.md) · [Timbre TTS](https://docs.gnani.ai/api/TTS/tts-inference) · [Evon v3.3](https://huggingface.co/gnani/gnani-evon-v3.3-30B-A3B)
- [India: 25% of TB cases, 32% of MDR-TB (WHO Global TB Report coverage)](https://www.theweek.in/news/health/2025/11/19/india-tops-global-tb-list-again-what-gaps-keep-pushing-us-into-this-crisis.html)
- [Accuracy of 99DOTS vs urine isoniazid testing (medRxiv)](https://www.medrxiv.org/content/10.1101/19011197.full.pdf)
