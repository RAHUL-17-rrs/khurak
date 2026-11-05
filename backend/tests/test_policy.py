"""Safety invariants of the agent (see app/policy.py). Pure logic - no network, no audio."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.classifier import classify  # noqa: E402
from app.dialogue import simulate  # noqa: E402
from app.evon import concerns_beyond_rules  # noqa: E402
from app.policy import CallMemory, final_decision  # noqa: E402


# I1: any un-negated red flag -> RED, whatever else is said
@pytest.mark.parametrize("lang,answers", [
    ("hi-IN", {"ask_dose": "हाँ ले ली", "ask_symptoms": "आँखें पीली हो गई हैं"}),
    ("hi-IN", {"ask_dose": "नहीं ली, खांसी में खून आ रहा है"}),
    ("hi-IN", {"ask_dose": "मैंने दवा बंद कर दी", "ask_symptoms": "सांस फूल रही है"}),
    ("mr-IN", {"ask_dose": "घेतली", "ask_symptoms": "दोन दिवसांपासून उलटी होतेय"}),
    ("bn-IN", {"ask_dose": "খেয়েছি", "ask_symptoms": "চোখে ঝাপসা দেখছি"}),
    ("kn-IN", {"ask_dose": "ಹೌದು", "ask_symptoms": "ಕಣ್ಣು ಹಳದಿ ಆಗಿದೆ"}),
    ("hi-en", {"ask_dose": "haan le li", "ask_symptoms": "cough mein blood aa raha hai"}),
])
def test_red_flag_always_red(lang, answers):
    d, _ = simulate(lang, answers)
    assert d.status == "RED" and d.rule == "R1"


# I2: never GREEN unless the dose was understood as TAKEN
@pytest.mark.parametrize("answers", [
    {"ask_dose": "मौसम अच्छा है", "followup_dose": "पता नहीं", "ask_symptoms": "कुछ नहीं"},
    {"ask_dose": "", "followup_dose": ""},
    {"ask_dose": "अभी टाइम नहीं है", "followup_dose": "बाद में बात करते हैं"},
])
def test_unclear_never_green(answers):
    d, _ = simulate("hi-IN", answers)
    assert d.status == "AMBER"


def test_low_confidence_never_green():
    m = CallMemory(dose="TAKEN", dose_conf=0.4, min_conf=0.4)
    assert final_decision(m).status == "AMBER"


# I3: a negated danger word is confirmed, never silently dropped
def test_negation_asks_confirmation_then_green():
    d, trace = simulate("hi-IN", {"ask_dose": "हाँ ले ली, आँखें पीली नहीं हैं, सब ठीक है", "confirm_symptom": "नहीं"})
    assert [t["stage"] for t in trace] == ["ask_dose", "confirm_symptom"]
    assert d.status == "GREEN"


def test_negation_confirmed_yes_is_red():
    d, _ = simulate("hi-IN", {"ask_dose": "हाँ ले ली, आँखें पीली नहीं हैं", "confirm_symptom": "हाँ, थोड़ी पीली हैं"})
    assert d.status == "RED"


def test_negation_confirm_silence_is_amber():
    d, _ = simulate("hi-IN", {"ask_dose": "हाँ ले ली, आँखें पीली नहीं हैं", "confirm_symptom": ""})
    assert d.status == "AMBER"


# Questions are not statements
def test_question_about_stopping_is_not_stopped():
    u = classify("दवा बंद कर दूँ क्या?", "hi-IN", "ask_symptoms")
    assert u.dose != "STOPPED"


# Short-word fuzzy drift: "hoon" (am) must not become "khoon" (blood)
def test_hoon_is_not_khoon():
    u = classify("Main theek ho gaya hoon", "hi-en", "ask_dose")
    assert "blood_cough" not in u.red_flags


# Codemix mid-phrase script switch (observed from Prisma)
def test_codemix_script_switch():
    u = classify("अब मैं ठीक हूँ, मैंने dawai band कर दी।", "hi-en", "ask_dose")
    assert u.dose == "STOPPED"


# I4: Evon may only add concern
def test_evon_only_escalates():
    assert concerns_beyond_rules({"dose": "TAKEN", "red_flags": [], "concern": ""}, ["yellow_eyes"], []) == []
    added = concerns_beyond_rules({"dose": "TAKEN", "red_flags": ["blood_cough"], "concern": ""}, [], [])
    assert added and added[0]["concern"] == "possible_blood_cough"
    m = CallMemory(dose="TAKEN", dose_conf=0.9, red_flags=["yellow_eyes"])
    m.evon_concerns = []
    assert final_decision(m).status == "RED"           # Evon silence cannot lower a red
    m2 = CallMemory(dose="TAKEN", dose_conf=0.9, evon_concerns=[{"concern": "possible_vision"}])
    assert final_decision(m2).status == "AMBER"        # Evon concern lifts green -> amber


def test_orange_urine_reassured_green():
    d, _ = simulate("hi-IN", {"ask_dose": "हाँ ले ली", "ask_symptoms": "पेशाब लाल आ रहा है"})
    assert d.status == "GREEN" and d.rule == "R7" and d.say[0] == "reassure_orange_urine"


def test_family_away_is_amber():
    d, _ = simulate("kn-IN", {"family_check": "ಅಮ್ಮ ಊರಿಗೆ ಹೋಗಿದ್ದಾರೆ, ಮಾತ್ರೆ ತೆಗೆದುಕೊಂಡು ಹೋಗಿಲ್ಲ"}, kind="family")
    assert d.status == "AMBER" and d.rule == "F2"
