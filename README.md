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
| Danger sign (yellow eyes/skin, blood in cough, repeated vomiting, breathlessness, blurred vision, rash) | 🔴 **escalates immediately** with the patient's exact words, advises hospital / 108 |
| Danger word **with negation** ("आँखें पीली **नहीं** हैं") | asks a **confirmation** question, never guesses |
| "Should I stop the medicine?" (a question) | not mistaken for "I stopped" |
| No answer | retries (max 2), then **calls the family contact** |
| 3 days without a confirmed dose | 🟡 **home visit needed** |
| Every morning | a **spoken briefing** for the health worker in Hindi |

**Languages:** Hindi, Marathi, Bengali, Kannada, and code-mixed Hinglish. The patient chooses; the agent never guesses the language (Hindi and Marathi share a script).

## Results (measured, not claimed)

`backend/scripts/evaluate.py` runs **48 scripted synthetic calls** through the full production path:
Timbre v3.0 voice (all 13 Timbre v3.0 speakers, with audio tags like `<coughs>`) → background noise at a target SNR → **300–3400 Hz band-pass → 8 kHz → G.711 μ-law** (a real phone line) → **Prisma v3.0** → classifier → policy. **485 real Prisma transcriptions.**

| Line condition | Status accuracy | **Red-flag recall** | Danger sign marked GREEN | Prisma CER | STT latency |
|---|---|---|---|---|---|
| Clean phone line | 100% | **100%** | 0 | 7.8% | 695 ms |
| Street traffic, 15 dB SNR | 100% | **100%** | 0 | 5.4% | 704 ms |
| Crowd babble, 10 dB SNR | 95.8% | **100%** | 0 | 12.6% | 709 ms |
| Construction, **5 dB SNR** | 100% | **100%** | 0 | 8.6% | 699 ms |
| Crowd 10 dB, **keyterm boost OFF** | 95.8% | 93.8% | 0 | 14.4% | 691 ms |

- **Prisma v3.0 keyterm boosting matters:** with TB drug and symptom keyterms off, a Marathi "खोकल्यातून रक्त" (blood in cough) became gibberish and red-flag recall fell from 100% to 93.8%. With boosting on, every danger sign was caught at every noise level.
- **Every miss is listed** in the in-app Evaluation page. Across all noisy conditions there was **one unsafe miss**: at 10 dB crowd noise, Prisma heard Kannada "ತೆಗೆದುಕೊಂಡಿಲ್ಲ" (*didn't take*) as "ತೆಗೆದುಕೊಂಡೆ" (*took*). The fused negative suffix was lost, so the call was marked green instead of amber. No danger sign was ever marked green.
- Honest caveat: these scenarios were also used while developing the lexicon. They are a development set, not a held-out test.

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

**Engineering details worth a look:**
- **Script-agnostic phonetic matching** (`app/translit.py`). Prisma's `codemix` output can switch script *mid-phrase* ("मैंने **dawai band** कर दी"). Devanagari and Latin are keyed phonetically (schwa deletion, nasal and vowel folding), so "बंद कर दी", "band kar di" and "band कर दी" all match.
- **Longest-phrase-wins span masking**, so "नहीं ली" (missed) is never also read as "ली" (taken).
- **Fuzzy limits for short words**, so "hoon" (*am*) never becomes "khoon" (*blood*). This was a real bug the tests caught.
- **Gnani keys allow one in-flight request.** All API calls go through a process-wide lock with backoff on 429. Latency is measured inside the lock, so it reflects the network round-trip, not queueing.
- **Every Timbre prompt is pre-generated and cached** (`scripts/build_prompts.py`), so calls start instantly and the demo can't break on the network.
- **Every decision has a trace**: transcript, evidence words, confidence, the rule ID that fired, the actions, and latency. Open "Why?" on any card.

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
python -m pytest -q tests          # 68 safety and scenario tests
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
