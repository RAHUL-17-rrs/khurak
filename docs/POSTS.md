# Posts

Upload the main video natively (the file, not a YouTube link). Tag **Gnani AI**. Post between 9 and 11 AM IST.
Reply to every comment in the first 2 hours. No engagement pods or bought likes (grounds for disqualification).

## Teaser (post first)

Building something for the #GreatIndianAIInternshipChallenge: a voice agent that calls TB patients every day in their own language, and knows when to wake up a health worker.

First working call 👇 Marathi, 8 kHz phone line, Gnani Prisma v3.0 + Timbre v3.0.

#GnaniAI #BuildInPublic

## Main post (LinkedIn)

**Day 19 of TB treatment. Ramesh's eyes turned yellow.**
The system tracking his medicine recorded one thing: *a missed call.*

India has ~25% of the world's TB cases. Patients feel better after a few weeks and stop their pills. Some stop because rifampicin turns their urine orange and nobody told them that's normal. Missed doses breed drug-resistant TB. And a missed call can't tell "I forgot to call" from "I stopped", or "my urine is orange" from "my eyes are yellow."

So I built **Khurak** (खुराक, "dose"), a voice agent that calls every TB patient daily in their own language, for the **#GreatIndianAIInternshipChallenge** by **Gnani AI**.

🎙️ **Gnani Timbre v3.0** speaks Hindi, Marathi, Bengali and Kannada on a phone-quality line
👂 **Gnani Prisma v3.0** understands the answer at 8 kHz, boosted with TB drug and symptom keyterms
🤖 A deterministic agent decides: reassure, ask again, call family, or escalate to the health worker
🗣️ The health worker gets her daily list as a voice briefing

What I'm proudest of:
• **Rules decide, not a language model.** Every spoken reply is a fixed, reviewable template.
• **Never green when unsure.** Unclear answers always reach a human.
• **"पीली नहीं हैं" ≠ "पीली हैं".** Negated danger words get a confirmation question.
• **Measured on a noisy phone line:** 52 synthetic calls × 5 conditions, 550 Prisma transcriptions. Red-flag recall was **100%** at every noise level, down to 5 dB SNR. Turning keyterm boosting off dropped it to 93.8%.
• Prisma's code-mixed output switches script mid-phrase ("मैंने dawai band कर दी"), so I built script-agnostic phonetic matching for it.

All patients, names, numbers and voices are synthetic.
🔗 GitHub: <link>

#GreatIndianAIInternshipChallenge #GnaniAI #VoiceAI #IndicAI #HealthTech #BuildInPublic

## X post (separate nomination)

Day 19 of TB treatment. Ramesh's eyes turned yellow. The tracking system logged: "missed call."

I built Khurak 🎙️, a voice agent that calls TB patients daily in Hindi, Marathi, Bengali and Kannada and escalates danger signs to a human. 100% red-flag recall on noisy 8 kHz calls.

Built on @GnaniAI Prisma v3.0 + Timbre v3.0
#GreatIndianAIInternshipChallenge #GnaniAI
[video]

## Follow-up (two days after the main post)

"How Khurak decides, and why no LLM is allowed to." Attach a screenshot of a decision trace and the evaluation table.
Then talk about the one unsafe miss in the evaluation and what it taught you about fused negation in Kannada speech recognition. Honest posts like this tend to get real comments.
