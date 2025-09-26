from __future__ import annotations

from typing import List, Optional, Sequence, Union

from fastapi import HTTPException, status

try:
    from backend.group_service import GROUP_PRIVACY_VALUES
except ModuleNotFoundError as exc:
    if exc.name != "backend":
        raise
    from group_service import GROUP_PRIVACY_VALUES  # type: ignore[no-redef]


def normalize_visibility_filter(value: Optional[Union[str, Sequence[str]]]) -> List[str]:
    """Parse visibility query parameters into a normalized list of privacy states."""

    if value is None:
        return ["public"]

    if isinstance(value, str):
        raw_values: Sequence[str] = [value]
    else:
        raw_values = value

    normalized: List[str] = []
    for raw in raw_values:
        if not isinstance(raw, str):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid visibility filter",
            )
        for fragment in raw.split(","):
            option = fragment.strip().lower()
            if not option:
                continue
            if option not in GROUP_PRIVACY_VALUES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid visibility filter",
                )
            if option not in normalized:
                normalized.append(option)

    return normalized or ["public"]