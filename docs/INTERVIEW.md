# Interview prep

These answers are grounded in what was built and measured.

**Why not let an LLM decide?**
In health, an unpredictable decision is a liability. Every Khurak decision has a rule ID and the evidence words behind it. Evon is used only where it can't hurt: it can add a human review (rule R6c) and write case notes, but it can never lower a status or speak to a patient. That invariant is a unit test.

**How does Prisma do on phone audio?**
All evaluation audio was band-limited to 300–3400 Hz, resampled to 8 kHz and μ-law encoded. Character error rate was 5–13% across conditions, and latency was about 700 ms per answer (Prisma itself reports about 0.15 s of processing). Red-flag recall was 100% at clean, 15 dB, 10 dB and 5 dB SNR. Turning keyterms off cost 6 points of red-flag recall at 10 dB: "खोकल्यातून रक्त" became "थोक यातून रख".

**What did you learn about the models?**
1. Prisma sometimes drops a very short leading answer ("हो", "হ্যাঁ") on phone audio, so the classifier relies on the verb ("घेतली"), not on "yes" alone.
2. `codemix` output can switch script mid-phrase ("मैंने dawai band कर दी"), so I added script-agnostic phonetic keys.
3. Kannada negation is a fused suffix (ತೆಗೆದುಕೊಂಡಿಲ್ಲ). When the suffix is lost in noise, the meaning flips. That was the one unsafe miss, and it can't be fixed downstream of the transcript. Ideas: a confirmation question for short Kannada dose answers, keyterms that include the negative forms, or using n-best / confidence output from Prisma if it's exposed.
4. Timbre's 8 kHz output and audio tags made realistic test patients possible without any real recordings.
5. Programme keys allow one concurrent request, so every call is serialised behind a lock with backoff, and all prompts are pre-cached.

**What happens when the speech recogniser is wrong?**
It fails safe by design. Low confidence goes to AMBER, never GREEN. A negated danger word triggers a confirmation question. The evaluation lists every miss and its direction; over-escalation (green heard as red) is the acceptable failure.

**What is the path to production?**
Exotel or Twilio media streams plus the Prisma realtime WebSocket; Ni-kshay integration for patient lists; clinician-reviewed templates and native-speaker-reviewed lexicons; a consented one-PHC pilot under the DPDP Act. Then measure adherence against urine isoniazid tests, the same benchmark 99DOTS was measured on.

**What would you build next at Gnani?**
Real telephony with barge-in, a voice reply channel for the health worker ("I visited Ramesh"), adherence-risk prediction from call patterns, and a confirmation-question policy driven by per-language speech-recognition confusion data.
