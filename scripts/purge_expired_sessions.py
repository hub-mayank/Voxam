#!/usr/bin/env python3
"""Preview or remove session data whose retention cutoff has passed.

Dry-run is the default. Apply mode deletes terminal session records and their
per-session recording from the configured AUDIO_DIR, plus the disposable
generated-speech cache. Copies outside those directories and provider-held
data remain an operator responsibility. Stop the API and worker before apply.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

from sqlalchemy import delete, select
from sqlalchemy.orm import sessionmaker

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.db import models as m  # noqa: E402
from app.db.engine import make_engine  # noqa: E402
from app.envfile import load_env  # noqa: E402

TERMINAL_STATUSES = ("ended", "scored", "failed", "abandoned")


def parse_cutoff(value: str) -> datetime:
    """Parse an ISO-8601 timestamp and require an explicit timezone."""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use an ISO-8601 timestamp, for example 2026-09-15T00:00:00Z") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("the cutoff must include a timezone, for example Z or +05:30")
    return parsed.astimezone(timezone.utc)


def audio_path(uri: str | None, root: Path) -> Path | None:
    """Resolve a local recording and reject paths outside AUDIO_DIR."""
    if not uri:
        return None
    parsed = urlparse(uri)
    if parsed.scheme == "file":
        path = Path(unquote(parsed.path)).resolve()
    elif parsed.scheme:
        raise ValueError("a session recording uses a non-local URI; remove it with its storage provider")
    else:
        path = Path(uri).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("a session recording is outside AUDIO_DIR; refusing to remove it") from exc
    if path == root:
        raise ValueError("a session recording points at AUDIO_DIR itself; refusing to remove it")
    return path


def candidates(db, cutoff: datetime):
    return list(db.scalars(
        select(m.Session)
        .where(m.Session.ended_at.is_not(None), m.Session.ended_at <= cutoff, m.Session.status.in_(TERMINAL_STATUSES))
        .order_by(m.Session.ended_at, m.Session.id)
    ).all())


def cache_files(cache_dir: Path) -> list[Path]:
    """The TTS cache is generated output; it can be rebuilt after removal."""
    if not cache_dir.is_dir():
        return []
    return [path for path in cache_dir.rglob("*") if path.is_file() and (path.suffix == ".wav" or path.suffix == ".tmp")]


def purge(db, sessions: list[m.Session], recordings: list[Path | None], cached_audio: list[Path]) -> tuple[int, int]:
    """Delete relational data atomically, then unlink local recordings and generated audio."""
    session_ids = [row.id for row in sessions]
    if session_ids:
        pairs = {(row.viva_id, row.student_id) for row in sessions}
        try:
            db.execute(delete(m.IntegrityEvent).where(m.IntegrityEvent.session_id.in_(session_ids)))
            db.execute(delete(m.Review).where(m.Review.session_id.in_(session_ids)))
            db.execute(delete(m.Override).where(m.Override.session_id.in_(session_ids)))
            db.execute(delete(m.Score).where(m.Score.session_id.in_(session_ids)))
            db.execute(delete(m.Turn).where(m.Turn.session_id.in_(session_ids)))
            db.execute(delete(m.Job).where(m.Job.session_id.in_(session_ids)))
            db.execute(delete(m.Session).where(m.Session.id.in_(session_ids)))
            for viva_id, student_id in pairs:
                db.execute(delete(m.AccessCode).where(m.AccessCode.viva_id == viva_id, m.AccessCode.student_id == student_id))
                db.execute(delete(m.RosterEntry).where(m.RosterEntry.viva_id == viva_id, m.RosterEntry.student_id == student_id))
            db.commit()
        except Exception:
            db.rollback()
            raise

    failures, removed = 0, 0
    for path in set(recordings + cached_audio):
        if path is None:
            continue
        try:
            if path.exists():
                path.unlink()
                removed += 1
        except OSError:
            failures += 1
            print("ERROR: database rows were removed but local audio cleanup failed; inspect AUDIO_DIR and TTS_CACHE.", file=sys.stderr)
    return failures, removed


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--before", required=True, type=parse_cutoff,
                        help="UTC or timezone-qualified end time; sessions ending at or before this time are eligible")
    parser.add_argument("--apply", action="store_true", help="delete eligible session data; without this flag, only preview")
    args = parser.parse_args(argv)

    load_env()
    audio_root = Path(os.environ.get("AUDIO_DIR", "audio")).resolve()
    cache_root = Path(os.environ.get("TTS_CACHE", str(audio_root / "tts_cache"))).resolve()
    if audio_root == Path(audio_root.anchor):
        parser.error("AUDIO_DIR cannot be a filesystem root")
    try:
        cache_root.relative_to(audio_root)
    except ValueError:
        parser.error("TTS_CACHE must be inside AUDIO_DIR so cache cleanup cannot reach unrelated files")
    if cache_root == audio_root:
        parser.error("TTS_CACHE must be a subdirectory of AUDIO_DIR, not AUDIO_DIR itself")
    engine = make_engine()
    factory = sessionmaker(engine)
    with factory() as db:
        expired = candidates(db, args.before)
        try:
            recordings = [audio_path(row.audio_uri, audio_root) for row in expired]
        except ValueError as exc:
            parser.error(str(exc))
        present = sum(1 for path in recordings if path is not None and path.is_file())
        cached_audio = cache_files(cache_root)
        mode = "APPLY" if args.apply else "DRY RUN"
        print(f"Mode: {mode}")
        print(f"Cutoff: {args.before.isoformat()}")
        print(f"Eligible terminal sessions: {len(expired)}")
        print(f"Per-session recordings present under AUDIO_DIR: {present}")
        print(f"Generated TTS cache files to clear: {len(cached_audio)}")
        if not args.apply:
            print("No data changed. Stop the API/worker, then re-run with --apply to remove this data.")
            return 0
        failures, removed = purge(db, expired, recordings, cached_audio)
        print(f"Database session records removed: {len(expired)}")
        print(f"Local audio/cache files removed: {removed}")
        return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
