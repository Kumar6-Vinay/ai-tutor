"""Graduated help ladder (Phase 2, section 8.7) and bug-targeted feedback.

Levels:
 0 encourage an attempt   1 attention prompt     2 strategic question
 3 step-specific hint     4 representation       5 parallel worked example
 6 reveal this step (only after level 5)
Automatic escalation after wrong answers stops at level 4; levels 5-6 need an
explicit request for help.
"""
from __future__ import annotations

from typing import Optional

from .curriculum import WORKED_EXAMPLE, skill_for
from .maths_engine import Bug, ColumnProblem, Op, Step

MAX_AUTO_LEVEL = 4
MAX_LEVEL = 6


def _worked_example(p: ColumnProblem) -> str:
    a, b = WORKED_EXAMPLE[skill_for(p.a, p.b, p.op)]
    ex = ColumnProblem(a, b, p.op)
    if p.op == Op.SUB:
        if ex.needs_regroup:
            return (f"Watch: {a} − {b}. {ex.ao} is too small to take {ex.bo}, so open a ten: "
                    f"{ex.ao + 10} − {ex.bo} = {ex.ao + 10 - ex.bo}. Tens: {ex.at - 1} − {ex.bt} = {ex.at - 1 - ex.bt}. "
                    f"Answer {ex.answer}.")
        return (f"Watch: {a} − {b}. Ones: {ex.ao} − {ex.bo} = {ex.ao - ex.bo}. "
                f"Tens: {ex.at} − {ex.bt} = {ex.at - ex.bt}. Answer {ex.answer}.")
    if ex.needs_regroup:
        return (f"Watch: {a} + {b}. Ones: {ex.ao} + {ex.bo} = {ex.ao + ex.bo}. Write {(ex.ao + ex.bo) % 10} and carry 1 ten. "
                f"Tens: {ex.at} + {ex.bt} + 1 = {ex.at + ex.bt + 1}. Answer {ex.answer}.")
    return (f"Watch: {a} + {b}. Ones: {ex.ao} + {ex.bo} = {ex.ao + ex.bo}. "
            f"Tens: {ex.at} + {ex.bt} = {ex.at + ex.bt}. Answer {ex.answer}.")


def hint(p: ColumnProblem, level: int) -> dict:
    """Return {'level', 'text', 'aid'} for the active step. aid tells the client what to show."""
    level = max(1, min(level, MAX_LEVEL))
    sub = p.op == Op.SUB
    word = "open" if sub else "carry"
    if p.step == Step.ONES:
        top = p.ao + 10 if (sub and p.regrouped) else p.ao
        texts = {
            1: "Look at the ones column first.",
            2: (f"Is {p.ao} big enough to take away {p.bo}?" if sub and p.needs_regroup and not p.regrouped
                else (f"How many is {top} take away {p.bo}?" if sub else f"How many is {p.ao} and {p.bo} together?")),
            3: ("When the top is too small, we open a ten. Tap \"Open a ten\"." if sub and p.needs_regroup and not p.regrouped
                else (f"Count back {p.bo} from {top}." if sub
                      else (f"{p.ao} + {p.bo} is {p.ao + p.bo}. That is more than 9, so write the ones and carry the ten."
                            if p.needs_regroup else f"Count on {p.bo} from {p.ao}."))),
            4: "Here are the sticks for this problem. Use them to work out the ones.",
            5: _worked_example(p),
            6: (f"Write {p.expected_ones()} in the ones." + (f" We had to {word} a ten." if p.needs_regroup else "")),
        }
    else:
        top = p.at - 1 if (sub and p.regrouped) else p.at
        texts = {
            1: "Now look at the tens column.",
            2: ("You opened one ten. How many tens are left on top?" if sub and p.regrouped
                else ("You carried one ten. Remember to add it." if (not sub and p.regrouped)
                      else "Look at the tens on top and on the bottom.")),
            3: (f"{top} tens take away {p.bt} tens." if sub
                else f"{p.at} tens and {p.bt} tens" + (" and the 1 you carried." if p.regrouped else ".")),
            4: "Here are the sticks. Count the bundles.",
            5: _worked_example(p),
            6: f"Write {p.expected_tens()} in the tens.",
        }
    aid = {4: "sticks", 5: "worked_example", 6: "reveal"}.get(level)
    return {"level": level, "text": texts[level], "aid": aid}


def bug_feedback(p: ColumnProblem, bug: Optional[Bug]) -> Optional[str]:
    """Targeted response when a known misconception is detected."""
    if bug == Bug.SMALLER_FROM_LARGER:
        return (f"You took {p.ao} from {p.bo}. We always take the bottom number from the top. "
                f"Can we take {p.bo} from {p.ao}?")
    if bug == Bug.NO_DECREMENT:
        return "You opened a ten, so the tens column has one less now. How many tens are left?"
    if bug == Bug.UNNEEDED_REGROUP:
        return (f"Is {p.ao} big enough to take away {p.bo}? Then we don't need to open a ten."
                if p.op == Op.SUB else f"{p.ao} + {p.bo} is less than 10, so there is nothing to carry.")
    if bug == Bug.AMBIGUOUS_REGROUP:
        return (f"How did you get {p.ones_value} in the ones? Did you take {p.bo} from {p.ao + 10}, "
                f"or {p.ao} from {p.bo}? Then look at the tens again.")
    if bug == Bug.NO_CARRY:
        return "Did you add the ten you carried from the ones?"
    if bug == Bug.WRONG_OPERATION:
        return ("Look at the sign. Is it take away or add?")
    return None
