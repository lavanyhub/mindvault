"""Background job queue for document ingestion.

UPGRADE (Phase 1.1): upload previously ran embedding + 5 LLM calls
synchronously inside the HTTP request — a 60-120s frozen tab on
llama3.1:8b. This moves that work to a background worker so the upload
request returns almost immediately.

Deliberately NOT Celery/Redis: this is a local-first, single-user app.
Requiring a message broker for one person uploading files occasionally
would be over-engineering. A ThreadPoolExecutor with an in-memory
registry is enough — the tradeoff is that job state doesn't survive a
server restart, which is acceptable here and worth being able to explain
in an interview.
"""

import uuid
import logging
import threading
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)
_jobs = {}
_lock = threading.Lock()


def create_job(document_id: int) -> str:
    job_id = uuid.uuid4().hex
    with _lock:
        _jobs[job_id] = {
            'job_id': job_id,
            'document_id': document_id,
            'status': 'queued',
            'stage': 'queued',
            'progress': 0,
            'error': None,
        }
    return job_id


def update_job(job_id: str, **fields):
    with _lock:
        if job_id in _jobs:
            _jobs[job_id].update(fields)


def get_job(job_id: str) -> dict | None:
    with _lock:
        job = _jobs.get(job_id)
        return dict(job) if job else None


def submit(job_id: str, fn, *args, **kwargs):
    """Run fn(*args, **kwargs) in the background, tracking status on job_id."""
    def _run():
        update_job(job_id, status='running', stage='processing')
        try:
            fn(*args, **kwargs)
            update_job(job_id, status='complete', stage='complete', progress=100)
        except Exception as exc:
            logger.exception('Background job %s failed', job_id)
            update_job(job_id, status='error', error=str(exc))

    _executor.submit(_run)
