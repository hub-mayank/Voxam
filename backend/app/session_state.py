"""Viva session state machine. Pure: no framework, no database, no clock."""
from enum import Enum


class SessionStatus(str, Enum):
    created = "created"
    consented = "consented"
    in_progress = "in_progress"
    ended = "ended"
    scoring = "scoring"
    scored = "scored"
    abandoned = "abandoned"
    failed = "failed"


class Event(str, Enum):
    consent = "consent"
    start = "start"
    end = "end"
    begin_scoring = "begin_scoring"
    scored = "scored"
    fail = "fail"
    abandon = "abandon"


S, E = SessionStatus, Event

TRANSITIONS = {
    (S.created, E.consent): S.consented,
    (S.consented, E.start): S.in_progress,
    (S.in_progress, E.end): S.ended,
    (S.ended, E.begin_scoring): S.scoring,
    (S.scoring, E.scored): S.scored,
    (S.scoring, E.fail): S.failed,
    (S.failed, E.begin_scoring): S.scoring,  # faculty or worker retries a failed job
    (S.created, E.abandon): S.abandoned,
    (S.consented, E.abandon): S.abandoned,
    (S.in_progress, E.abandon): S.abandoned,
}

# the student may rejoin (new token, old one dies) only in these states; after that the access code is dead
REJOIN_OK = frozenset({S.created, S.consented, S.in_progress})
TERMINAL = frozenset({S.scored, S.abandoned})


class InvalidTransition(ValueError):
    def __init__(self, status, event):
        super().__init__(f"cannot {Event(event).value} a session that is {SessionStatus(status).value}")
        self.status, self.event = SessionStatus(status), Event(event)


def transition(status, event) -> SessionStatus:
    """Next status, or InvalidTransition."""
    key = (SessionStatus(status), Event(event))
    if key not in TRANSITIONS:
        raise InvalidTransition(*key)
    return TRANSITIONS[key]


def can_rejoin(status) -> bool:
    return SessionStatus(status) in REJOIN_OK
