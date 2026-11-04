"""Runs analyses in the background so uploads return immediately (the UI polls for progress).

thread: in-process worker pool (local dev, a single always-on container).
sync:   run inside the request (tests).
On Modal we will swap this for `run_analysis.spawn(...)` on a separate function.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .config import settings
from .pipeline import run_analysis

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="analysis")


def submit(analysis_id: str) -> None:
    if settings.job_mode == "sync":
        run_analysis(analysis_id)
    else:
        _executor.submit(run_analysis, analysis_id)
