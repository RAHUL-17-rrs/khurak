"""The agent's brain: a deterministic, auditable decision table.

Two layers:
* `next_step()` - conversation control (which question next, or close). Pure function.
* `final_decision()` - status + actions, evaluated TOP-TO-BOTTOM, FIRST MATCH WINS.

Hard safety invariants (tested in tests/test_policy.py):
  I1  Any un-negated red flag  -> RED. Nothing can downgrade it.
  I2  Never GREEN unless the dose is TAKEN with confidence >= 0.5 on every turn.
  I3  A red-flag word with negation is never silently dropped: it is confirmed once.
  I4  The Evon second-listener can only ADD concern (-> AMBER review), never remove it.
  I5  Patients only ever hear fixed templates from prompts.py.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from .classifier import Understanding

GREEN, AMBER, RED = "GREEN", "AMBER", "RED"

RULES = {
    "R1": "Red-flag symptom reported -> escalate to health worker now",
    "R2": "Danger word said with negation -> ask one confirmation question",
    "R3": "Patient stopped treatment -> 'complete the course' + flag worker",
    "R4": "Dose still unclear after one follow-up -> flag worker",
    "R5": "Dose unclear (first time) -> ask one follow-up",
    "R6": "Dose missed -> acknowledge + flag worker",
    "R6b": "Non-red symptom needing review (vomiting once, pain, tingling, unconfirmed) -> flag worker",
    "R6c": "Evon second-listener raised a concern the rules did not -> human review",
    "R7": "Harmless, expected side effect -> approved reassurance + log",
    "R8": "Dose taken, no problems -> thank + log",
    "R9": "Low confidence somewhere in the call -> never green, flag worker",
    "F1": "Family contact reports danger sign -> escalate",
    "F2": "Family contact reached; patient unreachable -> home visit / follow-up",
    "X1": "No answer -> retry in 2 hours (max 2 attempts)",
    "X2": "Two unanswered attempts -> call family contact",
    "X3": "Three consecutive days without confirmed dose -> home visit needed",
}


@dataclass
class CallMemory:
    """Everything understood so far in one call."""
    kind: str = "patient"                    # patient | family
    dose: str = "UNCLEAR"
    dose_conf: float = 0.0
    followup_asked: bool = False
    symptoms_asked: bool = False
    red_flags: list[str] = field(default_factory=list)
    benign: list[str] = field(default_factory=list)
    watch: list[str] = field(default_factory=list)
    pending_confirm: list[str] = field(default_factory=list)
    confirmed_absent: list[str] = field(default_factory=list)
    confirm_asked: list[str] = field(default_factory=list)
    unconfirmed: list[str] = field(default_factory=list)
    unspecified_problem: bool = False
    away: bool = False
    min_conf: float = 1.0
    quotes: list[str] = field(default_factory=list)
    evon_concerns: list[dict] = field(default_factory=list)
    turns: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "CallMemory":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Step:
    stage: str | None            # next question stage, or None = close the call
    prompt: str | None = None    # template key for the next question
    prompt_vars: dict = field(default_factory=dict)
    rule: str | None = None


@dataclass
class Decision:
    status: str
    rule: str
    rule_text: str
    reasons: list[str]
    say: list[str]               # template keys to play before hanging up
    actions: list[dict]          # tool calls the orchestrator executes

    def to_dict(self) -> dict:
        return asdict(self)


DOSE_RANK = {"UNCLEAR": 0, "TAKEN": 1, "MISSED": 2, "STOPPED": 3}


def absorb(mem: CallMemory, stage: str, u: Understanding) -> None:
    """Merge one turn's understanding into the call memory."""
    mem.turns += 1
    if u.transcript.strip():
        mem.quotes.append(u.transcript.strip())

    if stage in ("ask_dose", "followup_dose", "family_check"):
        if u.dose != "UNCLEAR":
            mem.dose, mem.dose_conf = u.dose, u.confidence
            mem.min_conf = min(mem.min_conf, u.confidence)
        elif stage == "followup_dose" or mem.kind == "family":
            mem.min_conf = min(mem.min_conf, u.confidence)
        # patient volunteered symptom info with the dose answer -> no need to ask again
        if u.no_problem or u.red_flags or u.negated or u.benign or u.watch:
            mem.symptoms_asked = True
    elif stage == "ask_symptoms":
        # a later "I stopped" / "I didn't take it" outranks an earlier "yes"
        if DOSE_RANK.get(u.dose, 0) > DOSE_RANK.get(mem.dose, 0) and u.dose in ("STOPPED", "MISSED"):
            mem.dose, mem.dose_conf = u.dose, u.confidence
        if not (u.red_flags or u.benign or u.watch or u.negated or u.no_problem or u.deny or u.affirm):
            mem.min_conf = min(mem.min_conf, 0.3)       # said something, we understood nothing
        elif u.affirm and not (u.red_flags or u.benign or u.watch or u.negated):
            mem.unspecified_problem = True               # "haan" to "any problems?"

    if stage == "confirm_symptom" and mem.pending_confirm:
        sym = mem.pending_confirm.pop(0)
        if u.red_flags and sym in u.red_flags or (u.affirm and not u.deny):
            mem.red_flags.append(sym)
        elif u.deny or u.no_problem or sym in u.negated:
            mem.confirmed_absent.append(sym)
        else:
            mem.unconfirmed.append(sym)                  # still unsure -> amber
        mem.red_flags += [r for r in u.red_flags if r != sym]
    else:
        mem.red_flags += u.red_flags
        for s in u.negated:
            if s not in mem.red_flags and s not in mem.confirm_asked:
                mem.pending_confirm.append(s)

    mem.benign += u.benign
    mem.watch += u.watch
    mem.away |= u.away
    for attr in ("red_flags", "benign", "watch", "pending_confirm"):
        setattr(mem, attr, list(dict.fromkeys(getattr(mem, attr))))
    mem.pending_confirm = [s for s in mem.pending_confirm if s not in mem.red_flags]


def next_step(mem: CallMemory, stage: str) -> Step:
    """What does the agent ask next? (R1/R2/R5 live here.)"""
    if mem.kind == "family":
        return Step(None)

    if mem.red_flags:                                   # R1: never keep a sick patient on the line
        return Step(None, rule="R1")

    if mem.pending_confirm:                             # R2: confirm a negated danger word once
        sym = mem.pending_confirm[0]
        mem.confirm_asked.append(sym)
        return Step("confirm_symptom", "confirm_symptom", {"symptom": sym}, rule="R2")

    if stage == "ask_dose" and mem.dose == "UNCLEAR" and not mem.followup_asked:
        mem.followup_asked = True                       # R5
        return Step("followup_dose", "followup_dose", rule="R5")

    if not mem.symptoms_asked:
        mem.symptoms_asked = True
        return Step("ask_symptoms", "ask_symptoms")

    return Step(None)


def final_decision(mem: CallMemory) -> Decision:
    """Status + actions. Top to bottom, first match wins."""
    quote = " / ".join(mem.quotes[-2:])[:400]

    def d(status, rule, reasons, say, actions):
        return Decision(status, rule, RULES[rule], reasons, say, actions)

    if mem.kind == "family":
        if mem.red_flags:
            return d(RED, "F1", mem.red_flags, ["red_advice"],
                     [{"tool": "escalate_red", "reason": "+".join(mem.red_flags), "quote": quote}])
        reason = "family_reports_away_or_missed" if (mem.away or mem.dose in ("MISSED", "STOPPED")) \
            else "patient_unreachable_family_contacted"
        return d(AMBER, "F2", [reason], ["family_close"],
                 [{"tool": "flag_worker", "reason": reason, "quote": quote}])

    if mem.red_flags:                                                     # R1
        return d(RED, "R1", mem.red_flags, ["red_advice"],
                 [{"tool": "escalate_red", "reason": "+".join(mem.red_flags), "quote": quote}])

    if mem.dose == "STOPPED":                                             # R3
        return d(AMBER, "R3", ["stopped_treatment"], ["complete_course"],
                 [{"tool": "flag_worker", "reason": "stopped_treatment", "quote": quote}])

    if mem.dose == "UNCLEAR":                                             # R4
        return d(AMBER, "R4", ["unclear_answer"], ["unclear_close"],
                 [{"tool": "flag_worker", "reason": "unclear_answer", "quote": quote}])

    if mem.dose == "MISSED":                                              # R6
        return d(AMBER, "R6", ["missed_dose"], ["missed_ack"],
                 [{"tool": "flag_worker", "reason": "missed_dose", "quote": quote}])

    review = mem.watch + [f"unconfirmed_{s}" for s in mem.unconfirmed] + \
        (["unspecified_problem"] if mem.unspecified_problem else [])
    if review:                                                            # R6b
        return d(AMBER, "R6b", review, ["symptom_ack"],
                 [{"tool": "flag_worker", "reason": "+".join(review), "quote": quote}])

    if mem.evon_concerns:                                                 # R6c (I4)
        reasons = [f"evon:{c.get('concern', 'concern')}" for c in mem.evon_concerns]
        return d(AMBER, "R6c", reasons, ["symptom_ack"],
                 [{"tool": "flag_worker", "reason": "+".join(reasons), "quote": quote}])

    if mem.min_conf < 0.5 or mem.dose_conf < 0.5:                         # R9 (I2)
        return d(AMBER, "R9", ["low_confidence"], ["unclear_close"],
                 [{"tool": "flag_worker", "reason": "low_confidence", "quote": quote}])

    if mem.benign:                                                        # R7
        return d(GREEN, "R7", mem.benign, [f"reassure_{mem.benign[0]}", "thanks"],
                 [{"tool": "log_note", "note": "+".join(mem.benign)}])

    return d(GREEN, "R8", ["dose_taken"], ["thanks"], [])                 # R8
