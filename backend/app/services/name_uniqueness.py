from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Query

_DASH_TRANSLATION = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
    }
)


def normalized_display_name(value: str) -> str:
    text = ((value or "").translate(_DASH_TRANSLATION))
    return " ".join(text.split()).casefold()


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
    query = query.filter(func.lower(func.btrim(column)) == normalized)
    if exclude_id is not None and id_column is not None:
        query = query.filter(id_column != exclude_id)
    return query
