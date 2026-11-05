"""Script-agnostic phonetic keys for Devanagari + romanised Hindi/Marathi.

Prisma's `codemix` output can switch script mid-phrase ("मैंने dawai band कर दी"). Matching on
a loose phonetic key makes "बंद कर दी", "band kar di" and "band कर दी" identical:
    key("बंद कर दी") == key("band kar di") == "band kar di"
"""
from __future__ import annotations

import re

_CONS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh",
    "ञ": "n", "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d",
    "ध": "dh", "न": "n", "प": "p", "फ": "f", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r",
    "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h", "ळ": "l", "ड़": "r", "ढ़": "rh",
}
_VOW = {"अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ए": "e", "ऐ": "ai", "ओ": "o",
        "औ": "au", "ऋ": "ri", "ऑ": "o"}
_MATRA = {"ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
          "ृ": "ri", "ॉ": "o"}
_NASAL = {"ं": "n", "ँ": "n"}
VIRAMA = "्"


def _deva_word(w: str) -> str:
    w = w.replace("़", "")                  # nukta
    out, i = [], 0
    while i < len(w):
        ch = w[i]
        if ch in _CONS:
            out.append(_CONS[ch])
            nxt = w[i + 1] if i + 1 < len(w) else ""
            if nxt in _MATRA:
                out.append(_MATRA[nxt])
                i += 1
            elif nxt == VIRAMA:
                i += 1
            elif nxt:
                # inherent schwa: dropped at word end, and mid-word when a vowel precedes and the
                # next consonant carries its own vowel sign (Hindi schwa deletion): घेतली -> ghetli
                after = w[i + 2] if i + 2 < len(w) else ""
                mid_drop = out[:-1] and nxt in _CONS and after in _MATRA and i > 0
                if not mid_drop:
                    out.append("a")
        elif ch in _VOW:
            out.append(_VOW[ch])
        elif ch in _NASAL:
            out.append("n")
        elif ch == "ः":
            out.append("h")
        elif ch.isascii():
            out.append(ch)
        i += 1
    return "".join(out)


def _squash(s: str) -> str:
    s = s.lower()
    for a, b in (("aa", "a"), ("ee", "i"), ("oo", "u"), ("ph", "f"), ("w", "v"), ("z", "j"),
                 ("q", "k"), ("y", "i"), ("ai", "e")):
        s = s.replace(a, b)
    s = re.sub(r"(.)\1+", r"\1", s)             # collapse doubles: "chhod" ~ "chod"
    s = re.sub(r"(?<=[aeiou])n$", "", s) if len(s) > 2 else s   # nahin~nahi, haan~ha
    s = s.replace("chh", "ch")
    return s.rstrip("h") if len(s) > 3 else s    # "nahin"/"nahi", "haan"/"ha" stay distinct enough


def key_token(tok: str) -> str:
    if re.search(r"[ऀ-ॿ]", tok):
        tok = _deva_word(tok)
    elif re.search(r"[^\x00-\x7f]", tok):
        return tok                                # other scripts: unchanged
    return _squash(tok)


def key_phrase(p: str) -> str:
    return " ".join(key_token(t) for t in p.split())
