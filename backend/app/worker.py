"""The scoring worker: python -m app.worker [--once] [--poll 5] [--id NAME]

Each pass ends sessions whose deadline has passed (students who left; this is the background `sweep_expired` loop) and then scores every
due job. Several workers may run against one database: jobs are claimed with a compare-and-set, and a worker that dies mid-job
is replaced by the next one once the job's lease (5 minutes) runs out. Settings come from the same environment as the API:
DATABASE_URL, and SCORER_LLM_CHAIN (falls back to LLM_CHAIN, then mock)."""
import argparse
import logging
import os
import socket
import time
from datetime import datetime, timezone

from sqlalchemy.orm import sessionmaker

from .db.engine import init_db, make_engine
from .envfile import load_env
from .llm.factory import make_llm
from .services import core, scoring

log = logging.getLogger("aiviva.worker")


def run_pass(db, worker_id: str, now, llm_factory, chain=None, limit=1000) -> dict:
    """Sweep expired sessions, then score due jobs until none are left. -> counts per outcome (plus `swept`)."""
    counts = {"swept": core.sweep_expired(db, now())}
    for _ in range(limit):
        outcome = scoring.process_next(db, worker_id, now(), llm_factory, chain)
        if outcome is None:
            break
        counts[outcome] = counts.get(outcome, 0) + 1
        if outcome == "deferred":  # the provider's budget is used up, so every other job would be deferred too: try next pass
            break
    return counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="one pass, then exit")
    ap.add_argument("--poll", type=float, default=5.0, help="seconds between passes")
    ap.add_argument("--id", default=f"{socket.gethostname()}-{os.getpid()}")
    a = ap.parse_args()
    load_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    chain = os.environ.get("SCORER_LLM_CHAIN") or os.environ.get("LLM_CHAIN") or None
    engine = make_engine()
    init_db(engine)
    factory = sessionmaker(engine)
    now = lambda: datetime.now(timezone.utc)  # noqa: E731
    print(f"worker {a.id} started (scorer llm: {chain or 'mock'})")
    while True:
        with factory() as db:
            counts = run_pass(db, a.id, now, make_llm, chain)
        if any(v for k, v in counts.items()):
            print(f"pass: {counts}")
        if a.once:
            return
        time.sleep(a.poll)


if __name__ == "__main__":
    main()
