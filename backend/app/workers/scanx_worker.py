"""RQ worker entrypoint for ScanX.

Usage (from backend/ with venv):
  set REDIS_URL=redis://127.0.0.1:6379/0
  python -m app.workers.scanx_worker
"""

from __future__ import annotations

import logging
import sys

from redis import Redis
from rq import Worker

from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scanx_worker")


def main() -> int:
    redis_url = (settings.REDIS_URL or "").strip()
    if not redis_url:
        logger.error("REDIS_URL is required to run the ScanX RQ worker")
        return 1
    queue_name = (settings.SCANX_WORKER_QUEUE or "scanx").strip() or "scanx"
    try:
        from app.services.scanx_ocr import prewarm_ocr_engines

        logger.info("Pre-warming ScanX OCR engines…")
        prewarm_ocr_engines(include_fallback=True)
        logger.info("ScanX OCR pre-warm complete")
    except Exception:
        logger.exception("ScanX OCR pre-warm failed; first job may cold-start")
    conn = Redis.from_url(redis_url)
    logger.info("Starting ScanX worker on queue=%s", queue_name)
    worker = Worker([queue_name], connection=conn)
    worker.work(with_scheduler=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
