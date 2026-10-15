"""T8 robustness table: what happens when the network drops, the student rejoins, the microphone is muted or silent, the student
talks over the AI, a worker dies, or every model is down. Each row names the executable test that proves it and records pass/fail
from a real pytest run (junit xml). Providers are stub/mock: this proves OUR handling, not speech quality. Background noise through
a real microphone is NOT run here (needs a person and a room) and is listed as such.
Usage: python scripts/robustness.py [--out results/robustness_scenarios.csv]"""
import argparse
import csv
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.results_meta import write_meta  # noqa: E402

TESTS = "backend/tests"
SCENARIOS = [
    ("network drop in the middle of the viva, same tab reconnects", "the same question and time left return; the answer is not stored twice; the old socket is replaced",
     "test_voice_protocol.py::test_reconnect_resumes_without_duplicating_and_the_old_connection_is_replaced"),
    ("student rejoins from another tab or after a reload", "resumes the session with a new token; the old token stops working",
     "test_real_student.py::test_rejoin_mid_viva_resumes_with_a_new_token_and_kills_the_old_one"),
    ("same answer sent twice (retry after a timeout)", "the same reply is replayed and nothing is stored twice",
     "test_real_student.py::test_duplicate_client_seq_replays_the_same_reply_and_stores_nothing_twice"),
    ("two copies of the same answer arrive at once", "exactly one reply is produced",
     "test_real_student.py::test_concurrent_duplicates_produce_exactly_one_reply"),
    ("long silence", "one gentle prompt per question, not more",
     "test_voice_protocol.py::test_one_silence_prompt_per_question"),
    ("microphone muted or a click instead of speech", "no speech: nothing is stored and the student is not penalised",
     "test_voice_protocol.py::test_a_too_short_answer_is_no_speech_and_nothing_is_stored"),
    ("student talks over the AI", "the AI stops and listens",
     "test_voice_protocol.py::test_speaking_over_the_ai_is_an_interrupt"),
    ("a short noise while the AI talks", "not treated as a barge-in; real speech is",
     "test_voice_protocol.py::test_a_short_noise_while_the_ai_talks_is_not_a_barge_in_but_real_speech_is"),
    ("every language model is down", "a graceful canned reply; the answer is stored; the viva continues",
     "test_real_student.py::test_when_every_model_is_down_the_student_gets_a_graceful_reply_and_nothing_is_lost"),
    ("the server process is killed and restarted", "the viva continues from the database",
     "test_real_student.py::test_kill_and_restart_continues_the_session"),
    ("a worker dies holding the answer lease", "another worker takes over after the lease",
     "test_real_student.py::test_a_dead_workers_lease_expires_and_another_worker_takes_over"),
    ("the hard time limit passes", "the AI speaks the closing turn, the session ends and scoring is queued",
     "test_voice_protocol.py::test_hard_stop_speaks_the_closing_turn_ends_the_session_and_closes"),
    ("malformed or unknown messages on the socket", "ignored; the connection stays up",
     "test_voice_protocol.py::test_bad_json_and_unknown_messages_do_not_break_the_connection"),
]
NOT_RUN = [("background noise in a real room through a real microphone", "needs a person; see docs/qa/student-checklist.md rows 10-12"),
           ("slow or lossy real network", "not simulated; the reconnect path is tested, throughput is not")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "results" / "robustness_scenarios.csv"))
    a = ap.parse_args()
    with tempfile.TemporaryDirectory() as d:
        xml = Path(d) / "junit.xml"
        ids = [f"{TESTS}/{t}" for _, _, t in SCENARIOS]
        subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={xml}", *ids], cwd=ROOT,
                       capture_output=True, text=True)
        cases = {c.get("name"): c for c in ET.parse(xml).getroot().iter("testcase")}
    rows = []
    for scenario, expected, test in SCENARIOS:
        c = cases.get(test.split("::")[1])
        outcome = "not found" if c is None else "fail" if (c.find("failure") is not None or c.find("error") is not None) \
            else "skipped" if c.find("skipped") is not None else "pass"
        rows.append({"scenario": scenario, "expected": expected, "outcome": outcome, "test": test})
    for scenario, why in NOT_RUN:
        rows.append({"scenario": scenario, "expected": "", "outcome": "not run", "test": why})
    with open(a.out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    write_meta(a.out, provider="stub", model="stub voice + mock LLM behind the real server and database", n=len(SCENARIOS),
               n_unit="scenarios run", not_run=[s for s, _ in NOT_RUN],
               note="each outcome is a pytest result; proves our handling of the failure, not speech or model quality")
    for r in rows:
        print(f"{r['outcome']:8} {r['scenario']}")


if __name__ == "__main__":
    main()
