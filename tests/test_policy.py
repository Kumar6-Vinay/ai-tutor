from datetime import date

from app.domain.learner_model import LearnerModel, State
from app.domain.maths_engine import ColumnProblem, Op
from app.domain.policy import Session

D0 = date(2026, 10, 24)
CHILD = {"id": "c1", "nickname": "Riya", "age_band": "5-7"}
SHEET = [{"a": a, "b": b, "op": "-"} for a, b in [(52, 27), (63, 38), (71, 46), (84, 59), (92, 35), (60, 24), (75, 38)]]


def solve_column(s, m):
    st = s.cur["state"]
    p = ColumnProblem(st["a"], st["b"], Op(st["op"]))
    p.regrouped = st["regrouped"]
    if st["step"] == "ones":
        s.respond({"kind": "digit", "value": p.expected_ones()}, m, D0)
        p.regrouped = p.regrouped or p.needs_regroup
    return s.respond({"kind": "digit", "value": p.expected_tens()}, m, D0)


def run_perfect(s, m):
    types = []
    while s.cur["type"] != "summary":
        c = s.cur
        types.append(c["type"] if c["type"] != "column" else f"column:{c['mode']}")
        if c["type"] == "diagnostic_build":
            s.respond({"kind": "build", "tens": c["target"] // 10, "ones": c["target"] % 10}, m, D0)
        elif c["type"] == "diagnostic_fact":
            s.respond({"kind": "number", "value": 20}, m, D0)
        elif c["type"] in ("model", "handback", "teach_place_value"):
            s.respond({"kind": "continue"}, m, D0)
        elif c["type"] == "column":
            solve_column(s, m)
        elif c["type"] == "word_problem":
            s.respond({"kind": "number", "value": c["a"] - c["b"]}, m, D0)
        assert len(types) < 40
    return types


def test_new_child_full_session_order():
    m = LearnerModel()
    s = Session.start(CHILD, SHEET, m, D0)
    types = run_perfect(s, m)
    assert types == ["diagnostic_build", "diagnostic_build", "diagnostic_fact", "model", "column:completion",
                     "column:practice", "column:practice", "column:practice", "column:practice", "column:practice",
                     "word_problem", "column:check"]
    assert m.state("sub_regroup", D0) == State.INDEPENDENT
    assert m.state("place_value_100", D0) == State.INDEPENDENT
    rep = s.report(m, D0)
    assert rep["word_problem"] == "solved first time"
    hw = rep["homework"]                     # every problem on the sheet was worked, none handed back to paper
    assert hw["total"] == 7 and len(hw["alone"]) == 5 and hw["saved_for_next_time"] == []
    assert hw["with_help"] == ["63−38"] and hw["watched"] == ["52−27"]
    assert rep["checks"] == [{"skill": "2-digit subtraction with regrouping", "passed": True}]


def test_independent_child_skips_teaching_next_day():
    m = LearnerModel()
    run_perfect(Session.start(CHILD, SHEET, m, D0), m)
    s2 = Session.start(CHILD, SHEET, m, date(2026, 10, 25))
    assert s2.cur["type"] == "column" and s2.cur["mode"] == "practice"


def test_failed_place_value_inserts_teaching():
    m = LearnerModel()
    s = Session.start(CHILD, SHEET, m, D0)
    s.respond({"kind": "build", "tens": 3, "ones": 4}, m, D0)
    s.respond({"kind": "build", "tens": 3, "ones": 4}, m, D0)
    assert s.cur["type"] == "teach_place_value"
    s.respond({"kind": "continue"}, m, D0)
    assert s.cur["type"] == "diagnostic_build" and s.cur["target"] == 56


def go_to_first_practice(s, m):
    while not (s.cur["type"] == "column" and s.cur["mode"] == "practice"):
        c = s.cur
        if c["type"] == "diagnostic_build":
            s.respond({"kind": "build", "tens": c["target"] // 10, "ones": c["target"] % 10}, m, D0)
        elif c["type"] == "diagnostic_fact":
            s.respond({"kind": "number", "value": 20}, m, D0)
        elif c["type"] == "model":
            s.respond({"kind": "continue"}, m, D0)
        else:
            solve_column(s, m)


def test_bug_feedback_and_auto_help_capped_at_4():
    m = LearnerModel()
    s = Session.start(CHILD, SHEET, m, D0)
    go_to_first_practice(s, m)                     # 71 - 46
    r = s.respond({"kind": "digit", "value": 9}, m, D0)
    assert r["feedback"]["tone"] == "hint"
    for _ in range(6):
        s.respond({"kind": "digit", "value": 9}, m, D0)
    assert s.cur["help"] == 4                       # never auto-escalates to worked example or reveal


def test_heavy_help_adds_fresh_item():
    m = LearnerModel()
    s = Session.start(CHILD, SHEET, m, D0)
    go_to_first_practice(s, m)
    for _ in range(6):
        s.respond({"kind": "help"}, m, D0)
    assert s.cur["help"] == 6
    solve_column(s, m)
    assert s.cur["type"] == "column" and s.cur["mode"] == "extra"


def test_two_stuck_signals_offer_break_and_resume():
    m = LearnerModel()
    s = Session.start(CHILD, SHEET, m, D0)
    go_to_first_practice(s, m)
    s.respond({"kind": "stuck"}, m, D0)
    r = s.respond({"kind": "stuck"}, m, D0)
    assert r["feedback"]["offer_break"]
    s.respond({"kind": "break"}, m, D0)
    assert s.cur["type"] == "pause"
    s.respond({"kind": "continue"}, m, D0)
    assert s.cur["type"] == "column"


def test_view_hides_expected_answers():
    m = LearnerModel()
    s = Session.start(CHILD, SHEET, m, D0)
    go_to_first_practice(s, m)
    v = s.view()
    assert "expected" not in str(v) and v["problem"]["a"] == 71


# ---------- every homework problem is learned, not just handed back ----------
def advance_to(s, m, pred, limit=60):
    for _ in range(limit):
        c = s.cur
        if pred(c):
            return c
        if c["type"] == "diagnostic_build":
            s.respond({"kind": "build", "tens": c["target"] // 10, "ones": c["target"] % 10}, m, D0)
        elif c["type"] == "diagnostic_fact":
            s.respond({"kind": "number", "value": 20}, m, D0)
        elif c["type"] in ("model", "handback", "teach_place_value"):
            s.respond({"kind": "continue"}, m, D0)
        elif c["type"] == "column":
            solve_column(s, m)
        elif c["type"] == "word_problem":
            s.respond({"kind": "number", "value": c["a"] - c["b"]}, m, D0)
    raise AssertionError("never reached")


def test_struggled_problem_comes_back_once():
    m = LearnerModel()
    s = Session.start(CHILD, SHEET[:4], m, D0)
    advance_to(s, m, lambda c: c["type"] == "column" and c["mode"] == "practice")
    item = (s.cur["a"], s.cur["b"])
    s.respond({"kind": "digit", "value": 0}, m, D0)          # wrong ones digit
    s.respond({"kind": "help"}, m, D0)
    s.respond({"kind": "help"}, m, D0)
    solve_column(s, m)
    retry = advance_to(s, m, lambda c: c["type"] == "column" and c["mode"] == "retry")
    assert (retry["a"], retry["b"]) == item
    solve_column(s, m)                                         # solved alone this time
    types = [a["mode"] for a in s.d["queue"] if a["type"] == "column"]
    assert "retry" not in types                                # never loops


def test_failed_check_reteaches_with_fresh_items():
    m = LearnerModel()
    s = Session.start(CHILD, SHEET[:3], m, D0)
    chk = advance_to(s, m, lambda c: c["type"] == "column" and c["mode"] == "check")
    first = (chk["a"], chk["b"])
    assert first not in {(w["a"], w["b"]) for w in SHEET}      # fresh, not from the homework
    s.respond({"kind": "digit", "value": 0}, m, D0)            # wrong
    solve_column(s, m)
    assert s.cur["type"] == "model" and (s.cur["a"], s.cur["b"]) != first
    chk2 = advance_to(s, m, lambda c: c["type"] == "column" and c["mode"] == "check")
    assert (chk2["a"], chk2["b"]) not in {first}
    solve_column(s, m)
    advance_to(s, m, lambda c: c["type"] == "summary")
    rep = s.report(m, D0)
    assert rep["checks"][0]["passed"] is True


def test_mixed_homework_teaches_every_skill_easiest_first():
    sheet = [{"a": 52, "b": 27, "op": "-"}, {"a": 23, "b": 14, "op": "+"}, {"a": 45, "b": 31, "op": "-"},
             {"a": 38, "b": 47, "op": "+"}]
    m = LearnerModel()
    s = Session.start(CHILD, sheet, m, D0)
    assert s.d["skills"] == ["add_no_carry", "sub_no_regroup", "add_carry", "sub_regroup"]
    models = []
    while s.cur["type"] != "summary":
        if s.cur["type"] == "model":
            models.append((s.cur["a"], s.cur["b"], s.cur["op"]))
        c = s.cur
        if c["type"] == "diagnostic_build":
            s.respond({"kind": "build", "tens": c["target"] // 10, "ones": c["target"] % 10}, m, D0)
        elif c["type"] == "diagnostic_fact":
            s.respond({"kind": "number", "value": 20 if c["op"] == "-" else 50}, m, D0)
        elif c["type"] in ("model", "handback", "teach_place_value"):
            s.respond({"kind": "continue"}, m, D0)
        elif c["type"] == "column":
            solve_column(s, m)
        elif c["type"] == "word_problem":
            s.respond({"kind": "number", "value": c["a"] + c["b"] if c["op"] == "+" else c["a"] - c["b"]}, m, D0)
    assert models == [(23, 14, "+"), (45, 31, "-"), (38, 47, "+"), (52, 27, "-")]
    rep = s.report(m, D0)
    assert len(rep["skills"]) == 4 and len(rep["checks"]) == 4


def test_time_cap_saves_remaining_problems_for_next_time(monkeypatch):
    m = LearnerModel()
    s = Session.start(CHILD, SHEET, m, D0)
    advance_to(s, m, lambda c: c["type"] == "column" and c["mode"] == "practice")
    s.d["started"] -= 60 * 60                                   # an hour has passed
    solve_column(s, m)
    assert s.cur["type"] == "handback" and len(s.cur["items"]) == 4
    saved = [f"{i['a']}−{i['b']}" for i in s.cur["items"]]
    s.respond({"kind": "continue"}, m, D0)
    assert s.cur["type"] == "summary"
    assert s.report(m, D0)["homework"]["saved_for_next_time"] == saved
