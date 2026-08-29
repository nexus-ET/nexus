from __future__ import annotations

import sys
from typing import TextIO


def safe_print(
    *values: object,
    sep: str = " ",
    end: str = "\n",
    file: TextIO | None = None,
    flush: bool = False,
) -> None:
    """Print without letting the console encoding break application code."""
    stream = file or sys.stdout
    text = sep.join(str(value) for value in values)
    encoding = getattr(stream, "encoding", None) or "utf-8"
    safe_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
    stream.write(safe_text + end)
    if flush:
        stream.flush()
