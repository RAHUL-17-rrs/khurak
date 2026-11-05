"""Every scripted scenario passes at text level (ground-truth transcript -> dialogue -> policy)."""
import re
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.dialogue import simulate  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"
S = yaml.safe_load((DATA / "scenarios.yaml").read_text(encoding="utf-8"))
P = {p["id"]: p for p in yaml.safe_load((DATA / "patients.yaml").read_text(encoding="utf-8"))["patients"]}
strip = lambda t: re.sub(r"<[^>]+>", "", t).strip()  # noqa: E731

CASES = []
for pid, sc in S["demo"].items():
    if "answers" in sc:
        CASES.append((pid, P[pid]["language"], {k: strip(v) for k, v in sc["answers"].items()}, sc["expected"], "patient"))
    else:
        CASES.append((pid, P[pid]["language"], {"family_check": strip(sc["family_answer"])}, sc["expected"], "family"))
for e in S["eval"]:
    CASES.append((e["id"], e["lang"], {k: strip(v) for k, v in e["answers"].items()}, e["expected"], "patient"))


@pytest.mark.parametrize("cid,lang,answers,expected,kind", CASES, ids=[c[0] for c in CASES])
def test_scenario(cid, lang, answers, expected, kind):
    d, _ = simulate(lang, answers, kind)
    assert (d.status, d.rule) == (expected["status"], expected["rule"])
