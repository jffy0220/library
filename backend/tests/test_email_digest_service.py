from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from backend.app.schemas.notifications import EmailDigestOption, NotificationType
from backend.app.services import email_digest


class DummyProvider:
    def __init__(self) -> None:
        self.messages = []

    def send_email(self, recipient: str, subject: str, html_body: str, text_body: str) -> None:
        self.messages.append(
            {
                "recipient": recipient,
                "subject": subject,
                "html_body": html_body,
                "text_body": text_body,
            }
        )

    def describe(self) -> str:  # pragma: no cover - compatibility shim
        return "dummy"


class FakeCursor:
    def __init__(self, *, fetchall_result=None):
        self.fetchall_result = list(fetchall_result or [])
        self.execute_calls = []

    def execute(self, query, params=None):
        self.execute_calls.append((" ".join(query.split()), params))

    def fetchall(self):
        return list(self.fetchall_result)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self, *cursors):
        self._cursors = list(cursors)
        self.cursor_calls = []

    def cursor(self, *args, **kwargs):
        self.cursor_calls.append((args, kwargs))
        if not self._cursors:
            raise AssertionError("No cursor configured")
        return self._cursors.pop(0)


def _build_row(notification_id: int, created_at: datetime) -> dict:
    return {
        "id": notification_id,
        "user_id": 42,
        "type": NotificationType.REPLY_TO_SNIPPET.value,
        "title": "New reply",
        "body": "A very long body that should be shortened for the digest output.",
        "snippet_id": 15,
        "comment_id": 9,
        "created_at": created_at,
        "email": "reader@example.com",
        "username": "reader",
    }


def test_send_email_digests_sends_and_marks_notifications(monkeypatch):
    now = datetime(2024, 6, 1, 12, tzinfo=timezone.utc)
    rows = [
        _build_row(1, now - timedelta(hours=12)),
        _build_row(2, now - timedelta(hours=1)),
    ]

    select_cursor = FakeCursor(fetchall_result=rows)
    update_cursor = FakeCursor()
    conn = FakeConnection(select_cursor, update_cursor)

    provider = DummyProvider()
    monkeypatch.setattr(email_digest, "_get_email_provider", lambda: provider)
    monkeypatch.setattr(
        email_digest,
        "EMAIL_CONFIG",
        SimpleNamespace(app_base_url="https://library.test", from_email="noreply@library.test"),
    )

    summary = email_digest.send_email_digests(
        EmailDigestOption.DAILY,
        now=now,
        conn=conn,
    )

    assert summary.digests_sent == 1
    assert summary.notifications_delivered == 2
    assert summary.failures == 0
    assert provider.messages
    message = provider.messages[0]
    assert message["recipient"] == "reader@example.com"
    assert "Daily" in message["subject"]
    assert "snippet/15" in message["html_body"]
    assert "#comment-9" in message["html_body"]

    assert update_cursor.execute_calls
    (_, params) = update_cursor.execute_calls[0]
    assert sorted(params[1]) == [1, 2]


def test_send_email_digests_handles_provider_failure(monkeypatch):
    now = datetime(2024, 7, 1, 8, tzinfo=timezone.utc)
    rows = [_build_row(10, now - timedelta(hours=2))]

    select_cursor = FakeCursor(fetchall_result=rows)
    conn = FakeConnection(select_cursor)

    class FailingProvider:
        def send_email(self, *args, **kwargs):
            raise RuntimeError("boom")

        def describe(self):  # pragma: no cover - compatibility shim
            return "failing"

    monkeypatch.setattr(email_digest, "_get_email_provider", lambda: FailingProvider())
    monkeypatch.setattr(
        email_digest,
        "EMAIL_CONFIG",
        SimpleNamespace(app_base_url="https://library.test", from_email="noreply@library.test"),
    )

    summary = email_digest.send_email_digests(
        EmailDigestOption.DAILY,
        now=now,
        conn=conn,
    )

    assert summary.digests_sent == 0
    assert summary.notifications_delivered == 0
    assert summary.failures == 1

    # Update cursor should never have been invoked because the send failed.
    assert len(conn.cursor_calls) == 1