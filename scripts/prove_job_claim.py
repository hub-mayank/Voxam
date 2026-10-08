"""Prove the job queue never hands one job to two workers, with real OS processes.
Creates N sessions + jobs in a fresh schema (PostgreSQL) or file (SQLite), starts P worker processes that each loop
claim_next_job() -> a little pretend work -> complete_job(), then checks: every job claimed exactly once, none left over.
Usage: python scripts/prove_job_claim.py [--db URL] [--jobs 300] [--workers 4] [--work-ms 5] [--results results/job_claim_<db>.csv]
Default database: TEST_DATABASE_URL (shell or .env), else a temporary SQLite file."""
import argparse
import collections
import csv
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import sqlalchemy as sa  # noqa: E402
from sqlalchemy.orm import Session as Db  # noqa: E402

from app.db import models as m  # noqa: E402
from app.db.engine import init_db, make_engine, normalise_url  # noqa: E402
from app.services.jobs import claim_next_job, complete_job  # noqa: E402


def utc():
    return datetime.now(timezone.utc)


def worker(url, worker_id, out, work_ms):
    """Each claim is written to `out` the moment it happens (one line per job id), so a crash or a lost job cannot hide a double claim."""
    engine = make_engine(url)
    with Db(engine) as db, open(out, "a", buffering=1) as log:
        while True:
            job = claim_next_job(db, worker_id, utc())
            if job is None:
                break
            log.write(f"{job.id}\n")
            time.sleep(work_ms / 1000)
            if not complete_job(db, job.id, worker_id, utc()):
                log.write(f"lost {job.id}\n")


def seed(engine, n):
    init_db(engine)
    with Db(engine) as db:
        db.add(m.Viva(id="claim-proof", title="t", subject="s", topics=["a"], difficulty="easy", rules_version="rules-v1", config={}, created_by="proof"))
        db.commit()
        db.add_all([m.RosterEntry(viva_id="claim-proof", student_id=f"S{i}") for i in range(n)])
        db.commit()
        sessions = [m.Session(id=uuid.uuid4(), viva_id="claim-proof", student_id=f"S{i}", status="ended") for i in range(n)]
        db.add_all(sessions)
        db.commit()
        now = utc()
        db.add_all([m.Job(session_id=s.id, kind="score", status="queued", run_after=now) for s in sessions])
        db.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db")
    ap.add_argument("--jobs", type=int, default=300)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--work-ms", type=float, default=5)
    ap.add_argument("--results")
    ap.add_argument("--worker", metavar="ID", help="internal: run as a worker process")
    ap.add_argument("--out", help="internal: worker output file")
    a = ap.parse_args()
    if a.worker:
        return worker(a.db, a.worker, a.out, a.work_ms)
    from app.envfile import load_env, read_var
    load_env()
    url = normalise_url(a.db or os.environ.get("TEST_DATABASE_URL") or read_var("TEST_DATABASE_URL") or "")
    tmp = tempfile.TemporaryDirectory()
    if not url:
        url = f"sqlite:///{Path(tmp.name) / 'claim.db'}"
    schema, admin_url = None, url
    if url.startswith("postgresql"):
        schema = f"claim_proof_{os.getpid()}"
        admin = sa.create_engine(admin_url)
        with admin.begin() as c:
            c.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
        url = sa.engine.make_url(url).update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(hide_password=False)
    engine = make_engine(url)
    dialect = engine.dialect.name
    seed(engine, a.jobs)
    t = time.perf_counter()
    outs = [Path(tmp.name) / f"w{i}.json" for i in range(a.workers)]
    procs = [subprocess.Popen([sys.executable, __file__, "--worker", f"worker-{i}", "--db", url, "--out", str(outs[i]), "--work-ms", str(a.work_ms)])
             for i in range(a.workers)]
    codes = [p.wait() for p in procs]
    wall = time.perf_counter() - t
    lines = {f"worker-{i}": o.read_text().split() if o.exists() else [] for i, o in enumerate(outs)}
    claimed = {k: [int(x) for x in v if x != "lost"] for k, v in lines.items()}
    lost = sum(v.count("lost") for v in lines.values())
    all_ids = [j for ids in claimed.values() for j in ids]
    dupes = [j for j, c in collections.Counter(all_ids).items() if c > 1]
    with Db(engine) as db:
        status = collections.Counter(s for (s,) in db.execute(sa.select(m.Job.status)))
        attempts = collections.Counter(n for (n,) in db.execute(sa.select(m.Job.attempts)))
        version = db.execute(sa.text("select version()")).scalar().split(",")[0] if dialect == "postgresql" else f"SQLite {sa.__version__ and __import__('sqlite3').sqlite_version}"
    ok = not any(codes) and not dupes and not lost and len(all_ids) == a.jobs and status == {"done": a.jobs} and attempts == {1: a.jobs}
    summary = {"database": version, "dialect": dialect, "jobs": a.jobs, "workers": a.workers, "claims": len(all_ids), "duplicate_claims": len(dupes),
               "lost_jobs": lost, "per_worker": {k: len(v) for k, v in claimed.items()}, "final_status": dict(status), "attempts_histogram": dict(attempts),
               "wall_s": round(wall, 2), "ok": ok}
    if a.results:
        from app.results_meta import write_meta
        out = Path(a.results)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["worker", "jobs_claimed"])
            for k, v in sorted(claimed.items()):
                w.writerow([k, len(v)])
            w.writerow(["TOTAL", len(all_ids)])
            w.writerow(["duplicate_claims", len(dupes)])
            w.writerow(["jobs_never_claimed", a.jobs - len(set(all_ids))])
        write_meta(out, provider="live", model=version, n=a.jobs, n_unit="jobs claimed by competing OS processes", workers=a.workers, work_ms=a.work_ms,
                   wall_s=summary["wall_s"], dialect=dialect, note="a local database, not a provider; every job must be claimed exactly once")
    if schema:
        engine.dispose()
        with sa.create_engine(admin_url).begin() as c:
            c.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
    print(json.dumps(summary))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
