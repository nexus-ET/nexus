"""Shared validation for optional HTML-backed text fields."""

from html import unescape
import re
from typing import Annotated

from pydantic import AfterValidator


_HTML_TAG_RE = re.compile(r"<[^>]*>")


def _validate_optional_rich_text(value: str | None, max_chars: int, field_label: str) -> str | None:
    if value is None:
        return None
    visible_text = unescape(_HTML_TAG_RE.sub(" ", value))
    visible_text = " ".join(visible_text.split())
    if len(visible_text) > max_chars:
        raise ValueError(f"{field_label} must be {max_chars} characters or fewer")
    return value


def _validate_optional_rich_text_2000(value: str | None) -> str | None:
    return _validate_optional_rich_text(value, 2000, "Sub-major description")


def _validate_optional_rich_text_5000(value: str | None) -> str | None:
    return _validate_optional_rich_text(value, 5000, "Description")


OptionalRichText2000 = Annotated[
    str | None,
    AfterValidator(_validate_optional_rich_text_2000),
]

OptionalRichText5000 = Annotated[
    str | None,
    AfterValidator(_validate_optional_rich_text_5000),
]
