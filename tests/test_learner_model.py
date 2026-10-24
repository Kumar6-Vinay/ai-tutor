from datetime import date, timedelta

from app.domain.learner_model import Evidence, Kind, LearnerModel, State

D0 = date(2026, 10, 24)


def ev(correct=True, help=0, kind=Kind.PRACTICE, day=D0, **kw):
    return Evidence("sub_regroup", kw.pop("item", "52-27"), correct, help, kind, day=day.isoformat(), **kw)


def test_two_independent_correct_in_a_day_makes_independent_and_schedules_review():
    m = LearnerModel()
    m.update(ev(item="a"), D0)
    assert m.state("sub_regroup", D0) != State.INDEPENDENT
    m.update(ev(item="b"), D0)
    assert m.state("sub_regroup", D0) == State.INDEPENDENT
    assert m.skills["sub_regroup"].next_review == (D0 + timedelta(days=2)).isoformat()


def test_heavy_help_gives_no_mastery_credit():
    m = LearnerModel()
    p0 = m.p_known("sub_regroup")
    m.update(ev(help=5), D0)
    assert m.p_known("sub_regroup", D0) == p0
    assert m.state("sub_regroup", D0) in (State.INTRODUCED, State.SUPPORTED)


def test_low_confidence_speech_is_ignored():
    m = LearnerModel()
    p0 = m.p_known("sub_regroup")
    m.update(ev(input_mode="voice", asr_confidence=0.5), D0)
    assert m.p_known("sub_regroup", D0) == p0


def test_fast_correct_answers_count_less():
    slow, fast = LearnerModel(), LearnerModel()
    slow.update(ev(ms=8000), D0)
    fast.update(ev(ms=500), D0)
    assert fast.p_known("sub_regroup", D0) < slow.p_known("sub_regroup", D0)


def test_secure_needs_two_days_transfer_and_representation():
    m = LearnerModel()
    for d in (D0, D0 + timedelta(days=2)):
        m.update(ev(item="a", day=d), d)
        m.update(ev(item="b", day=d), d)
    assert m.state("sub_regroup", D0 + timedelta(days=2)) == State.INDEPENDENT
    d = D0 + timedelta(days=2)
    m.update(ev(kind=Kind.TRANSFER, day=d), d)
    m.update(ev(kind=Kind.REPRESENTATION, day=d), d)
    assert m.state("sub_regroup", d) == State.SECURE


def test_overdue_review_and_failed_review():
    m = LearnerModel()
    m.update(ev(item="a"), D0)
    m.update(ev(item="b"), D0)
    later = D0 + timedelta(days=5)
    assert m.state("sub_regroup", later) == State.DUE_FOR_REVIEW
    assert "sub_regroup" in m.due_reviews(later)
    m.update(ev(correct=False, kind=Kind.REVIEW, day=later), later)
    assert m.state("sub_regroup", later) == State.SUPPORTED


def test_misconception_needs_two_items_and_expires():
    m = LearnerModel()
    m.record_bug("sub_regroup", "smaller_from_larger", "81-37", D0)
    assert m.active_misconceptions(D0)[0]["confirmed"] is False
    m.record_bug("sub_regroup", "smaller_from_larger", "62-28", D0)
    assert m.active_misconceptions(D0)[0]["confirmed"] is True
    assert m.active_misconceptions(D0 + timedelta(days=31)) == []
    assert m.dismiss_misconception("sub_regroup", "smaller_from_larger")
    assert m.active_misconceptions(D0) == []


def test_round_trip_serialisation():
    m = LearnerModel()
    m.update(ev(), D0)
    m2 = LearnerModel(m.to_dict())
    assert m2.state("sub_regroup", D0) == m.state("sub_regroup", D0)
