from datetime import datetime, timezone

from backend import digests
from backend.app.schemas.notifications import EmailDigestOption
from backend.app.services.email_digest import DigestDispatchSummary


def test_run_digest_job_updates_metrics(monkeypatch):
    digests._reset_metrics_for_testing()

    summary = DigestDispatchSummary(digests_sent=3, notifications_delivered=5, failures=2)

    def fake_send(frequency, *, now=None):
        assert frequency == EmailDigestOption.DAILY
        return summary

    monkeypatch.setattr(digests, "send_email_digests", fake_send)

    run_time = datetime(2024, 8, 1, 9, tzinfo=timezone.utc)
    result = digests.run_digest_job(EmailDigestOption.DAILY, now=run_time)

    assert result == summary

    metrics = digests.get_digest_metrics()[EmailDigestOption.DAILY.value]
    assert metrics["digests_sent"] == summary.digests_sent
    assert metrics["notifications_sent"] == summary.notifications_delivered
    assert metrics["failures"] == summary.failures
    assert metrics["last_run_at"] == run_time.isoformat()
    assert metrics["last_success_at"] == run_time.isoformat()
    assert metrics["last_error"] is None