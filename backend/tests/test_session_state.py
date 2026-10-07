import itertools

import pytest

from app.session_state import Event, InvalidTransition, SessionStatus, TRANSITIONS, can_rejoin, transition

HAPPY_PATH = [
    (SessionStatus.created, Event.consent, SessionStatus.consented),
    (SessionStatus.consented, Event.start, SessionStatus.in_progress),
    (SessionStatus.in_progress, Event.end, SessionStatus.ended),
    (SessionStatus.ended, Event.begin_scoring, SessionStatus.scoring),
    (SessionStatus.scoring, Event.scored, SessionStatus.scored),
]


@pytest.mark.parametrize("status,event,expected", HAPPY_PATH)
def test_happy_path(status, event, expected):
    assert transition(status, event) == expected


def test_full_path_from_created_to_scored():
    status = SessionStatus.created
    for _, event, _ in HAPPY_PATH:
        status = transition(status, event)
    assert status == SessionStatus.scored


def test_scoring_failure_and_retry():
    assert transition("scoring", "fail") == SessionStatus.failed
    assert transition("failed", "begin_scoring") == SessionStatus.scoring


@pytest.mark.parametrize("status", ["created", "consented", "in_progress"])
def test_abandon_before_the_end(status):
    assert transition(status, "abandon") == SessionStatus.abandoned


def test_every_other_pair_is_rejected():
    for status, event in itertools.product(SessionStatus, Event):
        if (status, event) in TRANSITIONS:
            continue
        with pytest.raises(InvalidTransition):
            transition(status, event)


def test_cannot_skip_consent_or_restart():
    with pytest.raises(InvalidTransition):
        transition("created", "start")
    with pytest.raises(InvalidTransition):
        transition("in_progress", "start")
    with pytest.raises(InvalidTransition):
        transition("scored", "begin_scoring")


def test_terminal_states_have_no_exit():
    for status in (SessionStatus.scored, SessionStatus.abandoned):
        assert not [k for k in TRANSITIONS if k[0] == status]


def test_unknown_status_or_event_is_a_value_error():
    with pytest.raises(ValueError):
        transition("nope", "start")
    with pytest.raises(ValueError):
        transition("created", "nope")


def test_rejoin_only_while_the_session_can_still_be_taken():
    ok = {s for s in SessionStatus if can_rejoin(s)}
    assert ok == {SessionStatus.created, SessionStatus.consented, SessionStatus.in_progress}
    assert not can_rejoin("ended") and not can_rejoin("scoring") and not can_rejoin("failed")
