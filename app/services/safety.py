"""Output and input safety checks (Phase 2, sections 8.11 and 11)."""
from __future__ import annotations

import re

NUM = re.compile(r"\d+")

# Prohibited behaviours: shame, threats, loss framing, claimed feelings, dependency, secrecy, comparison.
PROHIBITED = [
    r"\beasy\b.*\bwhy can'?t you\b", r"\bshould know\b", r"\bdisappoint", r"\bi'?m (so )?(sad|happy|proud|upset)\b",
    r"\bi feel\b", r"\bi love you\b", r"\b(best )?friend\b", r"\bdon'?t tell\b", r"\bsecret\b",
    r"\bother (kids|children)\b", r"\byou'?ll lose\b", r"\bstreak\b", r"\bhurry\b", r"\bstupid\b", r"\bdumb\b",
]
PROHIBITED_RE = re.compile("|".join(PROHIBITED), re.IGNORECASE)

# Child free-text or speech that must trigger the disclosure protocol rather than tutoring.
DISCLOSURE = re.compile(r"\b(hurt me|hits? me|scared of|touch(ed)? me|hate myself|kill|die)\b", re.IGNORECASE)


def check_output(text: str) -> tuple[bool, str]:
    if PROHIBITED_RE.search(text or ""):
        return False, "prohibited phrasing"
    if len(text) > 400:
        return False, "too long"
    return True, ""


def check_reworded(original: str, reworded: str) -> tuple[bool, str]:
    """A reworded line must keep exactly the same numbers and pass the output check."""
    if sorted(NUM.findall(original)) != sorted(NUM.findall(reworded)):
        return False, "numbers changed"
    if len(reworded) > max(200, int(len(original) * 1.6)):
        return False, "too long"
    return check_output(reworded)


def is_disclosure(text: str) -> bool:
    return bool(DISCLOSURE.search(text or ""))
