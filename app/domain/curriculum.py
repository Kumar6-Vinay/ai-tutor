"""Hand-authored skill graph for Class 1-3 maths (addition and subtraction to 100).

Human-authored and reviewed content only. The LLM never adds skills, items or
explanations here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .maths_engine import ColumnProblem, Op


@dataclass(frozen=True)
class Skill:
    id: str
    name: str            # parent-facing name
    child_name: str      # child-facing "I can..." name
    prerequisite: Optional[str]
    grade: int


SKILLS: dict[str, Skill] = {s.id: s for s in [
    Skill("place_value_100", "Tens and ones to 100", "Tens and ones", None, 1),
    Skill("add_no_carry", "2-digit addition without carrying", "Adding tens and ones", "place_value_100", 1),
    Skill("add_carry", "2-digit addition with carrying", "Carrying a ten", "add_no_carry", 2),
    Skill("sub_no_regroup", "2-digit subtraction without regrouping", "Taking away tens and ones", "place_value_100", 1),
    Skill("sub_regroup", "2-digit subtraction with regrouping", "Opening a ten", "sub_no_regroup", 2),
]}


def skill_for(a: int, b: int, op: Op) -> str:
    p = ColumnProblem(a, b, op)
    if op == Op.SUB:
        return "sub_regroup" if p.needs_regroup else "sub_no_regroup"
    return "add_carry" if p.needs_regroup else "add_no_carry"


# Reviewed item bank: fresh items for practice beyond the worksheet, by skill.
ITEM_BANK: dict[str, list[tuple[int, int]]] = {
    "sub_regroup": [(54, 29), (43, 18), (81, 37), (66, 48), (70, 26), (35, 17)],
    "sub_no_regroup": [(46, 23), (58, 31), (79, 45), (67, 24)],
    "add_carry": [(38, 45), (27, 46), (19, 56), (48, 37)],
    "add_no_carry": [(23, 45), (31, 52), (44, 33), (12, 67)],
}

# Parallel worked examples used at help level 5 (never the child's own item).
WORKED_EXAMPLE: dict[str, tuple[int, int]] = {
    "sub_regroup": (43, 18), "sub_no_regroup": (46, 23),
    "add_carry": (27, 46), "add_no_carry": (23, 45),
}

# Word problems for transfer checks. Names and contexts are reviewed for range.
WORD_PROBLEMS: dict[str, list[dict]] = {
    "sub_regroup": [
        {"text": "{name} had 45 stickers and gave away 18. How many are left?", "a": 45, "b": 18},
        {"text": "There were 62 mangoes in a basket. Aarav took 27. How many are left?", "a": 62, "b": 27},
    ],
    "sub_no_regroup": [
        {"text": "{name} had 58 marbles and lost 23. How many are left?", "a": 58, "b": 23},
    ],
    "add_carry": [
        {"text": "Meera has 28 beads and gets 15 more. How many beads now?", "a": 28, "b": 15},
    ],
    "add_no_carry": [
        {"text": "{name} read 21 pages on Monday and 14 on Tuesday. How many pages in all?", "a": 21, "b": 14},
    ],
}

# Place-value diagnostic numbers.
PLACE_VALUE_PROBES = [43, 56, 71, 38]
