"""Scheduler integration for email notification digests."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from threading import Event, Lock, Thread
from typing import Dict, Optional

from backend.app.schemas.notifications import EmailDigestOption
from backend.app.services.email_digest import DigestDispatchSummary, send_email_digests

logger = logging.getLogger(__name__)

_scheduler_lock = Lock()
_workers: Dict[str, "_DigestWorker"] = {}

_DIGEST_METRICS: Dict[str, Dict[str, object]] = {
    EmailDigestOption.DAILY.value: {
        "digests_sent": 0,
        "notifications_sent": 0,
        "failures": 0,
        "last_run_at": None,
        "last_success_at": None,
        "last_error": None,
    },
    EmailDigestOption.WEEKLY.value: {
        "digests_sent": 0,
        "notifications_sent": 0,
        "failures": 0,
        "last_run_at": None,
        "last_success_at": None,
        "last_error": None,
    },
}
_metrics_lock = Lock()


def _record_run_start(frequency: EmailDigestOption, started_at: datetime) -> None:
    with _metrics_lock:
        metrics = _DIGEST_METRICS[frequency.value]
        metrics["last_run_at"] = started_at


def _record_run_success(
    frequency: EmailDigestOption,
    completed_at: datetime,
    summary: DigestDispatchSummary,
) -> None:
    with _metrics_lock:
        metrics = _DIGEST_METRICS[frequency.value]
        metrics["digests_sent"] = int(metrics.get("digests_sent", 0)) + summary.digests_sent
        metrics["notifications_sent"] = int(metrics.get("notifications_sent", 0)) + summary.notifications_delivered
        metrics["failures"] = int(metrics.get("failures", 0)) + summary.failures
        metrics["last_success_at"] = completed_at
        metrics["last_error"] = None


def _record_run_failure(
    frequency: EmailDigestOption,
    failed_at: datetime,
    error: Exception,
    summary: Optional[DigestDispatchSummary] = None,
) -> None:
    with _metrics_lock:
        metrics = _DIGEST_METRICS[frequency.value]
        metrics["failures"] = int(metrics.get("failures", 0)) + 1
        metrics["last_error"] = f"{type(error).__name__}: {error}"
        metrics["last_success_at"] = metrics.get("last_success_at")
        if summary:
            metrics["digests_sent"] = int(metrics.get("digests_sent", 0)) + summary.digests_sent
            metrics["notifications_sent"] = int(metrics.get("notifications_sent", 0)) + summary.notifications_delivered


def run_digest_job(frequency: EmailDigestOption, *, now: Optional[datetime] = None) -> DigestDispatchSummary:
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)

    _record_run_start(frequency, current_time)
    summary: Optional[DigestDispatchSummary] = None
    try:
        summary = send_email_digests(frequency, now=current_time)
    except Exception as exc:  # pragma: no cover - defensive log path
        _record_run_failure(frequency, current_time, exc, summary)
        logger.exception(
            "Email digest job failed",
            extra={"frequency": frequency.value},
        )
        raise
    else:
        _record_run_success(frequency, current_time, summary)
        logger.info(
            "Email digest job completed",
            extra={
                "frequency": frequency.value,
                "digests_sent": summary.digests_sent,
                "notifications_sent": summary.notifications_delivered,
                "failures": summary.failures,
            },
        )
        return summary


class _DigestWorker(Thread):
    def __init__(self, frequency: EmailDigestOption, *, initial_delay: float, interval: float):
        super().__init__(daemon=True)
        self.frequency = frequency
        self._initial_delay = max(0.0, initial_delay)
        self._interval = max(1.0, interval)
        self._stop = Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:  # pragma: no cover - thread execution
        if self._stop.wait(self._initial_delay):
            return
        while not self._stop.is_set():
            try:
                run_digest_job(self.frequency)
            except Exception:
                # Errors are logged inside run_digest_job; continue schedule.
                pass
            if self._stop.wait(self._interval):
                break


def _seconds_until(hour: int, minute: int = 0, day_of_week: Optional[int] = None) -> float:
    now = datetime.now(timezone.utc)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if day_of_week is None:
        if target <= now:
            target += timedelta(days=1)
    else:
        days_ahead = (day_of_week - target.weekday()) % 7
        if days_ahead == 0 and target <= now:
            days_ahead = 7
        target += timedelta(days=days_ahead)
    return max((target - now).total_seconds(), 0.0)


def start_digest_scheduler() -> None:
    with _scheduler_lock:
        if _workers:
            return
        daily_delay = _seconds_until(9, 0)
        weekly_delay = _seconds_until(9, 30, day_of_week=0)
        daily_worker = _DigestWorker(
            EmailDigestOption.DAILY,
            initial_delay=daily_delay,
            interval=24 * 60 * 60,
        )
        weekly_worker = _DigestWorker(
            EmailDigestOption.WEEKLY,
            initial_delay=weekly_delay,
            interval=7 * 24 * 60 * 60,
        )
        _workers[EmailDigestOption.DAILY.value] = daily_worker
        _workers[EmailDigestOption.WEEKLY.value] = weekly_worker
        for worker in _workers.values():
            worker.start()
        logger.info(
            "Email digest scheduler started",
            extra={
                "daily_initial_delay_seconds": round(daily_delay, 2),
                "weekly_initial_delay_seconds": round(weekly_delay, 2),
            },
        )


def shutdown_digest_scheduler() -> None:
    with _scheduler_lock:
        workers = list(_workers.values())
        for worker in workers:
            worker.stop()
        for worker in workers:
            worker.join(timeout=1.0)
        _workers.clear()
        logger.info("Email digest scheduler stopped")


def get_digest_metrics() -> Dict[str, Dict[str, object]]:
    with _metrics_lock:
        snapshot: Dict[str, Dict[str, object]] = {}
        for key, value in _DIGEST_METRICS.items():
            snapshot[key] = {
                **value,
                "last_run_at": value["last_run_at"].isoformat() if value.get("last_run_at") else None,
                "last_success_at": value["last_success_at"].isoformat() if value.get("last_success_at") else None,
            }
        return snapshot


def _reset_metrics_for_testing() -> None:  # pragma: no cover - used in tests only
    with _metrics_lock:
        for metrics in _DIGEST_METRICS.values():
            metrics.update(
                {
                    "digests_sent": 0,
                    "notifications_sent": 0,
                    "failures": 0,
                    "last_run_at": None,
                    "last_success_at": None,
                    "last_error": None,
                }
            )


__all__ = [
    "start_digest_scheduler",
    "shutdown_digest_scheduler",
    "get_digest_metrics",
    "run_digest_job",
]