import importlib
import pathlib
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, List, Optional

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import backend.main as backend_main


@dataclass
class _TokenRow:
    user_id: int
    token_type: str
    token_hash: str
    email: Optional[str]
    expires_at: datetime


class _FakeTokenDatabase:
    def __init__(self) -> None:
        self._rows: List[_TokenRow] = []

    def connect(self):
        return _FakeConnection(self)

    def insert(self, row: _TokenRow) -> None:
        self._rows.append(row)

    def delete_expired(self, cutoff: datetime) -> int:
        before = len(self._rows)
        self._rows = [row for row in self._rows if row.expires_at > cutoff]
        return before - len(self._rows)

    def delete_for_user(self, user_id: int, token_type: str) -> int:
        before = len(self._rows)
        self._rows = [
            row
            for row in self._rows
            if not (row.user_id == user_id and row.token_type == token_type)
        ]
        return before - len(self._rows)

    def delete_exact(self, user_id: int, token_type: str, token_hash: str) -> int:
        before = len(self._rows)
        self._rows = [
            row
            for row in self._rows
            if not (
                row.user_id == user_id
                and row.token_type == token_type
                and row.token_hash == token_hash
            )
        ]
        return before - len(self._rows)

    def find(self, user_id: int, token_type: str) -> Optional[_TokenRow]:
        for row in self._rows:
            if row.user_id == user_id and row.token_type == token_type:
                return row
        return None


class _FakeCursor:
    def __init__(self, store: _FakeTokenDatabase) -> None:
        self._store = store
        self._result: Optional[List[Any]] = None
        self.rowcount: int = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass

    def execute(self, query: str, params: Optional[tuple] = None) -> None:
        sql = " ".join(query.strip().split())
        params = params or ()
        if sql.startswith("DELETE FROM user_tokens WHERE expires_at"):
            cutoff = params[0]
            self.rowcount = self._store.delete_expired(cutoff)
            self._result = None
            return
        if sql.startswith("DELETE FROM user_tokens WHERE user_id = %s AND token_type = %s AND token_hash = %s"):
            user_id, token_type, token_hash = params
            self.rowcount = self._store.delete_exact(user_id, token_type, token_hash)
            self._result = None
            return
        if sql.startswith("DELETE FROM user_tokens WHERE user_id = %s AND token_type = %s"):
            user_id, token_type = params
            self.rowcount = self._store.delete_for_user(user_id, token_type)
            self._result = None
            return
        if sql.startswith("INSERT INTO user_tokens"):
            user_id, token_type, token_hash, email, expires_at = params
            self._store.insert(
                _TokenRow(
                    user_id=user_id,
                    token_type=token_type,
                    token_hash=token_hash,
                    email=email,
                    expires_at=expires_at,
                )
            )
            self.rowcount = 1
            self._result = None
            return
        if sql.startswith("SELECT email, expires_at, token_hash FROM user_tokens"):
            user_id, token_type = params
            row = self._store.find(user_id, token_type)
            if row:
                self._result = [(row.email, row.expires_at, row.token_hash)]
                self.rowcount = 1
            else:
                self._result = []
                self.rowcount = 0
            return
        raise AssertionError(f"Unexpected query: {sql}")

    def fetchone(self):
        if not self._result:
            return None
        return self._result[0]


class _FakeConnection:
    def __init__(self, store: _FakeTokenDatabase) -> None:
        self._store = store
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        pass

    def cursor(self):
        return _FakeCursor(self._store)

    def commit(self) -> None:
        pass

    def rollback(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True


def _patch_db(monkeypatch, store: _FakeTokenDatabase):
    monkeypatch.setattr(backend_main, "get_conn", store.connect)


def test_issue_token_persists_between_requests(monkeypatch):
    store = _FakeTokenDatabase()
    _patch_db(monkeypatch, store)

    token, expires_at = backend_main.issue_onboarding_token(1, "user@example.com")

    assert token
    assert store.find(1, backend_main.TOKEN_TYPE_ONBOARDING) is not None
    assert expires_at > datetime.utcnow()

    # Issue a second token and ensure the previous one is replaced atomically.
    token2, expires_at2 = backend_main.issue_onboarding_token(1, "user@example.com")
    assert token2 != token
    row = store.find(1, backend_main.TOKEN_TYPE_ONBOARDING)
    assert row is not None
    assert row.token_hash == backend_main._hash_token(token2)
    assert row.expires_at == expires_at2


def test_validate_token_and_consume(monkeypatch):
    store = _FakeTokenDatabase()
    _patch_db(monkeypatch, store)

    token, expires_at = backend_main.issue_password_reset_token(5, "reset@example.com")
    result = backend_main.validate_password_reset_token(5, token)

    assert result is not None
    assert result.email == "reset@example.com"
    assert result.expires_at == expires_at

    consumed = backend_main.validate_password_reset_token(5, token, consume=True)
    assert consumed is not None
    assert store.find(5, backend_main.TOKEN_TYPE_PASSWORD_RESET) is None


def test_expired_tokens_are_pruned(monkeypatch):
    store = _FakeTokenDatabase()
    _patch_db(monkeypatch, store)

    token, _ = backend_main.issue_onboarding_token(7, "expire@example.com")
    row = store.find(7, backend_main.TOKEN_TYPE_ONBOARDING)
    assert row is not None
    row.expires_at = datetime.utcnow() - timedelta(minutes=1)

    result = backend_main.validate_onboarding_token(7, token)
    assert result is None
    assert store.find(7, backend_main.TOKEN_TYPE_ONBOARDING) is None


def test_tokens_survive_process_restart(monkeypatch):
    store = _FakeTokenDatabase()
    _patch_db(monkeypatch, store)

    token, expires_at = backend_main.issue_onboarding_token(9, "restart@example.com")

    module = importlib.reload(sys.modules["backend.main"])
    monkeypatch.setattr(module, "get_conn", store.connect)

    result = module.validate_onboarding_token(9, token)
    assert result is not None
    assert result.email == "restart@example.com"
    assert result.expires_at == expires_at