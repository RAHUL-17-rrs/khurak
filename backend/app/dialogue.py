"""Pure, I/O-free call state machine. Used by BOTH the live orchestrator and the evaluator,
so the accuracy numbers measure exactly the logic that runs in production.

    DIALING -> GREETING -> ASK_DOSE -> [FOLLOWUP_DOSE] -> [ASK_SYMPTOMS] -> [CONFIRM_SYMPTOM] -> DECIDE -> CLOSE
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import evon
from .classifier import Understanding, classify
from .policy import CallMemory, Decision, absorb, final_decision, next_step
from .prompts import render, render_en

MAX_TURNS = 6
MAX_REPEATS = 2             # "please say that again" replays the question, at most twice per call
HESITATION_PAUSE_MS = 2500   # a long silence before "yes" is a hesitation signal (cf. Tell)


@dataclass
class Prompt:
    key: str
    text: str
    english: str
    vars: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"key": self.key, "text": self.text, "english": self.english, "vars": self.vars}


@dataclass
class TurnOutcome:
    stage: str
    understanding: Understanding
    evon: dict | None
    next_prompt: Prompt | None          # None -> call ends with `decision`
    step_rule: str | None
    decision: Decision | None


class Dialogue:
    def __init__(self, lang: str, name: str, kind: str = "patient", use_evon: bool = True):
        self.lang, self.name, self.kind = lang, name, kind
        self.mem = CallMemory(kind=kind)
        self.stage = "family_check" if kind == "family" else "ask_dose"
        self.use_evon = use_evon and evon.enabled()
        self.decision: Decision | None = None
        self.last_prompt_en = ""
        self.last_key: str | None = None      # the question on the line, so it can be replayed (R0)
        self.last_vars: dict = {}
        self.repeats = 0
        self.repeated_stage: str | None = None

    def prompt(self, key: str, **vars) -> Prompt:
        p = Prompt(key, render(key, self.lang, **vars), render_en(key, **vars), vars)
        return p

    # --- stateless hosting (Vercel): the whole call state round-trips through the client, signed
    def to_state(self) -> dict:
        return {"lang": self.lang, "name": self.name, "kind": self.kind, "stage": self.stage,
                "mem": self.mem.to_dict(), "last_prompt_en": self.last_prompt_en,
                "last_key": self.last_key, "last_vars": self.last_vars, "repeats": self.repeats,
                "repeated_stage": self.repeated_stage}

    @classmethod
    def from_state(cls, st: dict, use_evon: bool = True) -> "Dialogue":
        d = cls(st["lang"], st["name"], st["kind"], use_evon=use_evon)
        d.stage, d.last_prompt_en = st["stage"], st.get("last_prompt_en", "")
        d.mem = CallMemory.from_dict(st["mem"])
        d.last_key, d.last_vars = st.get("last_key"), st.get("last_vars") or {}
        d.repeats, d.repeated_stage = st.get("repeats", 0), st.get("repeated_stage")
        return d

    def opening(self) -> list[Prompt]:
        if self.kind == "family":
            ps = [self.prompt("family_check", name=self.name)]
        else:
            ps = [self.prompt("greeting", name=self.name), self.prompt("ask_dose")]
        self.last_prompt_en = ps[-1].english
        self.last_key, self.last_vars = ps[-1].key, ps[-1].vars
        return ps

    def closing(self) -> list[Prompt]:
        return [self.prompt(k) for k in (self.decision.say if self.decision else [])]

    def answer(self, transcript: str, onset_ms: int | None = None) -> TurnOutcome:
        """onset_ms = silence before the patient started speaking (audio answers only)."""
        stage = self.stage
        u = classify(transcript, self.lang, stage)
        if onset_ms is not None and onset_ms >= HESITATION_PAUSE_MS and transcript.strip():
            u.hesitant = True
            u.evidence.append(f"pause={onset_ms}ms before answering")

        # R0: "I couldn't hear you" is not an answer. Replay the same question instead of reading
        # "सुनाई नहीं दिया" as "नहीं" (missed) or spending the single follow-up on it.
        if (u.repeat and not _substantive(u) and self.last_key and self.repeats < MAX_REPEATS
                and self.repeated_stage != stage):
            self.repeats += 1
            self.repeated_stage = stage
            u.evidence.append("asked to repeat -> question replayed")
            p = self.prompt(self.last_key, **self.last_vars)
            return TurnOutcome(stage, u, None, p, "R0", None)

        absorb(self.mem, stage, u)

        opinion = None
        if self.use_evon and self.kind == "patient":
            opinion = evon.second_opinion(transcript, self.lang, self.last_prompt_en)
            self.mem.evon_concerns += evon.concerns_beyond_rules(
                opinion, self.mem.red_flags, self.mem.confirmed_absent)

        step = next_step(self.mem, stage)
        if step.stage is None or self.mem.turns >= MAX_TURNS:
            self.decision = final_decision(self.mem)
            self.stage = "closed"
            return TurnOutcome(stage, u, opinion, None, step.rule, self.decision)

        self.stage = step.stage
        p = self.prompt(step.prompt, **step.prompt_vars)
        self.last_prompt_en = p.english
        self.last_key, self.last_vars = p.key, p.vars
        return TurnOutcome(stage, u, opinion, p, step.rule, None)


def _substantive(u: Understanding) -> bool:
    """Did the answer carry real information (beyond a bare yes/no)?"""
    return bool(u.dose != "UNCLEAR" or u.red_flags or u.negated or u.benign or u.watch or u.no_problem
                or u.away or u.asked_about_stopping)


def simulate(lang: str, answers: dict[str, str], kind: str = "patient", name: str = "Test",
             use_evon: bool = False) -> tuple[Decision, list[dict]]:
    """Run a whole call against scripted per-stage transcripts (missing stage -> silence)."""
    d = Dialogue(lang, name, kind, use_evon=use_evon)
    d.opening()
    trace = []
    while d.stage != "closed":
        stage = d.stage
        text = answers.get(stage, "")
        out = d.answer(text)
        trace.append({"stage": stage, "transcript": text, "dose": out.understanding.dose,
                      "red": out.understanding.red_flags, "neg": out.understanding.negated,
                      "evidence": out.understanding.evidence})
    return d.decision, trace
