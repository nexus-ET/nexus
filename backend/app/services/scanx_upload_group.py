"""ScanX multi-file upload grouping (passport front/back pairs).

JPEG batches already group every image in one picker selection. PDF batches only
group when filenames carry complementary front/back (or equivalent) cues and
share the same stem — unrelated PDFs stay separate documents.
"""

from __future__ import annotations

import re
from pathlib import Path

_SIDE_RE = re.compile(
    r"(?i)(?:^|[\s_\-.(\[])"
    r"(?P<side>front|frnt|recto|obverse|back|bck|verso|reverse)"
    r"(?:$|[\s_\-.)\]])"
)

_FRONT_TOKENS = frozenset({"front", "frnt", "recto", "obverse"})
_BACK_TOKENS = frozenset({"back", "bck", "verso", "reverse"})


def is_pdf_filename(name: str) -> bool:
    return Path(name or "").suffix.lower() == ".pdf"


def is_image_filename(name: str) -> bool:
    return Path(name or "").suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff"}


def passport_side_from_filename(name: str) -> str | None:
    """Return ``front`` / ``back`` when the filename carries a side cue."""
    stem = Path(name or "").stem
    match = _SIDE_RE.search(stem)
    if not match:
        return None
    tok = (match.group("side") or "").lower()
    if tok in _FRONT_TOKENS:
        return "front"
    if tok in _BACK_TOKENS:
        return "back"
    return None


def pairing_stem(name: str) -> str:
    """Normalize filename stem for front/back pairing (side tokens stripped)."""
    stem = Path(name or "").stem
    stem = _SIDE_RE.sub(" ", stem)
    stem = re.sub(r"[\s_\-]+", " ", stem).strip().lower()
    return stem


def group_upload_file_indices(
    filenames: list[str],
) -> list[list[int]]:
    """Return ordered index groups for a single picker batch.

    - Images: all image indices in one group when there are two or more
      (mirrors the existing JPEG ``multi_image_group`` path).
    - PDFs: only complementary front+back pairs that share ``pairing_stem``.
    - Everything else: singleton groups, preserving input order.
    """
    n = len(filenames)
    if n == 0:
        return []

    image_idxs = [i for i, name in enumerate(filenames) if is_image_filename(name)]
    pdf_idxs = [i for i, name in enumerate(filenames) if is_pdf_filename(name)]
    other_idxs = [
        i
        for i in range(n)
        if i not in image_idxs and i not in pdf_idxs
    ]

    groups: list[list[int]] = []
    claimed: set[int] = set()

    if len(image_idxs) >= 2:
        groups.append(list(image_idxs))
        claimed.update(image_idxs)
    else:
        for i in image_idxs:
            groups.append([i])
            claimed.add(i)

    # Pair PDFs by shared stem + complementary sides (front with back only).
    by_stem: dict[str, dict[str, list[int]]] = {}
    for i in pdf_idxs:
        side = passport_side_from_filename(filenames[i])
        if not side:
            continue
        stem = pairing_stem(filenames[i])
        if not stem:
            continue
        by_stem.setdefault(stem, {}).setdefault(side, []).append(i)

    for stem in sorted(by_stem.keys()):
        sides = by_stem[stem]
        fronts = sides.get("front") or []
        backs = sides.get("back") or []
        while fronts and backs:
            fi = fronts.pop(0)
            bi = backs.pop(0)
            # Front first, then back (stable for OCR page order).
            groups.append([fi, bi])
            claimed.update((fi, bi))

    for i in range(n):
        if i in claimed:
            continue
        groups.append([i])
        claimed.add(i)

    # Preserve relative order of first member across groups.
    groups.sort(key=lambda g: g[0])
    # Drop unused other_idxs placeholder (they are included via remainder loop).
    _ = other_idxs
    return groups
