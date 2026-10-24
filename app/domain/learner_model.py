"""Learner profile and mastery estimation (Phase 2, section 9).

Stores academic evidence only: per-skill states, an evidence log and observed
misconceptions with expiry. No traits, moods or timing beyond a guess flag.
Only the maths engine's results (via the orchestrator) and parent actions write
here; the LLM never does.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
from enum import Enum
from typing import Optional

from .curriculum import SKILLS

# Hand-set parameters (Phase 2, section 9.4). Fit from pilot data later.
P_INIT = 0.2
P_LEARN = 0.15
P_GUESS = 0.2
P_GUESS_SUPPORTED = 0.5     # correct after help levels 1-3 is weaker evidence
P_GUESS_FAST = 0.45         # very fast answers may be guesses
P_SLIP = 0.1
FORGET_PER_DAY = 0.02
FAST_MS = 1500
ASR_MIN_CONFIDENCE = 0.8
REVIEW_INTERVALS = [2, 7, 21]          # days; hypothesis to tune in pilot
MISCONCEPTION_EXPIRY_DAYS = 30


class State(str, Enum):
    NOT_SEEN = "not_seen"
    INTRODUCED = "introduced"
    SUPPORTED = "supported"
    INDEPENDENT = "independent"
    SECURE = "secure"
    DUE_FOR_REVIEW = "due_for_review"


class Kind(str, Enum):
    PRACTICE = "practice"
    TRANSFER = "transfer"
    REPRESENTATION = "representation"
    REVIEW = "review"
    DIAGNOSTIC = "diagnostic"


@dataclass
class Evidence:
    skill: str
    item: str
    correct: bool
    help: int = 0
    kind: Kind = Kind.PRACTICE
    ms: Optional[int] = None
    input_mode: str = "tap"
    asr_confidence: Optional[float] = None
    day: str = field(default_factory=lambda: date.today().isoformat())

    def counts_for_mastery(self) -> bool:
        if self.help >= 4:
            return False
        if self.input_mode == "voice" and (self.asr_confidence or 0) < ASR_MIN_CONFIDENCE:
            return False
        return True


@dataclass
class SkillRecord:
    skill: str
    p_known: float = P_INIT
    state: State = State.NOT_SEEN
    last_update: Optional[str] = None
    independent_days: list = field(default_factory=list)   # days with >=2 independent correct
    independent_today: int = 0
    transfer_ok: bool = False
    representation_ok: bool = False
    review_index: int = -1
    next_review: Optional[str] = None


class LearnerModel:
    def __init__(self, data: Optional[dict] = None):
        data = data or {}
        self.skills: dict[str, SkillRecord] = {}
        for sid, rec in data.get("skills", {}).items():
            rec = dict(rec)
            rec["state"] = State(rec["state"])
            self.skills[sid] = SkillRecord(**rec)
        self.misconceptions: dict[str, dict] = data.get("misconceptions", {})
        self.log: list[dict] = data.get("log", [])

    # ---------- serialisation ----------
    def to_dict(self) -> dict:
        return {
            "skills": {k: {**asdict(v), "state": v.state.value} for k, v in self.skills.items()},
            "misconceptions": self.misconceptions,
            "log": self.log[-500:],   # rolling window
        }

    def rec(self, skill: str) -> SkillRecord:
        if skill not in SKILLS:
            raise KeyError(skill)
        return self.skills.setdefault(skill, SkillRecord(skill))

    # ---------- reading ----------
    def state(self, skill: str, today: Optional[date] = None) -> State:
        today = today or date.today()
        r = self.skills.get(skill)
        if not r:
            return State.NOT_SEEN
        if r.next_review and date.fromisoformat(r.next_review) < today and r.state in (State.INDEPENDENT, State.SECURE):
            return State.DUE_FOR_REVIEW
        return r.state

    def p_known(self, skill: str, today: Optional[date] = None) -> float:
        r = self.skills.get(skill)
        if not r:
            return P_INIT
        return self._decayed(r, today or date.today())

    def due_reviews(self, today: Optional[date] = None) -> list[str]:
        today = today or date.today()
        return [s for s in self.skills if self.state(s, today) == State.DUE_FOR_REVIEW]

    # ---------- writing ----------
    def mark_introduced(self, skill: str) -> None:
        r = self.rec(skill)
        if r.state == State.NOT_SEEN:
            r.state = State.INTRODUCED

    def _decayed(self, r: SkillRecord, today: date) -> float:
        if not r.last_update:
            return r.p_known
        days = max(0, (today - date.fromisoformat(r.last_update)).days)
        return r.p_known * ((1 - FORGET_PER_DAY) ** days)

    def update(self, ev: Evidence, today: Optional[date] = None) -> State:
        today = today or date.fromisoformat(ev.day)
        r = self.rec(ev.skill)
        self.log.append({**{k: v for k, v in asdict(ev).items() if k != "ms"}, "kind": ev.kind.value})  # answer time is used, not stored

        if r.last_update != today.isoformat():
            r.independent_today = 0

        if ev.counts_for_mastery():
            p = self._decayed(r, today)
            guess = P_GUESS
            if 1 <= ev.help <= 3:
                guess = P_GUESS_SUPPORTED
            if ev.correct and ev.ms is not None and ev.ms < FAST_MS:
                guess = max(guess, P_GUESS_FAST)
            if ev.correct:
                post = p * (1 - P_SLIP) / (p * (1 - P_SLIP) + (1 - p) * guess)
            else:
                post = p * P_SLIP / (p * P_SLIP + (1 - p) * (1 - guess))
            r.p_known = post + (1 - post) * P_LEARN
        r.last_update = today.isoformat()

        self._update_state(r, ev, today)
        return self.state(ev.skill, today)

    def _update_state(self, r: SkillRecord, ev: Evidence, today: date) -> None:
        if r.state == State.NOT_SEEN:
            r.state = State.INTRODUCED

        if ev.kind == Kind.REVIEW:
            if ev.correct and ev.help == 0:
                r.review_index = min(r.review_index + 1, len(REVIEW_INTERVALS) - 1)
                r.next_review = (today + timedelta(days=REVIEW_INTERVALS[r.review_index])).isoformat()
                if today.isoformat() not in r.independent_days:
                    r.independent_days.append(today.isoformat())
            else:
                # Failed review: back to supported, not to "not seen".
                r.state = State.SUPPORTED
                r.review_index = -1
                r.next_review = (today + timedelta(days=REVIEW_INTERVALS[0])).isoformat()
                return

        if ev.kind == Kind.REPRESENTATION and ev.correct:
            r.representation_ok = True
        if ev.kind == Kind.TRANSFER and ev.correct and ev.help <= 3:
            r.transfer_ok = True

        if ev.kind == Kind.PRACTICE and ev.correct:
            if ev.help == 0 and ev.counts_for_mastery():
                r.independent_today += 1
                if r.independent_today >= 2 and today.isoformat() not in r.independent_days:
                    r.independent_days.append(today.isoformat())
            elif r.state in (State.INTRODUCED,):
                r.state = State.SUPPORTED
        elif ev.kind == Kind.PRACTICE and not ev.correct and r.state == State.INTRODUCED:
            r.state = State.SUPPORTED

        if r.independent_days and r.state in (State.NOT_SEEN, State.INTRODUCED, State.SUPPORTED):
            r.state = State.INDEPENDENT
            if r.review_index < 0:
                r.review_index = 0
                r.next_review = (today + timedelta(days=REVIEW_INTERVALS[0])).isoformat()

        if (len(set(r.independent_days)) >= 2 and r.transfer_ok and r.representation_ok
                and r.state in (State.INDEPENDENT, State.DUE_FOR_REVIEW)):
            r.state = State.SECURE

    # ---------- misconceptions ----------
    def record_bug(self, skill: str, bug: str, item: str, today: Optional[date] = None) -> dict:
        today = today or date.today()
        key = f"{skill}:{bug}"
        m = self.misconceptions.setdefault(key, {"skill": skill, "bug": bug, "items": [],
                                                 "first_seen": today.isoformat(), "last_seen": today.isoformat()})
        if item not in m["items"]:
            m["items"].append(item)
        m["last_seen"] = today.isoformat()
        return m

    def active_misconceptions(self, today: Optional[date] = None) -> list[dict]:
        """Only patterns seen on 2+ different items count; all expire after 30 days unseen."""
        today = today or date.today()
        out = []
        for m in self.misconceptions.values():
            age = (today - date.fromisoformat(m["last_seen"])).days
            if age > MISCONCEPTION_EXPIRY_DAYS:
                continue
            out.append({**m, "confirmed": len(m["items"]) >= 2})
        return out

    def dismiss_misconception(self, skill: str, bug: str) -> bool:
        """Parent marks an observation as wrong: it is removed, not softened."""
        return self.misconceptions.pop(f"{skill}:{bug}", None) is not None
