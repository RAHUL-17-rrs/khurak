# Submission text

## Models used

- **Gnani Prisma v3.0** (STT, REST): every patient answer, on 8 kHz μ-law phone audio. Uses `keyterms` boosting (TB drugs, symptoms, yes/no words per language), `topic`, `previous_text`, `format=codemix`, and multi-candidate `language_code=hi-IN,en-IN` for Hinglish.
- **Gnani Timbre v3.0** (TTS, REST): the agent's voice in 4 languages at 8 kHz; all 13 voices used as synthetic patients and family members; audio tags (`<coughs>`, `<sigh>`, `<pauses>`); the health worker's 24 kHz morning voice briefing.
- **Gnani Evon v3.3** (optional, open weights behind an OpenAI-compatible server): an escalation-only second listener and health-worker case notes.

## Written explanation

**Khurak** is a voice agent for TB treatment adherence. Every day it calls each patient in their chosen language (Hindi, Marathi, Bengali, Kannada or Hinglish) using **Gnani Timbre v3.0**, and understands the spoken answer using **Gnani Prisma v3.0** on 8 kHz phone-quality audio with TB-specific keyterm boosting.

A deterministic policy engine decides the next action:
- reassure about expected side effects with approved templates
- ask one clarifying question, or confirm a negated danger word
- call a family contact after two unanswered calls, and flag a home visit after three days without a confirmed dose
- escalate danger signs (yellow eyes, blood in cough, repeated vomiting, blurred vision, breathlessness, rash) to the health worker with the patient's exact words

It never generates medical advice and never marks an unclear answer as safe. The health worker gets a prioritised dashboard, a decision trace for every call, and a spoken morning briefing.

We evaluated the full pipeline on 48 synthetic calls across 5 languages and 5 line conditions (485 Prisma transcriptions). **Red-flag recall was 100% at every noise level, down to 5 dB SNR**, and call-status accuracy was 95.8–100% per condition. Disabling Prisma keyterm boosting reduced red-flag recall to 93.8%. All misses are published, including the single case where a mis-heard Kannada negation produced a false green. All data is synthetic.
