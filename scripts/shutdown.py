"""Attempt independent cleanup completely before reporting any resource failures."""

from __future__ import annotations

import threading
from collections.abc import Callable


def cleanup(*steps: tuple[str, Callable[[], object]]) -> None:
    failures = []
    for name, release in steps:
        try:
            release()
        except Exception as error:
            failures.append((name, error))
    if failures:
        details = "; ".join(f"{name}: {error}" for name, error in failures)
        raise RuntimeError(f"Shutdown cleanup failed ({details})") from failures[0][1]


def join_worker(worker: threading.Thread | None, timeout: float) -> None:
    if worker is not None and worker is not threading.current_thread():
        worker.join(timeout=timeout)
        if worker.is_alive():
            raise TimeoutError(f"Worker did not stop within {timeout:g} seconds")
