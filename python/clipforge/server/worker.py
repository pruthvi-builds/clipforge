"""Background worker loop.

Run with:  python -m clipforge.server.worker   (or `npm run worker`)

Polls the ``jobs`` table, claims one job at a time (SQLite row lock via the
``processing`` state) and executes it. A single process with concurrency 1 keeps
CPU/GPU pressure predictable; set CLIPFORGE_WORKER_CONCURRENCY>1 to run more
worker processes.
"""

from __future__ import annotations

import os
import signal
import sys
import time

from ..config import get_settings
from ..db import claim_next_job, init_db, requeue_stale_jobs
from ..logging_setup import get_logger, setup_logging
from .jobs import run_job

log = get_logger("clipforge.worker")

_STOP = False


def _handle_sig(signum, _frame):
    global _STOP
    _STOP = True
    log.info("received signal %s, finishing current job then exiting", signum)


def main() -> int:
    setup_logging(os.environ.get("CLIPFORGE_LOG_LEVEL", "INFO"))
    signal.signal(signal.SIGINT, _handle_sig)
    signal.signal(signal.SIGTERM, _handle_sig)

    s = get_settings()
    init_db()
    n = requeue_stale_jobs()
    if n:
        log.info("re-queued %d stale job(s) from a previous run", n)

    log.info("worker up. data_dir=%s db=%s  (poll 1s)", s.data_dir, s.db_path)
    idle_logged = False
    while not _STOP:
        job = claim_next_job()
        if not job:
            if not idle_logged:
                log.debug("idle — waiting for jobs")
                idle_logged = True
            time.sleep(1.0)
            continue
        idle_logged = False
        log.info("claimed job %s kind=%s project=%s", job["id"], job["kind"], job["project_id"])
        t0 = time.time()
        run_job(job)
        log.info("job %s done in %.1fs", job["id"], time.time() - t0)

    log.info("worker stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
