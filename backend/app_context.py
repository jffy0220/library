"""Shared application context for reusable dependencies."""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

_get_conn: Optional[Callable[[], Any]] = None
_get_current_user: Optional[Callable[..., Any]] = None
_get_optional_current_user: Optional[Callable[..., Optional[Any]]] = None
_user_model: Optional[Any] = None
_snippet_model: Optional[Any] = None
_snippet_list_response_model: Optional[Any] = None
_comment_model: Optional[Any] = None
_fetch_tags_for_snippets: Optional[Callable[[Any, List[int]], Dict[int, List[Any]]]] = None


def configure(
    *,
    get_conn: Callable[[], Any],
    get_current_user: Callable[..., Any],
    get_optional_current_user: Callable[..., Optional[Any]],
    user_model: Any,
    snippet_model: Any,
    snippet_list_response_model: Any,
    comment_model: Any,
    fetch_tags_for_snippets: Callable[[Any, List[int]], Dict[int, List[Any]]],
) -> None:
    """Register application-wide dependencies required by modular routers."""

    global _get_conn
    global _get_current_user
    global _get_optional_current_user
    global _user_model
    global _snippet_model
    global _snippet_list_response_model
    global _comment_model
    global _fetch_tags_for_snippets

    _get_conn = get_conn
    _get_current_user = get_current_user
    _get_optional_current_user = get_optional_current_user
    _user_model = user_model
    _snippet_model = snippet_model
    _snippet_list_response_model = snippet_list_response_model
    _comment_model = comment_model
    _fetch_tags_for_snippets = fetch_tags_for_snippets


def _require(value: Optional[Any], name: str) -> Any:
    if value is None:
        raise RuntimeError(f"Application context has not been configured yet: {name}")
    return value


def get_conn() -> Any:
    conn_factory = _require(_get_conn, "get_conn")
    return conn_factory()


def get_current_user(*args: Any, **kwargs: Any) -> Any:
    dependency = _require(_get_current_user, "get_current_user")
    return dependency(*args, **kwargs)


def get_optional_current_user(*args: Any, **kwargs: Any) -> Optional[Any]:
    dependency = _require(_get_optional_current_user, "get_optional_current_user")
    return dependency(*args, **kwargs)


def get_user_model() -> Any:
    return _require(_user_model, "user_model")


def get_snippet_model() -> Any:
    return _require(_snippet_model, "snippet_model")


def get_snippet_list_response_model() -> Any:
    return _require(_snippet_list_response_model, "snippet_list_response_model")


def get_comment_model() -> Any:
    return _require(_comment_model, "comment_model")


def fetch_tags_for_snippets(conn: Any, snippet_ids: List[int]) -> Dict[int, List[Any]]:
    fetcher = _require(_fetch_tags_for_snippets, "fetch_tags_for_snippets")
    return fetcher(conn, snippet_ids)