"""Tutoring orchestrator (Phase 2, sections 7-8).

Deterministic code decides what happens next. Language models only reword the
text this module produces (see app/services/phraser.py).
"""
from __future__ import annotations

import time
import uuid
from datetime import date, timedelta
from typing import Any, Optional

from . import help_ladder
from .curriculum import ITEM_BANK, PLACE_VALUE_PROBES, SKILLS, WORD_PROBLEMS, skill_for
from .learner_model import Evidence, Kind, LearnerModel, State
from .maths_engine import BUG_TEXT, Bug, ColumnProblem, Op, Step, check_whole_answer

SESSION_CAP_MIN = {"5-7": 15, "8-10": 25}
# Every problem on the homework is worked on screen. Skills are taught easiest first; a problem that needed
# real help comes back once later; a fresh problem per skill checks the child can do it alone.
SKILL_ORDER = ["add_no_carry", "sub_no_regroup", "add_carry", "sub_regroup"]
STRUGGLE_HELP = 2        # help level at which a problem counts as "not yet learned"

TRY_AT_HOME = {
    "sub_regroup": "Use 5 bundles of 10 sticks. Ask {name} to take away 17 and show you how.",
    "sub_no_regroup": "Use bundles and single sticks. Ask {name} to take away 23 from 58.",
    "add_carry": "Use sticks: make 28 and 15, then bundle any 10 loose sticks together.",
    "add_no_carry": "Use coins of 10 and 1. Ask {name} to add 21 and 14.",
    "place_value_100": "Ask {name} to show 43 with bundles of ten and single sticks.",
}

STATE_PLAIN = {
    State.NOT_SEEN: "Not started yet.",
    State.INTRODUCED: "Has seen how it works.",
    State.SUPPORTED: "Can do it with some help. Needs more guided practice.",
    State.INDEPENDENT: "Did it alone today. Not yet secure: needs success on another day.",
    State.SECURE: "Secure: solved alone on different days and in a word problem.",
    State.DUE_FOR_REVIEW: "Due for a quick review.",
}


def _op(s: str) -> Op:
    return Op.SUB if s in ("-", "−") else Op.ADD


def sym(op: Op) -> str:
    return "−" if op == Op.SUB else "+"


class Session:
    """One tutoring session. Fully serialisable via to_dict / from_dict."""

    def __init__(self, data: dict):
        self.d = data

    # ---------- construction ----------
    @classmethod
    def start(cls, child: dict, items: list[dict], learner: LearnerModel, today: Optional[date] = None) -> "Session":
        today = today or date.today()
        probs = []
        for it in items:
            op = _op(it.get("op", "-"))
            ColumnProblem(int(it["a"]), int(it["b"]), op)  # validates scope
            probs.append({"a": int(it["a"]), "b": int(it["b"]), "op": op.value})
        if not probs:
            raise ValueError("No confirmed worksheet items")
        skills = [skill_for(p["a"], p["b"], Op(p["op"])) for p in probs]
        target = max(set(skills), key=skills.count)
        plan = cls._plan(child, target, probs, learner, today)
        d = {
            "id": uuid.uuid4().hex, "child_id": child["id"], "name": child["nickname"],
            "age_band": child.get("age_band", "5-7"), "target": target,
            "started": time.time(), "queue": plan, "current": None, "action_no": 0,
            "skills": [k for k in SKILL_ORDER if k in skills], "carry": [], "checks": {},
            "used_bank": [[x["a"], x["b"]] for x in plan if x.get("mode") in ("check", "review")],
            "signals": 0, "wrong_run": 0, "extra_done": False, "paused": None,
            "results": [], "bugs": [], "diag": {}, "worksheet": probs, "ended": False,
        }
        s = cls(d)
        s._advance()
        return s

    @staticmethod
    def _fresh(skill: str, worksheet: list[dict], used: list) -> Optional[tuple[int, int]]:
        """A reviewed bank item that is neither on the homework nor already used this session."""
        seen = {(p["a"], p["b"]) for p in worksheet} | {tuple(u) for u in used}
        return next((ab for ab in ITEM_BANK.get(skill, []) if ab not in seen), None)

    @staticmethod
    def _plan(child: dict, target: str, probs: list[dict], learner: LearnerModel, today: date) -> list[dict]:
        plan: list[dict] = []
        groups: dict[str, list[dict]] = {}
        for p in probs:
            groups.setdefault(skill_for(p["a"], p["b"], Op(p["op"])), []).append(p)
        skills = [k for k in SKILL_ORDER if k in groups]
        # 1. Due reviews first (at most two), from the item bank.
        for sk in learner.due_reviews(today)[:2]:
            if sk in ITEM_BANK:
                a, b = ITEM_BANK[sk][0]
                op = "-" if sk.startswith("sub") else "+"
                plan.append({"type": "column", "mode": "review", "a": a, "b": b, "op": op})
        # 2. Prerequisite checks.
        new = lambda sk: learner.state(sk, today) in (State.NOT_SEEN, State.INTRODUCED)
        if learner.state("place_value_100", today) not in (State.INDEPENDENT, State.SECURE):
            plan.append({"type": "diagnostic_build", "target": PLACE_VALUE_PROBES[0]})
            plan.append({"type": "diagnostic_build", "target": PLACE_VALUE_PROBES[2]})
        if any(k.startswith("sub") and new(k) for k in skills):
            plan.append({"type": "diagnostic_fact", "a": 40, "b": 20, "op": "-"})
        if any(k.startswith("add") and new(k) for k in skills):
            plan.append({"type": "diagnostic_fact", "a": 30, "b": 20, "op": "+"})
        # 3. One block per skill in the homework, easiest first: teach if needed, then every problem.
        for sk in skills:
            rest = list(groups[sk])
            if learner.state(sk, today) in (State.NOT_SEEN, State.INTRODUCED, State.SUPPORTED, State.DUE_FOR_REVIEW):
                plan.append({"type": "model", **rest.pop(0)})
                if rest:
                    plan.append({"type": "column", "mode": "completion", **rest.pop(0)})
            for p in rest:
                plan.append({"type": "column", "mode": "practice", **p})
            # Transfer: the same skill in a story.
            if sk in WORD_PROBLEMS:
                wp = WORD_PROBLEMS[sk][0]
                plan.append({"type": "word_problem", "text": wp["text"], "a": wp["a"], "b": wp["b"],
                             "op": "-" if sk.startswith("sub") else "+"})
        # 4. Check: a fresh problem per skill, done alone.
        for sk in skills:
            ab = Session._fresh(sk, probs, [])
            if ab:
                plan.append({"type": "column", "mode": "check", "a": ab[0], "b": ab[1],
                             "op": "-" if sk.startswith("sub") else "+"})
        plan.append({"type": "summary"})
        return plan

    # ---------- serialisation ----------
    def to_dict(self) -> dict:
        return self.d

    @classmethod
    def from_dict(cls, d: dict) -> "Session":
        return cls(d)

    # ---------- helpers ----------
    @property
    def cur(self) -> dict:
        return self.d["current"]

    def _elapsed_min(self) -> float:
        return (time.time() - self.d["started"]) / 60

    def _advance(self) -> None:
        q = self.d["queue"]
        cap = SESSION_CAP_MIN.get(self.d["age_band"], 15)
        if self._elapsed_min() > cap:
            # Stop rule: problems not reached are saved for next time, never silently dropped.
            carry = [{"a": a["a"], "b": a["b"], "op": a["op"]} for a in q
                     if a["type"] == "column" and a.get("mode") in ("practice", "completion")]
            if carry:
                self.d["carry"] = self.d.get("carry", []) + carry
            self.d["queue"] = q = ([{"type": "handback", "items": carry}] if carry else []) + [{"type": "summary"}]
        nxt = q.pop(0) if q else {"type": "summary"}
        nxt = dict(nxt)
        nxt["no"] = self.d["action_no"] = self.d["action_no"] + 1
        if nxt["type"] == "column":
            nxt["state"] = {"a": nxt["a"], "b": nxt["b"], "op": nxt["op"], "regrouped": nxt.get("mode") == "completion"
                            and ColumnProblem(nxt["a"], nxt["b"], Op(nxt["op"])).needs_regroup,
                            "ones": None, "tens": None, "step": "ones"}
            nxt.update(help=0, wrong=0, tapped_regroup=False, shown_at=time.time())
        if nxt["type"] in ("diagnostic_build",):
            nxt["tries"] = 0
        if nxt["type"] in ("word_problem", "diagnostic_fact"):
            nxt["tries"] = 0
        if nxt["type"] == "summary":
            self.d["ended"] = True
        self.d["current"] = nxt

    def _problem(self) -> ColumnProblem:
        st = self.cur["state"]
        p = ColumnProblem(st["a"], st["b"], Op(st["op"]))
        p.regrouped, p.ones_value, p.tens_value, p.step = st["regrouped"], st["ones"], st["tens"], Step(st["step"])
        p.explicit_regroup, p.ones_ambiguous = st.get("explicit", False), st.get("ambiguous", False)
        return p

    def _save_problem(self, p: ColumnProblem) -> None:
        self.cur["state"].update(regrouped=p.regrouped, ones=p.ones_value, tens=p.tens_value, step=p.step.value,
                                 explicit=p.explicit_regroup, ambiguous=p.ones_ambiguous)

    def _fb(self, text: str, tone: str = "neutral", **extra) -> dict:
        return {"text": text, "tone": tone, **extra}

    def _bug(self, learner: LearnerModel, skill: str, bug: Bug, item: str, today: date) -> None:
        self.d["bugs"].append({"skill": skill, "bug": bug.value, "item": item})
        learner.record_bug(skill, bug.value, item, today)

    # ---------- the view sent to the client ----------
    def view(self) -> dict:
        c = dict(self.cur)
        out: dict[str, Any] = {"no": c["no"], "type": c["type"], "name": self.d["name"]}
        t = c["type"]
        if t == "column":
            p = self._problem()
            out.update(mode=c["mode"], problem=p.to_view(), help_level=c["help"],
                       title={"completion": "Your turn, with a head start", "practice": "Your turn",
                              "review": "Quick review", "extra": "A fresh one",
                              "retry": "Let's try it again", "check": "Show what you know"}[c["mode"]],
                       say={"completion": ("I opened a ten for you. Now finish it." if p.op == Op.SUB and p.regrouped
                                           else "Finish this one with me."),
                            "practice": "Solve this one. Start with the ones.",
                            "review": "Do you remember this from last time?",
                            "extra": "Let's try a new one, just like the last.",
                            "retry": "This one was tricky. Let's try it again, you can do it!",
                            "check": "Now try a brand new one all by yourself. You've got this!"}[c["mode"]],
                       regroup_label="Open a ten" if p.op == Op.SUB else "Carry a ten")
        elif t == "diagnostic_build":
            out.update(target=c["target"], title=f"Make {c['target']}",
                       say=f"Use bundles of ten and single sticks to make {c['target']}.")
        elif t == "teach_place_value":
            n = c["number"]
            out.update(number=n, title="Tens and ones",
                       say=f"{n} means {n // 10} tens and {n % 10} ones. Each bundle has 10 sticks.")
        elif t == "diagnostic_fact":
            op = Op(c["op"])
            out.update(title="Quick one", say=f"What is {c['a']} {sym(op)} {c['b']}?")
        elif t == "model":
            out.update(title=f"Watch: {c['a']} {sym(Op(c['op']))} {c['b']}", a=c["a"], b=c["b"], op=c["op"],
                       steps=self._model_steps(c["a"], c["b"], Op(c["op"])))
        elif t == "word_problem":
            out.update(title="A story", say=c["text"].format(name=self.d["name"]))
        elif t == "handback":
            out.update(title="Saved for next time", say="We will learn these together next time. You worked hard today!",
                       items=[f"{i['a']} {sym(Op(i['op']))} {i['b']}" for i in c["items"]])
        elif t == "pause":
            out.update(title="Break time", say="Stretch and have some water. Your work is saved.")
        elif t == "summary":
            sk = SKILLS[self.d["target"]]
            done = [r for r in self.d["results"] if r["type"] == "column"]
            alone = [r for r in done if r["help"] == 0 and r["wrong"] == 0]
            out.update(title="Today you learned", say=f"{sk.child_name}.",
                       chips=[SKILLS["place_value_100"].child_name] + [SKILLS[k].child_name for k in self.d.get("skills") or [self.d["target"]]],
                       solved=len(done), alone=len(alone))
        return out

    @staticmethod
    def _model_steps(a: int, b: int, op: Op) -> list[dict]:
        p = ColumnProblem(a, b, op)
        if op == Op.SUB:
            steps = [{"say": f"This is {a}. It is {p.at} tens and {p.ao} ones.", "do": "show"},
                     {"say": f"We need to take away {b}. That is {p.bt} tens and {p.bo} ones.", "do": "show"}]
            if p.needs_regroup:
                steps += [{"say": f"Can we take {p.bo} ones from {p.ao} ones? No. So we open one ten. Tap a bundle.", "do": "open"},
                          {"say": f"Now we have {p.at - 1} tens and {p.ao + 10} ones. Take away {p.bo} ones.", "do": "remove_ones"},
                          {"say": f"{p.ao + 10 - p.bo} ones are left. Now take away {p.bt} tens.", "do": "remove_tens"}]
            else:
                steps += [{"say": f"Take away {p.bo} ones.", "do": "remove_ones"},
                          {"say": f"{p.ao - p.bo} ones are left. Now take away {p.bt} tens.", "do": "remove_tens"}]
            steps.append({"say": f"{p.answer // 10} tens and {p.answer % 10} ones are left. So {a} − {b} = {p.answer}.", "do": "done"})
        else:
            steps = [{"say": f"This is {a}: {p.at} tens and {p.ao} ones. We add {b}: {p.bt} tens and {p.bo} ones.", "do": "show"},
                     {"say": f"Put the ones together: {p.ao} + {p.bo} = {p.ao + p.bo}.", "do": "join_ones"}]
            if p.needs_regroup:
                steps.append({"say": f"{p.ao + p.bo} ones is more than 9. Bundle 10 of them into a ten. Tap to bundle.", "do": "bundle"})
            steps.append({"say": f"Now count the tens and ones. {a} + {b} = {p.answer}.", "do": "done"})
        return steps

    # ---------- input handling ----------
    def respond(self, inp: dict, learner: LearnerModel, today: Optional[date] = None) -> dict:
        today = today or date.today()
        kind = inp.get("kind")
        c = self.cur
        t = c["type"]

        if kind == "stuck":
            return self._signal()
        if kind == "break":
            if t in ("pause", "summary"):
                return {"feedback": None}
            self.d["paused"] = c
            self.d["current"] = {"type": "pause", "no": c["no"]}
            return {"feedback": None}
        if t == "pause" and kind == "continue":
            self.d["current"] = self.d["paused"]
            self.d["paused"] = None
            self.d["signals"] = 0
            if self.cur["type"] == "column":
                return self._hint(3, auto=False)
            return {"feedback": None}

        if t == "column":
            return self._column(inp, learner, today)
        if t == "diagnostic_build":
            return self._build(inp, learner, today)
        if t == "teach_place_value" and kind == "continue":
            self._advance()
            return {"feedback": None}
        if t == "diagnostic_fact" and kind == "number":
            ok, _ = check_whole_answer(c["a"], c["b"], Op(c["op"]), int(inp["value"]))
            self.d["diag"]["fact"] = ok
            ans = ColumnProblem(c["a"], c["b"], Op(c["op"])).answer
            joiner = "take away" if c["op"] == "-" else "and"
            text = f"Yes. {c['a'] // 10} tens {joiner} {c['b'] // 10} tens is {ans // 10} tens: {ans}."
            self._advance()
            return {"feedback": self._fb(text if ok else "Tens work like ones. We will use this soon.", "good" if ok else "hint")}
        if t == "model" and kind == "continue":
            learner.mark_introduced(skill_for(c["a"], c["b"], Op(c["op"])))
            self.d.setdefault("watched", []).append(f"{c['a']}{sym(Op(c['op']))}{c['b']}")
            self._advance()
            return {"feedback": None}
        if t == "word_problem" and kind == "number":
            return self._word(inp, learner, today)
        if t == "handback" and kind == "continue":
            self._advance()
            return {"feedback": None}
        return {"feedback": None}

    def _signal(self) -> dict:
        self.d["signals"] += 1
        if self.d["signals"] >= 2:
            self.d["signals"] = 0
            return {"feedback": self._fb("This one is tricky. What would you like?", "neutral", offer_break=True)}
        if self.cur["type"] == "column":
            return self._hint(min(self.cur["help"] + 1, 3), auto=False, prefix="That's OK. Let's do one step at a time. ")
        return {"feedback": self._fb("That's OK. Take your time, or tap Help me.", "neutral")}

    def _hint(self, level: int, auto: bool, prefix: str = "") -> dict:
        c = self.cur
        p = self._problem()
        level = min(level, help_ladder.MAX_AUTO_LEVEL) if auto else min(level, help_ladder.MAX_LEVEL)
        c["help"] = max(c["help"], level)
        h = help_ladder.hint(p, level)
        extra: dict[str, Any] = {"help_level": level, "aid": h["aid"]}
        if h["aid"] == "reveal":
            if p.step == Step.ONES and p.needs_regroup and p.op == Op.SUB:
                p.regrouped = True
                self._save_problem(p)
        return {"feedback": self._fb(prefix + h["text"], "hint", **extra)}

    def _column(self, inp: dict, learner: LearnerModel, today: date) -> dict:
        c = self.cur
        kind = inp.get("kind")
        p = self._problem()
        skill = skill_for(p.a, p.b, p.op)
        item = f"{p.a}{sym(p.op)}{p.b}"
        if kind == "help":
            return self._hint(c["help"] + 1 if c["help"] < help_ladder.MAX_LEVEL else help_ladder.MAX_LEVEL, auto=False)
        if kind == "regroup":
            r = p.regroup()
            self._save_problem(p)
            if r.bug:
                self._bug(learner, skill, r.bug, item, today)
                return {"feedback": self._fb(help_ladder.bug_feedback(p, r.bug), "hint")}
            if r.correct and p.op == Op.SUB:
                c["tapped_regroup"] = True
                return {"feedback": self._fb(f"Good. Now there are {p.ao + 10} ones and {p.at - 1} tens. "
                                             "Take away the ones.", "good")}
            if r.correct:
                c["tapped_regroup"] = True
                return {"feedback": self._fb("Good. Write the ones, and remember the ten you carry.", "good")}
            return {"feedback": self._fb("Look at the tens now.", "hint")}
        if kind != "digit":
            return {"feedback": None}
        r = p.enter(int(inp["value"]))
        self._save_problem(p)
        if r.correct:
            self.d["wrong_run"] = 0
            if r.next_step == Step.TENS:
                return {"feedback": self._fb("Right. Now the tens.", "good")}
            return self._finish_column(p, skill, item, learner, today)
        # wrong step
        c["wrong"] += 1
        self.d["wrong_run"] += 1
        if r.bug:
            self._bug(learner, skill, r.bug, item, today)
        res: dict
        msg = help_ladder.bug_feedback(p, r.bug)
        if msg:
            c["help"] = max(c["help"], 2)
            res = {"feedback": self._fb(msg, "hint", help_level=c["help"])}
        else:
            res = self._hint(c["help"] + 1, auto=True)
        if self.d["wrong_run"] >= 3:
            self.d["wrong_run"] = 0
            res["feedback"]["offer_break"] = True
        return res

    def _finish_column(self, p: ColumnProblem, skill: str, item: str, learner: LearnerModel, today: date) -> dict:
        c = self.cur
        ms = int((time.time() - c["shown_at"]) * 1000)
        mode = c["mode"]
        first_try = c["wrong"] == 0
        kind = Kind.REVIEW if mode == "review" else Kind.PRACTICE
        help_used = c["help"] if mode != "completion" else max(c["help"], 1)  # head start counts as support
        learner.update(Evidence(skill=skill, item=item, correct=first_try, help=help_used, kind=kind, ms=ms,
                                day=today.isoformat()), today)
        if c.get("tapped_regroup") and c["help"] < 3:
            learner.update(Evidence(skill=skill, item=item, correct=True, kind=Kind.REPRESENTATION,
                                    day=today.isoformat()), today)
        self.d["results"].append({"type": "column", "item": item, "mode": mode, "help": help_used,
                                  "wrong": c["wrong"], "skill": skill})
        alone = help_used == 0 and first_try
        text = f"{p.a} {sym(p.op)} {p.b} = {p.answer}. " + ("You did it on your own." if alone else "You got there.")
        q = self.d["queue"]
        # After heavy help, always one fresh similar item before moving on (section 8.7).
        if c["help"] >= 5 and not self.d["extra_done"] and skill in ITEM_BANK:
            ab = self._fresh(skill, self.d["worksheet"], self.d["used_bank"])
            if ab:
                self.d["extra_done"] = True
                self.d["used_bank"].append(list(ab))
                q.insert(0, {"type": "column", "mode": "extra", "a": ab[0], "b": ab[1], "op": p.op.value})
        # A homework problem that needed real help comes back once, a few steps later.
        if mode in ("practice", "completion") and (c["wrong"] > 0 or c["help"] >= STRUGGLE_HELP):
            q.insert(min(2, max(0, len(q) - 1)), {"type": "column", "mode": "retry", "a": p.a, "b": p.b, "op": p.op.value})
        # The fresh check: if it was not done alone, teach it once more and check again.
        if mode == "check":
            self.d["checks"][skill] = alone
            if not alone and skill not in self.d.get("reteach", []):
                ab1 = self._fresh(skill, self.d["worksheet"], self.d["used_bank"])
                if ab1:
                    self.d["used_bank"].append(list(ab1))
                    ab2 = self._fresh(skill, self.d["worksheet"], self.d["used_bank"])
                    self.d.setdefault("reteach", []).append(skill)
                    again = [{"type": "model", "a": ab1[0], "b": ab1[1], "op": p.op.value}]
                    if ab2:
                        self.d["used_bank"].append(list(ab2))
                        again.append({"type": "column", "mode": "check", "a": ab2[0], "b": ab2[1], "op": p.op.value})
                    q[:0] = again
                    text += " Let's look at one more together, then you try again."
        self._advance()
        return {"feedback": self._fb(text, "good"), "completed": True}

    def _build(self, inp: dict, learner: LearnerModel, today: date) -> dict:
        c = self.cur
        if inp.get("kind") != "build":
            return {"feedback": None}
        tens, ones = int(inp["tens"]), int(inp["ones"])
        target = c["target"]
        if tens * 10 + ones == target and ones < 10:
            first = c["tries"] == 0
            learner.update(Evidence("place_value_100", f"build {target}", first, 0 if first else 2,
                                    Kind.PRACTICE, day=today.isoformat()), today)
            learner.update(Evidence("place_value_100", f"build {target}", True, kind=Kind.REPRESENTATION,
                                    day=today.isoformat()), today)
            self.d["diag"].setdefault("build", []).append(first)
            self._advance()
            return {"feedback": self._fb(f"Yes. {target // 10} tens and {target % 10} ones make {target}.", "good")}
        c["tries"] += 1
        if c["tries"] >= 2:
            learner.update(Evidence("place_value_100", f"build {target}", False, 0, Kind.PRACTICE,
                                    day=today.isoformat()), today)
            self.d["diag"].setdefault("build", []).append(False)
            # Teach place value, then rebuild a different number, before continuing.
            self.d["queue"] = [a for a in self.d["queue"] if a["type"] != "diagnostic_build"]
            self.d["queue"][:0] = [{"type": "teach_place_value", "number": target},
                                   {"type": "diagnostic_build", "target": PLACE_VALUE_PROBES[1]}]
            self._advance()
            return {"feedback": self._fb(f"{target} is {target // 10} tens and {target % 10} ones. "
                                         "Let's look at tens together.", "hint")}
        if ones >= 10:
            return {"feedback": self._fb(f"You have {ones} single sticks. Can you make a bundle of ten?", "hint")}
        return {"feedback": self._fb(f"You have {tens} tens and {ones} ones. That makes {tens * 10 + ones}. "
                                     f"Try to make {target}.", "hint")}

    def _word(self, inp: dict, learner: LearnerModel, today: date) -> dict:
        c = self.cur
        op = Op(c["op"])
        v = int(inp["value"])
        ok, bug = check_whole_answer(c["a"], c["b"], op, v)
        skill = skill_for(c["a"], c["b"], op)
        item = f"word {c['a']}{sym(op)}{c['b']}"
        if ok:
            help_used = 0 if c["tries"] == 0 else 3
            learner.update(Evidence(skill, item, c["tries"] == 0, help_used, Kind.TRANSFER, day=today.isoformat()), today)
            self.d["results"].append({"type": "word", "item": item, "tries": c["tries"]})
            self._advance()
            return {"feedback": self._fb(f"Yes, the answer is {v}.", "good")}
        c["tries"] += 1
        if bug:
            self._bug(learner, skill, bug, item, today)
        p = ColumnProblem(c["a"], c["b"], op)
        if c["tries"] >= 3:
            learner.update(Evidence(skill, item, False, 5, Kind.TRANSFER, day=today.isoformat()), today)
            self.d["results"].append({"type": "word", "item": item, "tries": c["tries"], "worked": True})
            self._advance()
            return {"feedback": self._fb(help_ladder.hint(p, 5)["text"], "hint")}
        if bug == Bug.SMALLER_FROM_LARGER:
            return {"feedback": self._fb(f"Check the ones: can we take {p.bo} from {p.ao}? What do we do then?", "hint")}
        if bug == Bug.WRONG_OPERATION:
            return {"feedback": self._fb("Is this a taking-away story or a putting-together story?", "hint")}
        return {"feedback": self._fb(f"Write it in columns on paper: {c['a']} {sym(op)} {c['b']}. Start with the ones.", "hint")}

    # ---------- parent report ----------
    def report(self, learner: LearnerModel, today: Optional[date] = None) -> dict:
        today = today or date.today()
        target = self.d["target"]
        cols = [r for r in self.d["results"] if r["type"] == "column"]
        alone = [r for r in cols if r["help"] == 0 and r["wrong"] == 0]
        word = next((r for r in self.d["results"] if r["type"] == "word"), None)
        state = learner.state(target, today)
        rec = learner.skills.get(target)
        seen_now = {(b["skill"], b["bug"]) for b in self.d["bugs"]}
        noticed = []
        for m in learner.active_misconceptions(today):
            if (m["skill"], m["bug"]) in seen_now:
                noticed.append({"text": BUG_TEXT[Bug(m["bug"])], "confirmed": m["confirmed"], "items": m["items"],
                                "status": ("seen on 2+ problems, likely a real misconception" if m["confirmed"]
                                           else "seen once, may be a slip")})
        nxt = rec.next_review if rec and rec.next_review else (today + timedelta(days=2)).isoformat()
        minutes = max(1, round(self._elapsed_min()))
        sheet = [f"{w['a']}{sym(Op(w['op']))}{w['b']}" for w in self.d["worksheet"]]
        carried = [f"{w['a']}{sym(Op(w['op']))}{w['b']}" for w in self.d.get("carry", [])]
        by_item: dict[str, bool] = {}
        for r in cols:
            if r["item"] in sheet and r["mode"] in ("practice", "completion", "retry"):
                by_item[r["item"]] = by_item.get(r["item"], False) or (r["help"] == 0 and r["wrong"] == 0)
        homework = {
            "total": len(sheet),
            "alone": [i for i in sheet if by_item.get(i)],
            "with_help": [i for i in sheet if i in by_item and not by_item[i]],
            "watched": [i for i in self.d.get("watched", []) if i not in by_item],
            "saved_for_next_time": carried,
        }
        checks = [{"skill": SKILLS[k].name, "passed": ok} for k, ok in self.d.get("checks", {}).items()]
        skills = self.d.get("skills") or [target]
        return {
            "date": today.isoformat(), "minutes": minutes, "skill": SKILLS[target].name, "name": self.d["name"],
            "where": STATE_PLAIN[state], "state": state.value,
            "solved": len(cols), "alone": len(alone),
            "max_help": max([r["help"] for r in cols], default=0),
            "word_problem": (None if not word else ("solved first time" if word["tries"] == 0
                                                    else "needed a worked example" if word.get("worked")
                                                    else "solved after a hint")),
            "place_value": self.d["diag"].get("build"),
            "noticed": noticed,
            "try_at_home": " ".join(TRY_AT_HOME[k].format(name=self.d["name"]) for k in skills),
            "homework": homework, "checks": checks,
            "skills": [{"name": SKILLS[k].name, "where": STATE_PLAIN[learner.state(k, today)]} for k in skills],
            "next_review": nxt,
            "stored": "Stored: skills, steps and help level. Not stored: voice, photos after reading, answer times or mood.",
        }
