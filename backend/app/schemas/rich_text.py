"""Shared validation for optional HTML-backed text fields."""

from html import unescape
import re
from typing import Annotated

from pydantic import AfterValidator


_HTML_TAG_RE = re.compile(r"<[^>]*>")


def _validate_optional_rich_text_5000(value: str | None) -> str | None:
    if value is None:
        return None
    visible_text = unescape(_HTML_TAG_RE.sub(" ", value))
    visible_text = " ".join(visible_text.split())
    if len(visible_text) > 5000:
        raise ValueError("Description must be 5000 characters or fewer")
    return value


OptionalRichText5000 = Annotated[
    str | None,
    AfterValidator(_validate_optional_rich_text_5000),
]
