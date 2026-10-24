import pytest

from app.domain.maths_engine import Bug, ColumnProblem, Op, Step, check_whole_answer


def test_subtraction_with_regroup_correct_path():
    p = ColumnProblem(52, 27, Op.SUB)
    assert p.needs_regroup
    assert p.regroup().correct
    assert p.enter(5).correct and p.step == Step.TENS
    assert p.enter(2).correct and p.step == Step.DONE


def test_mental_regroup_is_accepted():
    p = ColumnProblem(81, 37, Op.SUB)
    assert p.enter(4).correct and p.regrouped
    assert p.enter(4).correct


def test_smaller_from_larger_detected_at_ones():
    r = ColumnProblem(81, 37, Op.SUB).enter(6)     # 7 - 1
    assert not r.correct and r.bug == Bug.SMALLER_FROM_LARGER


def test_no_decrement_detected_at_tens():
    p = ColumnProblem(81, 37, Op.SUB)
    p.regroup()
    assert p.enter(4).correct
    r = p.enter(5)          # 8 - 3, forgot the opened ten
    assert not r.correct and r.bug == Bug.NO_DECREMENT
    assert p.enter(4).correct


def test_52_minus_27_equals_35_is_flagged_ambiguous():
    # 12-7 and 7-2 both give 5, and both bugs then give 3 tens: the tutor must ask.
    p = ColumnProblem(52, 27, Op.SUB)
    assert p.enter(5).correct and p.ones_ambiguous
    assert p.enter(3).bug == Bug.AMBIGUOUS_REGROUP


def test_explicit_regroup_removes_ambiguity():
    p = ColumnProblem(52, 27, Op.SUB)
    p.regroup()
    p.enter(5)
    assert p.enter(3).bug == Bug.NO_DECREMENT


def test_unneeded_regroup():
    p = ColumnProblem(58, 31, Op.SUB)
    r = p.regroup()
    assert not r.correct and r.bug == Bug.UNNEEDED_REGROUP and not p.regrouped


def test_addition_carry_and_forgot_carry():
    p = ColumnProblem(38, 45, Op.ADD)
    assert p.enter(3).correct and p.regrouped
    assert p.enter(7).bug == Bug.NO_CARRY
    assert p.enter(8).correct and p.step == Step.DONE


def test_scope_validation():
    with pytest.raises(ValueError):
        ColumnProblem(27, 52, Op.SUB)
    with pytest.raises(ValueError):
        ColumnProblem(68, 45, Op.ADD)


def test_view_never_contains_answers():
    v = ColumnProblem(52, 27, Op.SUB).to_view()
    assert "answer" not in v and 25 not in v.values()


def test_whole_answer_bugs():
    assert check_whole_answer(45, 18, Op.SUB, 27) == (True, None)
    assert check_whole_answer(45, 18, Op.SUB, 33) == (False, Bug.SMALLER_FROM_LARGER)
    assert check_whole_answer(45, 18, Op.SUB, 63) == (False, Bug.WRONG_OPERATION)
