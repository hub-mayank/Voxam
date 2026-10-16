from pathlib import Path

from app.clock import VivaClock
from app.config import load_bank, load_config
from app.interviewer import Interviewer
from app.llm.graceful import GracefulLLM
from app.llm.mock import MockLLM

ROOT = Path(__file__).resolve().parents[2]
CFG = load_config(ROOT / "config/viva.config.json")
BANK = load_bank(ROOT / "config/question_bank.sample.json")
LONG = " ".join(["word"] * 30)
ANSWERS = [LONG, "short answer", "I don't know", LONG, "let's talk about cricket", LONG, "no idea", "cricket again",
           LONG, LONG, "short", LONG, "I don't know", LONG, LONG, LONG, "hmm", LONG, LONG, LONG, LONG, LONG, LONG]


class Tick:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def spoken_turns(log):
    """What the service stores: spoken events only, the student's quality taken from the decision event after it."""
    turns = []
    for e in log:
        if e["role"] == "student":
            turns.append(dict(e, quality=None))
        elif e["role"] == "system" and "quality" in e and turns and turns[-1]["role"] == "student":
            turns[-1]["quality"] = e["quality"]
        elif e["role"] == "ai":
            turns.append(dict(e))
    return turns


def state(iv):
    return (iv.phase_name, iv.q["id"], iv.followups, iv.redirects, tuple(iv.asked), dict(iv.topic_points), iv.opener_answered)


def fresh(seed, at):
    tick = Tick()
    clock = VivaClock(CFG, now=tick)
    clock.start()
    tick.t = at
    return tick, Interviewer(MockLLM(), BANK, clock, CFG, seed=seed)


def test_restored_state_equals_live_state_at_every_step_and_the_next_reply_matches():
    for seed in (0, 7, "session-a"):
        tick, live = fresh(seed, 0)
        live.start()
        snapshots = [(0, 1, state(live))]  # (time, number of turns stored, state)
        for i, answer in enumerate(ANSWERS):
            tick.t = 30 * (i + 1)
            before = len(live.log)
            live.respond(answer)
            new = spoken_turns(live.log[before:])
            stored = spoken_turns(live.log)
            snapshots.append((tick.t, len(stored), state(live)))
            if live.log[-1]["action"] == "close":
                break
        stored = spoken_turns(live.log)
        for (t, count, expected), nxt in zip(snapshots, range(len(snapshots))):
            rebuilt_tick, rebuilt = fresh(seed, t)
            rebuilt.restore(stored[:count])
            assert state(rebuilt) == expected, (seed, t)
        # the reply to the next answer is the same whether the interviewer lived or was rebuilt
        for k in range(1, len(snapshots) - 1):
            t, count, _ = snapshots[k]
            nxt_t = snapshots[k + 1][0]
            _, rebuilt = fresh(seed, nxt_t)
            rebuilt.restore(stored[:count])
            rebuilt.respond(ANSWERS[k])
            got = [e for e in rebuilt.log if e["role"] == "ai"][-1]
            want = stored[snapshots[k + 1][1] - 1]
            assert (got["text"], got["action"], got["question_id"], got["phase"]) == \
                   (want["text"], want["action"], want["question_id"], want["phase"]), (seed, k)


def test_question_choice_depends_only_on_seed_and_history():
    picks = []
    for _ in range(2):
        tick, iv = fresh("same-seed", 0)
        iv.start()
        tick.t = 70
        iv.respond("hello")
        iv.respond(LONG)
        picks.append([e["question_id"] for e in iv.log if e.get("action") == "new_question"])
    assert picks[0] == picks[1]
    different = {tuple(fresh(s, 0)[1]._pick("fundamentals")["id"] for _ in [0]) for s in range(20)}
    assert len(different) > 1, "seed should change the choice"


def test_clock_resumes_from_a_persisted_start():
    from datetime import datetime, timedelta, timezone
    started = datetime(2026, 10, 12, 5, 30, tzinfo=timezone.utc)
    now = [started + timedelta(seconds=61)]
    clock = VivaClock.resume(CFG, started, lambda: now[0])
    assert clock.started and clock.phase().name == "fundamentals" and round(clock.remaining()) == 839
    now[0] = started + timedelta(seconds=900)
    assert clock.expired()


def test_graceful_llm_answers_when_every_provider_fails():
    class Down:
        name = "down"

        def complete_json(self, *a, **k):
            raise RuntimeError("503")

        def complete_text(self, *a, **k):
            raise RuntimeError("503")

    llm = GracefulLLM(Down())
    tick = Tick()
    clock = VivaClock(CFG, now=tick)
    iv = Interviewer(llm, BANK, clock, CFG)
    iv.start()
    tick.t = 70
    iv.respond("hello")
    reply = iv.respond(LONG)  # classification fails -> "partial" -> nudge -> phrasing fails -> canned
    assert reply and "partway" in reply
    assert llm.served is None and len(llm.errors) >= 2
    assert any(e.get("action") == "classify_error" for e in iv.log)


def test_the_cross_check_comes_once_at_the_start_of_depth_from_the_opener_and_is_rebuilt_from_stored_turns():
    for seed in (0, 7, "session-a"):
        tick, live = fresh(seed, 0)
        live.start()
        asked = []
        for i, answer in enumerate(ANSWERS):
            tick.t = 30 * (i + 1)
            before = len(live.log)
            live.respond(answer)
            asked += [e for e in live.log[before:] if e.get("action") == "cross_check"]
            if live.log[-1]["action"] == "close":
                break
        assert len(asked) == 1, "once per viva"
        assert asked[0]["phase"] == "depth" and asked[0]["question_id"] == "xcheck" and asked[0]["t"] >= 300
        assert asked[0]["text"] == "Going back to the project you described: why did you make that design choice?"
        _, rebuilt = fresh(seed, 330)
        rebuilt.restore(spoken_turns(live.log)[:next(i for i, e in enumerate(spoken_turns(live.log)) if e.get("action") == "cross_check") + 1])
        assert rebuilt.cross_checked and rebuilt.q["id"] == "xcheck" and rebuilt.q["text"] == asked[0]["text"]


def test_no_cross_check_when_the_opener_gave_nothing_to_come_back_to():
    tick, live = fresh(0, 0)
    live.start()
    live.respond("a project")  # two words: nothing specific
    for i in range(1, 12):
        tick.t = 30 * (i + 1)
        live.respond(LONG)
        if live.log[-1]["action"] == "close":
            break
    assert not any(e.get("action") == "cross_check" for e in live.log) and not live.cross_checked


def test_a_failed_model_falls_back_to_a_fixed_cross_check_line():
    from app.interviewer import FALLBACK_REPLIES

    class Down(MockLLM):
        def complete_text(self, *a, **k):
            raise RuntimeError("down")

    tick, live = fresh(0, 0)
    live.llm = GracefulLLM(Down())
    live.start()
    live.respond(LONG)
    tick.t = 300
    live.respond(LONG)
    got = [e for e in live.log if e.get("action") == "cross_check"]
    assert len(got) == 1 and got[0]["text"] == FALLBACK_REPLIES["cross_check"]
