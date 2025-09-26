import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.group_filters import normalize_visibility_filter


def test_normalize_visibility_supports_comma_delimited_string():
    assert normalize_visibility_filter("public,unlisted") == ["public", "unlisted"]


def test_normalize_visibility_supports_multiple_query_params():
    assert normalize_visibility_filter(["public", "unlisted"]) == ["public", "unlisted"]


def test_normalize_visibility_deduplicates_and_preserves_order():
    assert normalize_visibility_filter(["public", "PUBLIC", "unlisted", "public"]) == [
        "public",
        "unlisted",
    ]