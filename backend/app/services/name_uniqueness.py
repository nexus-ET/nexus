from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Query


def normalized_display_name(value: str) -> str:
    return (value or "").strip().casefold()


def filter_by_display_name(
    query: Query,
    column,
    name: str,
    *,
    exclude_id=None,
    id_column=None,
) -> Query:
    normalized = normalized_display_name(name)
    if not normalized:
        return query.filter(False)
    query = query.filter(func.lower(column) == normalized)
    if exclude_id is not None and id_column is not None:
        query = query.filter(id_column != exclude_id)
    return query
