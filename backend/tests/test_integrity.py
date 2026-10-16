import pytest

from harness import RAO, begin, build, finish, join, make_viva, start


@pytest.fixture()
def env(tmp_path):
    app, client, clock = build(tmp_path)
    codes = make_viva(client, students=("S1", "S2"))
    return app, client, clock, codes


def report(client, sid, h, *events):
    return client.post(f"/student/sessions/{sid}/integrity", headers=h, json={"events": list(events)})


def stored(client, sid):
    return client.get(f"/faculty/sessions/{sid}", headers=RAO).json()["integrity_events"]


def test_signals_are_stored_with_the_server_clock_and_reach_faculty(env):
    app, client, clock, codes = env
    sid, h = begin(client, codes["S1"])
    clock.advance(42)
    r = report(client, sid, h, {"kind": "tab_hidden", "duration_ms": 9200, "client_id": "a1"}, {"kind": "paste", "chars": 312, "client_id": "a2"})
    assert r.status_code == 200 and r.json() == {"recorded": 2}
    events = stored(client, sid)
    assert [(e["kind"], e["t_ms"]) for e in events] == [("tab_hidden", 42_000), ("paste", 42_000)]
    assert events[0]["detail"] == {"duration_ms": 9200, "client_id": "a1"} and events[1]["detail"] == {"chars": 312, "client_id": "a2"}


def test_a_retry_with_the_same_client_id_is_stored_once(env):
    app, client, clock, codes = env
    sid, h = begin(client, codes["S1"])
    one = {"kind": "window_blur", "duration_ms": 5000, "client_id": "same"}
    assert report(client, sid, h, one).json() == {"recorded": 1}
    assert report(client, sid, h, one).json() == {"recorded": 0}
    assert len(stored(client, sid)) == 1


def test_nothing_is_stored_before_the_start_or_after_the_end(env):
    app, client, clock, codes = env
    sid, h, _ = join(client, codes["S1"])
    assert report(client, sid, h, {"kind": "paste", "chars": 1}).json() == {"recorded": 0}
    start(client, sid, h)
    assert report(client, sid, h, {"kind": "paste", "chars": 1}).json() == {"recorded": 1}
    finish(client, clock, sid, h)
    assert report(client, sid, h, {"kind": "paste", "chars": 1}).json() == {"recorded": 0}
    assert len(stored(client, sid)) == 1


def test_only_known_kinds_and_never_the_text_itself(env):
    app, client, clock, codes = env
    sid, h = begin(client, codes["S1"])
    for bad in ({"kind": "keylog"}, {"kind": "paste", "text": "my secret answer"}, {"kind": "paste", "chars": -1}, {"kind": "tab_hidden", "duration_ms": 10**9}):
        assert report(client, sid, h, bad).status_code == 422, bad
    assert client.post(f"/student/sessions/{sid}/integrity", headers=h, json={"events": []}).status_code == 422
    assert stored(client, sid) == []


def test_a_page_that_floods_signals_stops_at_the_limit(env):
    app, client, clock, codes = env
    sid, h = begin(client, codes["S1"])
    sent = 0
    while sent < 210:
        report(client, sid, h, *[{"kind": "window_blur", "duration_ms": 4000} for _ in range(10)])
        sent += 10
    assert len(stored(client, sid)) == 200


def test_a_student_cannot_report_for_someone_elses_session(env):
    app, client, clock, codes = env
    sid1, h1 = begin(client, codes["S1"])
    sid2, h2 = begin(client, codes["S2"], student_id="S2")
    r = report(client, sid1, h2, {"kind": "paste", "chars": 1})
    assert r.status_code in (403, 404)
    assert stored(client, sid1) == []


def test_signals_do_not_change_the_mark_inputs(env):
    """The scorer reads turns only; integrity rows are not part of what it is given."""
    import inspect
    from app import scorer
    assert "integrity" not in inspect.getsource(scorer).lower()
