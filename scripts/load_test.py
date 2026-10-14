"""Load test for the voice viva: N simulated students against one server process on PostgreSQL, with modelled STT/TTS/LLM (stub).
The real code under test: HTTP API, WebSocket voice sessions, engine, database, recorder. Modelled (from measured files in results/):
speech recognition capacity and service time, speech synthesis time, the LLM's latency and a per-minute request budget (backend/app/loadmodel.py).
So it proves OUR orchestration at 10-150 sessions; it says nothing about vendor behaviour (D6). Every output row is labelled provider=stub.

  python scripts/load_test.py --levels 10 25 50 100 150 --out results/load/baseline_llm27rpm.csv
  python scripts/load_test.py --levels 50 --llm-rpm 0 --storm 20:30:0.8 --out results/load/storm.csv     # 429 storm

Each level: its own viva, bank and roster; every bot joins, consents, starts, connects and answers `--answers` times (push-to-talk, a
tone of `--answer-seconds`), one answer every `--cadence` seconds after a random start offset (a real viva is about one answer per
80 s, so 20 s is 4x as hard); `--burst` makes every bot answer at the same instant (worst case for the speech queue).
A level fails when a session is dropped, more than 1% of operations error, or p95 reply latency passes 4 s."""
import argparse
import asyncio
import csv
import json
import os
import random
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import websockets

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.results_meta import write_meta  # noqa: E402
from app.voice import audio  # noqa: E402

FACULTY = "load-token-0123456789"
P95_LIMIT_MS = 4000
ERROR_LIMIT = 0.01


def pct(values, p):
    v = sorted(values)
    return round(v[min(len(v) - 1, int(p * len(v)))], 1) if v else None


class Stats:
    def __init__(self):
        self.server_ms, self.client_ms, self.errors = [], [], {}
        self.sessions_ok = self.sessions_dropped = self.turns = self.operations = 0

    def error(self, kind: str):
        self.errors[kind] = self.errors.get(kind, 0) + 1


async def bot(i, args, base, ws_base, viva, student, code, stats: Stats, barrier=None):
    ops = lambda: setattr(stats, "operations", stats.operations + 1)  # noqa: E731
    async with httpx.AsyncClient(base_url=base, timeout=60) as http:
        ops()
        try:
            r = await http.post("/student/join", json={"viva_id": viva, "student_id": student, "access_code": code})
            if r.status_code != 200:
                stats.error(f"join_{r.json().get('error', {}).get('code', r.status_code)}")
                stats.sessions_dropped += 1
                return
            j = r.json()
            h = {"Authorization": f"Bearer {j['session_token']}"}
            sid = j["session_id"]
            for step, path, body in (("consent", f"/student/sessions/{sid}/consent", {"accepted": True, "rules_version": j["rules_version"]}),
                                     ("start", f"/student/sessions/{sid}/start", None)):
                ops()
                r = await http.post(path, headers=h, json=body) if body else await http.post(path, headers=h)
                if r.status_code != 200:
                    stats.error(f"{step}_{r.json().get('error', {}).get('code', r.status_code)}")
                    stats.sessions_dropped += 1
                    return
        except (httpx.HTTPError, ValueError) as e:
            stats.error(f"http_{type(e).__name__}")
            stats.sessions_dropped += 1
            return
    frame = audio.tone(args.frame_ms / 1000, 16000, freq=300, amp=0.5)
    n_frames = int(args.answer_seconds * 1000 / args.frame_ms)
    ops()
    try:
        async with websockets.connect(f"{ws_base}/student/sessions/{sid}/voice", max_size=None, ping_interval=None, open_timeout=30) as ws:
            await ws.send(json.dumps({"type": "hello", "protocol": 1, "token": j["session_token"], "mode": "push_to_talk", "resume": False}))

            async def until(kinds, timeout):
                """Read until one of `kinds`; returns that message. Records server errors."""
                end = time.perf_counter() + timeout
                while True:
                    left = end - time.perf_counter()
                    if left <= 0:
                        raise asyncio.TimeoutError
                    raw = await asyncio.wait_for(ws.recv(), left)
                    if isinstance(raw, bytes):
                        continue
                    m = json.loads(raw)
                    if m["type"] == "error":
                        stats.error(f"ws_{m['code']}")
                        if not m["retryable"]:
                            raise ConnectionError(m["code"])
                    if m["type"] in kinds:
                        return m

            await until({"ready"}, 30)
            await until({"state"}, 60)  # opener spoken, listening
            t0 = time.perf_counter()
            await asyncio.sleep(random.uniform(0, args.cadence) if not args.burst else 0)
            for k in range(args.answers):
                if barrier is not None:
                    await barrier[k].wait()
                else:
                    await asyncio.sleep(max(0, t0 + k * args.cadence - time.perf_counter()) if k else 0)
                ops()
                await ws.send(json.dumps({"type": "ptt_start"}))
                for _ in range(n_frames):
                    await ws.send(frame)
                    await asyncio.sleep(args.frame_ms / 1000)
                await ws.send(json.dumps({"type": "ptt_end"}))
                t_stop = time.perf_counter()
                first_audio = None
                try:
                    while True:
                        m = await until({"audio", "ai_turn", "ended"}, args.timeout)
                        if m["type"] == "audio" and first_audio is None:
                            first_audio = (time.perf_counter() - t_stop) * 1000
                        if m["type"] == "ai_turn":
                            stats.turns += 1
                            if m["latency_ms"] is not None:
                                stats.server_ms.append(m["latency_ms"])
                            if first_audio is not None:
                                stats.client_ms.append(first_audio)
                            break
                        if m["type"] == "ended":
                            break
                    await until({"state"}, args.timeout)
                except asyncio.TimeoutError:
                    stats.error("answer_timeout")
                    stats.sessions_dropped += 1
                    return
            stats.sessions_ok += 1
    except (websockets.ConnectionClosed, ConnectionError, OSError, asyncio.TimeoutError) as e:
        stats.error(f"ws_{type(e).__name__}")
        stats.sessions_dropped += 1


class Server:
    def __init__(self, args, db_url):
        self.args, self.db_url, self.proc, self.port = args, db_url, None, args.port
        self.audio_dir = tempfile.mkdtemp(prefix="load_audio_")

    def start(self):
        env = {**os.environ, "AI_VIVA_NO_DOTENV": "1", "FACULTY_TOKENS": f"load:{FACULTY}", "ACCESS_CODE_PEPPER": "load-pepper-0123456789",
               "AUDIO_SIGNING_SECRET": "load-audio-secret-0123", "DATABASE_URL": self.db_url, "VOICE_PROVIDER": "modelled", "LLM_CHAIN": "modelled",
               "AUDIO_DIR": self.audio_dir, "VOICE_TIMER_S": "5", "VOICE_SILENCE_S": "9999", "LOAD_LLM_RPM": str(self.args.llm_rpm),
               "LOAD_STT_MODEL": self.args.stt_model, "LOAD_TTS_PROCS": str(self.args.tts_procs), "TRUST_FORWARDED_FOR": "0",
               "IP_FAILURES_PER_MINUTE": "100000"}
        if self.args.stt_workers:
            env["LOAD_STT_WORKERS"] = str(self.args.stt_workers)
        if self.args.storm:
            env["LOAD_LLM_STORM"] = self.args.storm
        self.proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.api.main:app", "--port", str(self.port), "--log-level", "warning"],
                                     cwd=ROOT / "backend", env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(120):
            try:
                if httpx.get(f"http://localhost:{self.port}/health", timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.5)
        raise SystemExit("server did not start")

    def stop(self):
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=20)


def psql(db, sql):
    out = subprocess.run(["psql", "-At", "-d", db, "-c", sql], capture_output=True, text=True)
    return out.stdout.strip()


async def sample(pid, db, samples, stop):
    while not stop.is_set():
        out = subprocess.run(["ps", "-o", "%cpu=,rss=", "-p", str(pid)], capture_output=True, text=True).stdout.split()
        conns = psql(db, f"select count(*) from pg_stat_activity where datname='{db}'") if db else ""
        if out:
            samples.append((float(out[0]), int(out[1]) / 1024, int(conns) if conns.isdigit() else 0))
        await asyncio.sleep(1)


def setup_viva(base, name, students):
    h = {"Authorization": f"Bearer {FACULTY}"}
    c = httpx.Client(base_url=base, timeout=120)
    r = c.post("/faculty/vivas", headers=h, json={"viva_id": name, "title": f"load {name}", "subject": "load", "topics": ["load"], "difficulty": "medium"})
    assert r.status_code == 201, r.text
    bank = (ROOT / "config" / "question_bank.dsa.json").read_bytes()
    assert c.post(f"/faculty/vivas/{name}/questions", headers=h, files={"file": ("bank.json", bank, "application/json")}).status_code == 200
    assert c.post(f"/faculty/vivas/{name}/questions/approve", headers=h, json={}).status_code == 200
    csv_text = "student_id,name\n" + "".join(f"S{i:03d},Load {i}\n" for i in range(students))
    r = c.post(f"/faculty/vivas/{name}/roster", headers=h, files={"file": ("r.csv", csv_text.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    return {x["student_id"]: x["access_code"] for x in r.json()["items"]}


async def run_level(args, server, db, level):
    base, ws_base = f"http://localhost:{server.port}", f"ws://localhost:{server.port}"
    viva = f"load-{level}-{int(time.time())}"
    codes = await asyncio.to_thread(setup_viva, base, viva, level)
    stats, samples, stop = Stats(), [], asyncio.Event()
    barrier = [asyncio.Event() for _ in range(args.answers)] if args.burst else None
    sampler = asyncio.create_task(sample(server.proc.pid, db, samples, stop))
    t0 = time.perf_counter()
    tasks = [asyncio.create_task(bot(i, args, base, ws_base, viva, sid, code, stats, barrier)) for i, (sid, code) in enumerate(codes.items())]
    if barrier:
        for k in range(args.answers):
            await asyncio.sleep(args.cadence if k else 3)
            barrier[k].set()
    await asyncio.gather(*tasks)
    duration = time.perf_counter() - t0
    stop.set()
    await sampler
    degraded = psql(db, f"select count(*) from turns t join sessions s on s.id=t.session_id where s.viva_id='{viva}' and t.meta->>'llm_degraded'='true'") if db else ""
    nerr = sum(stats.errors.values())
    err_rate = nerr / max(1, stats.operations)
    row = {
        "level": level, "provider": "stub", "scenario": args.scenario, "llm_rpm": args.llm_rpm, "answers_per_session": args.answers,
        "cadence_s": args.cadence, "burst": args.burst, "sessions_ok": stats.sessions_ok, "sessions_dropped": stats.sessions_dropped,
        "turns": stats.turns, "answers_per_s": round(stats.turns / duration, 2), "latency_server_p50_ms": pct(stats.server_ms, 0.5),
        "latency_server_p95_ms": pct(stats.server_ms, 0.95), "latency_server_max_ms": pct(stats.server_ms, 1.0),
        "latency_client_p50_ms": pct(stats.client_ms, 0.5), "latency_client_p95_ms": pct(stats.client_ms, 0.95),
        "operations": stats.operations, "errors": nerr, "error_rate": round(err_rate, 4), "error_kinds": json.dumps(stats.errors, sort_keys=True),
        "llm_degraded_turns": int(degraded) if degraded.isdigit() else "", "server_cpu_mean_pct": round(statistics.mean(s[0] for s in samples), 1) if samples else "",
        "server_cpu_max_pct": max((s[0] for s in samples), default=""), "server_rss_max_mb": round(max((s[1] for s in samples), default=0)),
        "db_connections_max": max((s[2] for s in samples), default=""), "duration_s": round(duration),
    }
    p95 = row["latency_server_p95_ms"] or 0
    row["pass"] = stats.sessions_dropped == 0 and err_rate <= ERROR_LIMIT and p95 <= P95_LIMIT_MS
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", nargs="+", type=int, default=[10, 25, 50, 100, 150])
    ap.add_argument("--answers", type=int, default=4)
    ap.add_argument("--cadence", type=float, default=20.0, help="seconds between one student's answers")
    ap.add_argument("--answer-seconds", type=float, default=4.0)
    ap.add_argument("--frame-ms", type=int, default=60)
    ap.add_argument("--timeout", type=float, default=60.0, help="seconds to wait for a reply before the session counts as dropped")
    ap.add_argument("--burst", action="store_true", help="every student answers at the same instant")
    ap.add_argument("--llm-rpm", type=float, default=27, help="the LLM's requests per minute for the whole server (0 = unlimited)")
    ap.add_argument("--storm", default="", help="start_s:duration_s:failure_share, e.g. 20:30:0.8 (429s)")
    ap.add_argument("--stt-model", default="faster-whisper-base-int8")
    ap.add_argument("--stt-workers", type=int, default=0, help="0 = the measured plateau (8)")
    ap.add_argument("--tts-procs", type=int, default=1)
    ap.add_argument("--scenario", default="baseline")
    ap.add_argument("--db", default="postgres", choices=["postgres", "sqlite"])
    ap.add_argument("--port", type=int, default=8020)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    db_name, db_url = "", f"sqlite:///{tempfile.mkdtemp(prefix='load_db_')}/load.db"
    if args.db == "postgres":
        db_name = f"ai_viva_load_{int(time.time())}"
        subprocess.run(["createdb", db_name], check=True)
        db_url = f"postgresql+psycopg://{os.environ.get('USER', 'postgres')}@localhost/{db_name}"
    server = Server(args, db_url)
    rows = []
    try:
        server.start()
        for level in args.levels:
            print(f"level {level} ...", flush=True)
            row = asyncio.run(run_level(args, server, db_name, level))
            rows.append(row)
            print(f"  ok={row['sessions_ok']} dropped={row['sessions_dropped']} turns={row['turns']} server p50/p95={row['latency_server_p50_ms']}/"
                  f"{row['latency_server_p95_ms']} ms errors={row['errors']} {row['error_kinds']} cpu max={row['server_cpu_max_pct']}% "
                  f"rss={row['server_rss_max_mb']} MB db conns={row['db_connections_max']} -> {'PASS' if row['pass'] else 'FAIL'}", flush=True)
    finally:
        server.stop()
        if db_name:
            subprocess.run(["dropdb", "--if-exists", db_name])
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    first_fail = next((r for r in rows if not r["pass"]), None)
    write_meta(out, provider="stub", model="modelled stt/tts/llm (app/loadmodel.py) behind the real server", n=sum(r["sessions_ok"] + r["sessions_dropped"] for r in rows),
               n_unit="sessions", database=args.db, levels=args.levels, scenario=args.scenario, llm_rpm=args.llm_rpm, storm=args.storm, burst=args.burst,
               stt_model=args.stt_model, stt_workers=args.stt_workers or "measured plateau", tts_procs=args.tts_procs,
               breaking_level=first_fail["level"] if first_fail else None, server="one uvicorn process, harness on the same machine",
               note="modelled providers: proves orchestration (API, WebSocket, engine, database, recorder), not vendor capacity (D6)")
    print("breaking point:", f"level {first_fail['level']} ({first_fail['error_kinds']}; p95 {first_fail['latency_server_p95_ms']} ms)" if first_fail else "none up to level " + str(rows[-1]["level"]))


if __name__ == "__main__":
    main()
