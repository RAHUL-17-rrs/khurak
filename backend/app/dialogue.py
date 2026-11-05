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

MAX_TURNS = 5


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

    def prompt(self, key: str, **vars) -> Prompt:
        p = Prompt(key, render(key, self.lang, **vars), render_en(key, **vars), vars)
        return p

    def opening(self) -> list[Prompt]:
        if self.kind == "family":
            ps = [self.prompt("family_check", name=self.name)]
        else:
            ps = [self.prompt("greeting", name=self.name), self.prompt("ask_dose")]
        self.last_prompt_en = ps[-1].english
        return ps

    def closing(self) -> list[Prompt]:
        return [self.prompt(k) for k in (self.decision.say if self.decision else [])]

    def answer(self, transcript: str) -> TurnOutcome:
        stage = self.stage
        u = classify(transcript, self.lang, stage)
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
        return TurnOutcome(stage, u, opinion, p, step.rule, None)


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
