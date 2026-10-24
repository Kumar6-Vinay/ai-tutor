"""Deterministic column-arithmetic engine for 2-digit addition and subtraction.

The engine is the only component allowed to decide whether a step is right.
It also matches wrong steps against a bug library so the tutor can respond to
the misconception rather than just the wrong digit.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Op(str, Enum):
    ADD = "+"
    SUB = "-"


class Step(str, Enum):
    ONES = "ones"
    TENS = "tens"
    DONE = "done"


class Bug(str, Enum):
    """Known error patterns (bug library)."""
    SMALLER_FROM_LARGER = "smaller_from_larger"   # 52-27: ones 7-2=5
    NO_DECREMENT = "regrouped_no_decrement"       # 52-27: regrouped but tens 5-2=3
    UNNEEDED_REGROUP = "unneeded_regroup"         # opened a ten when top ones was big enough
    NO_CARRY = "forgot_carry"                     # 38+45: tens 3+4=7
    WRONG_OPERATION = "wrong_operation"           # added instead of subtracted, or the reverse
    AMBIGUOUS_REGROUP = "ambiguous_regroup"       # 52-27 = 35: fits smaller-from-larger AND no-decrement


BUG_TEXT = {
    Bug.SMALLER_FROM_LARGER: "Took the smaller digit from the larger in a column",
    Bug.NO_DECREMENT: "Opened a ten but did not reduce the tens",
    Bug.UNNEEDED_REGROUP: "Opened a ten when it was not needed",
    Bug.NO_CARRY: "Forgot to carry the ten into the tens column",
    Bug.WRONG_OPERATION: "Used the other operation",
    Bug.AMBIGUOUS_REGROUP: "Got an answer that fits two different regrouping mistakes",
}


@dataclass
class StepResult:
    correct: bool
    step: Step                      # step that was checked
    next_step: Step                 # step now active
    bug: Optional[Bug] = None
    expected: Optional[int] = None  # kept server-side; never sent to the child unless help level 6


@dataclass
class ColumnProblem:
    a: int
    b: int
    op: Op
    regrouped: bool = False   # subtraction: a ten opened; addition: a ten carried
    ones_value: Optional[int] = None
    tens_value: Optional[int] = None
    step: Step = Step.ONES
    explicit_regroup: bool = False   # child tapped the regroup control
    ones_ambiguous: bool = False     # correct ones digit also equals the smaller-from-larger digit
    events: list = field(default_factory=list)

    def __post_init__(self) -> None:
        if not (10 <= self.a <= 99 and 0 <= self.b <= 99):
            raise ValueError("Only 2-digit problems are supported")
        if self.op == Op.SUB and self.b > self.a:
            raise ValueError("Result would be negative; not in Class 1-3 scope")
        if self.op == Op.ADD and self.a + self.b > 99:
            raise ValueError("Sum over 99 is out of scope")

    # digits
    @property
    def at(self) -> int: return self.a // 10
    @property
    def ao(self) -> int: return self.a % 10
    @property
    def bt(self) -> int: return self.b // 10
    @property
    def bo(self) -> int: return self.b % 10

    @property
    def needs_regroup(self) -> bool:
        if self.op == Op.SUB:
            return self.ao < self.bo
        return self.ao + self.bo >= 10

    @property
    def answer(self) -> int:
        return self.a - self.b if self.op == Op.SUB else self.a + self.b

    def expected_ones(self) -> int:
        if self.op == Op.SUB:
            return (self.ao + 10 - self.bo) if self.needs_regroup else (self.ao - self.bo)
        return (self.ao + self.bo) % 10

    def expected_tens(self) -> int:
        if self.op == Op.SUB:
            return (self.at - (1 if self.regrouped else 0)) - self.bt
        return self.at + self.bt + (1 if self.regrouped else 0)

    def regroup(self) -> StepResult:
        """Child taps 'Open a ten' (subtraction) or 'Carry a ten' (addition)."""
        if self.step != Step.ONES:
            return StepResult(False, self.step, self.step)
        if self.regrouped:
            return StepResult(True, Step.ONES, Step.ONES)
        if not self.needs_regroup:
            self.events.append(("regroup", False, Bug.UNNEEDED_REGROUP))
            return StepResult(False, Step.ONES, Step.ONES, bug=Bug.UNNEEDED_REGROUP)
        self.regrouped = True
        self.explicit_regroup = True
        self.events.append(("regroup", True, None))
        return StepResult(True, Step.ONES, Step.ONES)

    def enter(self, digit: int) -> StepResult:
        if not 0 <= digit <= 9:
            raise ValueError("digit must be 0-9")
        if self.step == Step.ONES:
            return self._enter_ones(digit)
        if self.step == Step.TENS:
            return self._enter_tens(digit)
        return StepResult(False, Step.DONE, Step.DONE)

    def _enter_ones(self, d: int) -> StepResult:
        exp = self.expected_ones()
        if d == exp:
            # Regrouping done mentally counts as regrouping.
            if self.needs_regroup:
                if (self.op == Op.SUB and not self.explicit_regroup and not self.regrouped
                        and d == self.bo - self.ao):
                    self.ones_ambiguous = True
                self.regrouped = True
            self.ones_value = d
            self.step = Step.TENS
            self.events.append(("ones", True, None))
            return StepResult(True, Step.ONES, Step.TENS, expected=exp)
        bug = None
        if self.op == Op.SUB:
            if self.needs_regroup and not self.regrouped and d == self.bo - self.ao:
                bug = Bug.SMALLER_FROM_LARGER
            elif d == (self.ao + self.bo) % 10:
                bug = Bug.WRONG_OPERATION
        else:
            if d == abs(self.ao - self.bo):
                bug = Bug.WRONG_OPERATION
        self.events.append(("ones", False, bug))
        return StepResult(False, Step.ONES, Step.ONES, bug=bug, expected=exp)

    def _enter_tens(self, d: int) -> StepResult:
        exp = self.expected_tens()
        if d == exp:
            self.tens_value = d
            self.step = Step.DONE
            self.events.append(("tens", True, None))
            return StepResult(True, Step.TENS, Step.DONE, expected=exp)
        bug = None
        if self.op == Op.SUB:
            if self.regrouped and d == self.at - self.bt:
                bug = Bug.AMBIGUOUS_REGROUP if self.ones_ambiguous else Bug.NO_DECREMENT
            elif d == self.at + self.bt:
                bug = Bug.WRONG_OPERATION
        else:
            if self.regrouped and d == self.at + self.bt:
                bug = Bug.NO_CARRY
            elif d == abs(self.at - self.bt):
                bug = Bug.WRONG_OPERATION
        self.events.append(("tens", False, bug))
        return StepResult(False, Step.TENS, Step.TENS, bug=bug, expected=exp)

    def to_view(self) -> dict:
        """What the client may see. Never includes expected answers."""
        return {
            "a": self.a, "b": self.b, "op": self.op.value,
            "digits": {"at": self.at, "ao": self.ao, "bt": self.bt, "bo": self.bo},
            "regrouped": self.regrouped, "step": self.step.value,
            "ones": self.ones_value, "tens": self.tens_value,
        }


def check_whole_answer(a: int, b: int, op: Op, value: int) -> tuple[bool, Optional[Bug]]:
    """For word problems answered as a single number."""
    p = ColumnProblem(a, b, op)
    if value == p.answer:
        return True, None
    if op == Op.SUB and p.needs_regroup:
        sfl = (p.at - p.bt) * 10 + abs(p.ao - p.bo)
        if value == sfl:
            return False, Bug.SMALLER_FROM_LARGER
    if op == Op.SUB and value == a + b:
        return False, Bug.WRONG_OPERATION
    if op == Op.ADD and value == abs(a - b):
        return False, Bug.WRONG_OPERATION
    if op == Op.ADD and p.needs_regroup and value == (p.at + p.bt) * 10 + (p.ao + p.bo) % 10:
        return False, Bug.NO_CARRY
    return False, None
