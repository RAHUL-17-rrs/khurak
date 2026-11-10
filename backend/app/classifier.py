"""Turn a Prisma transcript into structured understanding. No LLM, fully explainable.

Pipeline
1. normalise   - Unicode NFD, drop nukta, chandrabindu->anusvara, strip punctuation,
                 but remember clause boundaries (। , . ? ! and "but"-words).
2. match       - every lexicon phrase is searched; LONGEST phrase wins and masks its
                 span, so "नहीं ली" (missed) is never also read as "ली" (taken).
                 Exact substring on token boundaries first; fuzzy (rapidfuzz partial
                 ratio >= 88) for phrases of 5+ chars to absorb ASR spelling drift.
                 Short words (हाँ, हो, ना) only ever match a whole token exactly.
3. negation    - a symptom is `negated` if a negation word (or Kannada -ಲ್ಲ suffix)
                 appears within 3 tokens after / 2 before it, inside the same clause.
4. escalate    - vomiting + an intensifier (बार बार, दिवसांपासून, বারবার ...) in the same
                 clause becomes the red flag `persistent_vomit`; otherwise it is a
                 `watch` symptom for the health worker.
5. confidence  - derived from how unambiguous the evidence was.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml
from rapidfuzz import fuzz

from .config import DATA_DIR
from .translit import key_phrase, key_token

LEX_DIR = DATA_DIR / "lexicon"
LANG_FILE = {"hi-IN": "hi", "hi-en": "hi", "mr-IN": "mr", "bn-IN": "bn", "kn-IN": "kn"}

RED_FLAGS = ["yellow_eyes", "blood_cough", "persistent_vomit", "breathless", "vision", "rash"]
FUZZY_MIN_LEN = 5
FUZZY_MIN_LEN_SINGLE = 6
FUZZY_THRESHOLD = 88
CLAUSE_SPLIT = re.compile(r"[।॥.,!?;:|\n]+|\s(?:लेकिन|पर|पण|परंतु|কিন্তু|ಆದರೆ|but)\s")


@dataclass
class Match:
    category: str        # dose_taken | red:yellow_eyes | benign:orange_urine | ...
    phrase: str
    start: int           # token index
    end: int             # exclusive
    clause: int
    score: int           # 100 exact, else fuzzy score


@dataclass
class Understanding:
    transcript: str
    dose: str = "UNCLEAR"                 # TAKEN | MISSED | STOPPED | UNCLEAR
    red_flags: list[str] = field(default_factory=list)
    negated: list[str] = field(default_factory=list)
    benign: list[str] = field(default_factory=list)
    watch: list[str] = field(default_factory=list)
    affirm: bool = False
    deny: bool = False
    no_problem: bool = False
    away: bool = False
    asked_about_stopping: bool = False
    unsure: bool = False
    hesitant: bool = False
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# ----------------------------------------------------------------------------- normalisation

_NUKTAS = {"़", "়", "಼"}
_ZW = {"‌", "‍", "﻿"}


def normalise(text: str) -> str:
    t = unicodedata.normalize("NFD", text.lower())
    t = "".join(ch for ch in t if ch not in _NUKTAS and ch not in _ZW)
    t = t.replace("ँ", "ं")            # chandrabindu -> anusvara (हाँ == हां)
    t = unicodedata.normalize("NFC", t)
    t = t.replace("-", " ")
    return t


def _tokens(text: str) -> list[str]:
    return re.findall(r"[^\s\W]+|[ऀ-෿]+", text, flags=re.UNICODE)


def tokenize_with_clauses(text: str) -> tuple[list[str], list[int], set[int]]:
    """Tokens, the clause index of each token, and which clauses were questions ('?')."""
    toks, clause_ids, questions = [], [], set()
    norm = " " + normalise(text) + " "
    parts = CLAUSE_SPLIT.split(norm)
    seps = CLAUSE_SPLIT.findall(norm)
    for ci, clause in enumerate(parts):
        if ci < len(seps) and "?" in seps[ci]:
            questions.add(ci)
        for tok in re.findall(r"\S+", clause):
            tok = re.sub(r"[\"'“”‘’()\[\]{}…]+", "", tok)
            if tok:
                toks.append(tok)
                clause_ids.append(ci)
    return toks, clause_ids, questions


# ----------------------------------------------------------------------------- lexicon


@lru_cache(maxsize=None)
def load_lexicon(lang: str) -> dict:
    """Flatten <lang>.yaml + en.yaml into {category: [normalised phrases]}."""
    out: dict[str, set[str]] = {}

    def add(cat: str, phrases):
        out.setdefault(cat, set()).update(normalise(p).strip() for p in phrases if p)

    for name in (LANG_FILE.get(lang, "hi"), "en"):
        path = LEX_DIR / f"{name}.yaml"
        if not path.exists():
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for k, v in raw.items():
            if isinstance(v, dict):
                for sub, phrases in v.items():
                    add(f"{k}:{sub}", phrases)
            else:
                add(k, v)
    return {k: sorted(v, key=len, reverse=True) for k, v in out.items()}


MATCH_CATS_PREFIX = ("dose_", "red:", "benign:", "watch:", "vomit", "away", "no_problem", "affirm", "deny", "unsure")
PHONETIC_LANGS = {"hi-IN", "hi-en", "mr-IN"}


@lru_cache(maxsize=None)
def phonetic_lexicon(lang: str) -> dict:
    """The same lexicon, keyed phonetically (script-agnostic)."""
    out = {}
    for cat, phrases in load_lexicon(lang).items():
        keys = {key_phrase(p) for p in phrases}
        out[cat] = sorted((k for k in keys if len(k) >= 2), key=len, reverse=True)
    return out


def find_matches(tokens: list[str], clauses: list[int], lex: dict, used: list[bool] | None = None,
                 fuzzy_single: bool = True) -> list[Match]:
    """Longest-first, non-overlapping phrase matching over tokens. `used` is shared across passes."""
    cands: list[tuple[int, int, str, str, int]] = []  # (n_tokens, len, cat, phrase, -)
    for cat, phrases in lex.items():
        if not cat.startswith(MATCH_CATS_PREFIX):
            continue
        for p in phrases:
            cands.append((len(p.split()), len(p), cat, p, 0))
    # longer phrases first (by chars) so they claim their span before sub-phrases
    cands.sort(key=lambda c: (c[1], c[0]), reverse=True)

    used = used if used is not None else [False] * len(tokens)
    matches: list[Match] = []
    for n, _, cat, phrase, _ in cands:
        ptoks = phrase.split()
        n = len(ptoks)
        for i in range(0, len(tokens) - n + 1):
            if any(used[i:i + n]):
                continue
            window = tokens[i:i + n]
            score = 0
            if window == ptoks:
                score = 100
            elif ((n > 1 or fuzzy_single)
                  and len(phrase) >= (FUZZY_MIN_LEN if n > 1 else FUZZY_MIN_LEN_SINGLE)
                  and len(" ".join(window)) >= FUZZY_MIN_LEN):
                # single short words must not drift: "hoon" (am) is NOT "khoon" (blood)
                joined = " ".join(window)
                # prefix match handles inflection: पिवळे~पिवळेसर, তোমার suffixes, ತೊಂದರೆಯಿಲ್ಲ
                if all(w.startswith(p) for w, p in zip(window, ptoks)) and len(ptoks[-1]) >= 3:
                    score = 95
                else:
                    s = fuzz.ratio(joined, phrase)
                    if s >= FUZZY_THRESHOLD:
                        score = int(s)
            if score:
                for k in range(i, i + n):
                    used[k] = True
                matches.append(Match(cat, phrase, i, i + n, clauses[i], score))
    matches.sort(key=lambda m: m.start)
    return matches


def _is_negation(tok: str, lex: dict) -> bool:
    if tok in lex.get("negation", []):
        return True
    return any(tok.endswith(suf) and len(tok) > len(suf) + 1 for suf in lex.get("negation_suffix", []))


def _negated(m: Match, tokens: list[str], clauses: list[int], lex: dict) -> bool:
    # the matched phrase itself may contain a fused negation (ತೊಂದರೆಯಿಲ್ಲ)
    for k in range(m.start, m.end):
        if _is_negation(tokens[k], lex) and tokens[k] not in m.phrase.split():
            return True
    lo, hi = max(0, m.start - 2), min(len(tokens), m.end + 3)
    for k in list(range(lo, m.start)) + list(range(m.end, hi)):
        if clauses[k] == m.clause and _is_negation(tokens[k], lex):
            return True
    return False


# ----------------------------------------------------------------------------- main entry


def classify(transcript: str, lang: str, stage: str = "ask_dose") -> Understanding:
    """stage: ask_dose | followup_dose | ask_symptoms | confirm_symptom | family_check"""
    u = Understanding(transcript=transcript)
    if not transcript or not transcript.strip():
        u.evidence.append("empty transcript")
        return u

    lex = load_lexicon(lang)
    tokens, clauses, question_clauses = tokenize_with_clauses(transcript)
    qwords = set(lex.get("question", []))
    question_clauses |= {clauses[i] for i, t in enumerate(tokens) if t in qwords}
    used = [False] * len(tokens)
    matches = find_matches(tokens, clauses, lex, used)
    if lang in PHONETIC_LANGS:
        # pass 2: script-agnostic phonetic keys catch codemix like "मैंने dawai band कर दी"
        rtoks = [key_token(t) for t in tokens]
        for m in find_matches(rtoks, clauses, phonetic_lexicon(lang), used, fuzzy_single=False):
            m.score = min(m.score, 97)
            m.phrase = "~" + m.phrase
            matches.append(m)
        matches.sort(key=lambda m: m.start)
    intensifier_clauses = {
        clauses[i] for i in range(len(tokens))
        for p in lex.get("intensifier", []) if tokens[i:i + len(p.split())] == p.split()
    }

    # hesitation markers ("हम्म", "शायद", "বোধহয়") are scanned on raw tokens and never consume spans
    hes = [p for p in lex.get("hesitation", [])
           if any(tokens[i:i + len(p.split())] == p.split() for i in range(len(tokens)))]
    if not hes and lang in PHONETIC_LANGS:
        rt = [key_token(t) for t in tokens]
        hes = [p for p in lex.get("hesitation", [])
               if any(rt[i:i + len(p.split())] == key_phrase(p).split() for i in range(len(rt)))]
    if hes:
        u.hesitant = True
        u.evidence.append("hesitation=" + ",".join(hes))

    dose_hits: dict[str, list[Match]] = {}
    fuzzy_used = False
    for m in matches:
        neg = _negated(m, tokens, clauses, lex)
        tag = f"{m.category}={m.phrase}" + ("" if m.score == 100 else f"~{m.score}") + (" (neg)" if neg else "")
        u.evidence.append(tag)
        fuzzy_used |= m.score < 100
        cat = m.category
        if cat == "dose_stopped" and m.clause in question_clauses:
            # "दवा बंद कर दूँ क्या?" = asking whether to stop, not having stopped
            u.asked_about_stopping = True
            u.evidence.append("stop-phrase inside a question -> not counted as stopped")
            continue
        if cat.startswith("dose_"):
            dose_hits.setdefault(cat[5:].upper(), []).append(m)
        elif cat.startswith("red:"):
            name = cat[4:]
            (u.negated if neg else u.red_flags).append(name)
        elif cat == "vomit":
            if neg:
                u.negated.append("persistent_vomit")
            elif m.clause in intensifier_clauses:
                u.red_flags.append("persistent_vomit")
                u.evidence.append("vomiting + intensifier in same clause -> persistent_vomit")
            else:
                u.watch.append("vomiting")
        elif cat.startswith("benign:") and not neg:
            u.benign.append(cat[7:])
        elif cat.startswith("watch:") and not neg:
            u.watch.append(cat[6:])
        elif cat == "away":
            u.away = True
        elif cat == "no_problem":
            u.no_problem = True
        elif cat in ("affirm", "deny"):
            # a bare yes/no only counts if it LEADS the answer or the answer is short:
            # "नहीं, ली नहीं" = no;  "अभी टाइम नहीं है" != no
            if m.start <= 1 or len(tokens) <= 3:
                setattr(u, cat, True)
            else:
                u.evidence[-1] += " (ignored: not leading)"
        elif cat == "unsure":
            u.unsure = True

    # a symptom both asserted and negated -> treat as asserted (safety first)
    u.negated = [s for s in dict.fromkeys(u.negated) if s not in u.red_flags]
    u.red_flags = list(dict.fromkeys(u.red_flags))
    u.benign = list(dict.fromkeys(u.benign))
    u.watch = list(dict.fromkeys(u.watch))

    # ---- dose intent
    kinds = set(dose_hits)
    if u.away:
        kinds.add("MISSED")
    if len(kinds) == 1:
        u.dose = kinds.pop()
        u.confidence = 0.8 if fuzzy_used else 0.92
    elif kinds == {"TAKEN", "STOPPED"} or kinds == {"MISSED", "STOPPED"}:
        u.dose, u.confidence = "STOPPED", 0.75     # "le li thi, ab band kar di" -> stopped wins
    elif len(kinds) > 1:
        u.dose, u.confidence = "UNCLEAR", 0.3
        u.evidence.append("conflicting dose intents: " + ",".join(sorted(kinds)))
    elif stage in ("ask_dose", "followup_dose", "family_check"):
        # fall back on bare yes / no
        if u.affirm and not u.deny:
            u.dose, u.confidence = "TAKEN", 0.7
        elif u.deny and not u.affirm and not u.no_problem:
            u.dose, u.confidence = "MISSED", 0.65
        else:
            u.dose, u.confidence = "UNCLEAR", 0.2
    else:
        u.confidence = 0.85 if (u.red_flags or u.benign or u.watch or u.no_problem or u.deny or u.affirm) else 0.3

    if u.red_flags:
        u.confidence = max(u.confidence, 0.9)
    return u
