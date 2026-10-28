"""MedTwin background worker: processes the durable job queue.

    python -m app.worker            run until stopped (Ctrl+C / SIGTERM)
    python -m app.worker --drain    process every queued job, then exit
    python -m app.worker --once     process at most one job, then exit

Run from the backend directory with the same environment as the API
(DATABASE_URL, UPLOAD_DIR, storage-encryption keys). Several workers may share
one queue; GPU jobs are limited by MEDTWIN_GPU_SLOTS.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time

logger = logging.getLogger("medtwin.worker")


def main(argv: list[str] | None = None) -> int:
    stopping = False

    def stop(_signum, _frame):
        nonlocal stopping
        stopping = True
        logger.info("stop requested; finishing the current job")

    # Installed before the model stack is imported and migrations run (several seconds): a
    # container stopped during start-up must still exit cleanly, and as PID 1 the process
    # would otherwise ignore SIGTERM until then.
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true")
    mode.add_argument("--drain", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    parser.add_argument("--kinds", help="Comma-separated job kinds to accept (default: all).")
    parser.add_argument("--worker-id", default=None)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    kinds = [kind.strip() for kind in args.kinds.split(",")] if args.kinds else None

    from app.database import Base, SessionLocal, engine
    from app.migrations import run_migrations
    from app.services import job_handlers  # noqa: F401 - registers handlers
    from app.services import job_queue, upload_store

    worker_id = args.worker_id or job_queue.default_worker_id()
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    removed = upload_store.startup_cleanup()
    logger.info("worker %s started (kinds=%s, stale plaintext entries removed=%d)", worker_id, kinds or "all", removed)

    processed = 0
    while not stopping:
        with SessionLocal() as db:
            job = job_queue.process_next(db, worker_id, kinds)
        if job is not None:
            processed += 1
            logger.info("job %s %s -> %s%s", job.id, job.kind, job.status, f" ({job.last_error})" if job.last_error else "")
            if args.once:
                break
            continue
        if args.once or args.drain:
            break
        time.sleep(args.poll_seconds)
    logger.info("worker %s exiting after %d job(s)", worker_id, processed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
