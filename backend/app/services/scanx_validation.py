"""ScanX upload validation, filename sanitize, and R2 key builder."""

from __future__ import annotations

import hashlib
import io
import logging
import re
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException

from app.config import settings
from app.constants.scanx import (
    ALLOWED_EXTENSIONS,
    ALLOWED_MIME_TYPES,
    DOCX_MIME_TYPE,
    format_message,
    subfolder_for_document_type,
)

logger = logging.getLogger(__name__)

_UNSAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")
_SPACE_RE = re.compile(r"\s+")
_MULTI_USCORE = re.compile(r"_+")


def human_file_size(num_bytes: int) -> str:
    n = max(0, int(num_bytes))
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / (1024 * 1024):.0f} MB"


def max_file_size_bytes() -> int:
    return int(settings.SCANX_MAX_FILE_SIZE_BYTES)


def max_pages() -> int:
    return int(settings.SCANX_MAX_PAGES)


def select_images_for_ocr(
    images: list,
    *,
    likely_passport: bool = False,
    max_n: int | None = None,
) -> tuple[list, list[int]]:
    """Pick which page images to OCR under the page budget.

    Returns ``(selected_images, original_page_indices)``.

    Full passport booklet scans (CamScanner) often put biodata near the front and
    Name-of-Father / Address / File No. near the *end*. A simple ``images[:N]``
    cut drops the family page (e.g. page 17 of 18). For passports we keep the
    first and last pages within a higher budget.
    """
    if not images:
        return [], []
    base = int(max_n if max_n is not None else max_pages())
    base = max(1, base)
    n = len(images)
    if not likely_passport:
        limit = base
        if n <= limit:
            idxs = list(range(n))
        else:
            idxs = list(range(limit))
        return [images[i] for i in idxs], idxs

    # Passports: front biodata + rear family/address, up to 16 slots.
    # Order matters: OCR runs under a shared budget and stops on timeout —
    # do biodata (0–1) then rear family pages before middle visa blanks.
    limit = max(base, 16)
    if n <= limit:
        # Still prioritize rear pages early so a timeout cannot drop family OCR.
        ordered: list[int] = []
        for i in range(min(2, n)):
            ordered.append(i)
        for i in range(max(2, n - min(5, n)), n):
            if i not in ordered:
                ordered.append(i)
        for i in range(n):
            if i not in ordered:
                ordered.append(i)
        return [images[i] for i in ordered], ordered

    ordered = []
    for i in range(min(2, n)):
        ordered.append(i)
    back = min(5, n)
    for i in range(max(2, n - back), n):
        if i not in ordered:
            ordered.append(i)
    for i in range(2, min(5, n)):
        if i not in ordered:
            ordered.append(i)
    remaining = limit - len(ordered)
    mid_lo, mid_hi = 5, max(5, n - back)
    if remaining > 0 and mid_hi > mid_lo:
        step = max(1, (mid_hi - mid_lo) // (remaining + 1))
        for i in range(mid_lo, mid_hi, step):
            if len(ordered) >= limit:
                break
            if i not in ordered:
                ordered.append(i)
    return [images[i] for i in ordered], ordered


def scanx_error(code: str, *, status_code: int = 400, **fmt) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error_code": code,
            "message": format_message(
                code,
                max_size_label=fmt.get("max_size_label") or human_file_size(max_file_size_bytes()),
                max_pages=fmt.get("max_pages") if "max_pages" in fmt else max_pages(),
                name=fmt.get("name"),
            ),
        },
    )


def resolve_subfolder(document_type_id: str) -> str:
    subfolder = subfolder_for_document_type(document_type_id)
    if not subfolder:
        raise scanx_error("M2")
    return subfolder


def sanitize_original_basename(filename: str, *, max_stem_len: int = 90) -> tuple[str, str]:
    """Return (safe_basename_without_ext, ext_with_dot)."""
    raw = Path(filename or "").name
    if not raw:
        raw = "document"
    ext = Path(raw).suffix.lower()
    stem = Path(raw).stem
    cleaned = _SPACE_RE.sub("_", stem)
    cleaned = _UNSAFE_RE.sub("_", cleaned).strip(" ._")
    cleaned = _MULTI_USCORE.sub("_", cleaned).strip("._")
    if not cleaned:
        cleaned = "document"
    if len(cleaned) > max_stem_len:
        cleaned = cleaned[:max_stem_len].rstrip("._")
    if ext not in ALLOWED_EXTENSIONS:
        if not ext:
            ext = ""
    return cleaned, ext


def build_r2_key(
    *,
    lead_id: int,
    subfolder: str,
    doc_uuid: UUID | str,
    document_type_id: str,
    original_filename: str,
) -> str:
    """Build STUDENTS/{Lead.id}/… key. ``lead_id`` must be CRM ``leads.id`` PK."""
    root = (settings.SCANX_R2_KEY_ROOT or "STUDENTS").strip().strip("/") or "STUDENTS"
    safe_stem, ext = sanitize_original_basename(original_filename)
    type_id = (document_type_id or "").strip().upper()
    key = f"{root}/{int(lead_id)}/{subfolder}/{doc_uuid}__{type_id}__{safe_stem}{ext}"
    return key


def build_source_page_r2_key(
    *,
    lead_id: int,
    subfolder: str,
    doc_uuid: UUID | str,
    document_type_id: str,
    original_filename: str,
    page_index: int,
) -> str:
    """R2 key for page N of a multi-image document group (0-based)."""
    root = (settings.SCANX_R2_KEY_ROOT or "STUDENTS").strip().strip("/") or "STUDENTS"
    safe_stem, ext = sanitize_original_basename(original_filename)
    type_id = (document_type_id or "").strip().upper()
    idx = max(0, int(page_index))
    return (
        f"{root}/{int(lead_id)}/{subfolder}/"
        f"{doc_uuid}__{type_id}__p{idx}__{safe_stem}{ext}"
    )


def content_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


# Browsers often send DOCX as a generic type; never treat these as final MIME.
_GENERIC_UPLOAD_MIME: frozenset[str] = frozenset(
    {
        "",
        "application/octet-stream",
        "application/zip",
        "application/x-zip-compressed",
        "application/x-zip",
        "multipart/x-zip",
    }
)


def _is_zip_local_file_header(content: bytes) -> bool:
    """True for ZIP local file header (DOCX/OOXML uses PK\\x03\\x04)."""
    return len(content) >= 4 and content[:4] == b"PK\x03\x04"


def looks_like_docx(content: bytes) -> bool:
    """Public OOXML sniff used by upload validation and the ScanX worker."""
    return _looks_like_docx(content)


def _looks_like_docx(content: bytes) -> bool:
    """DOCX is a ZIP package; require OOXML content types + word/ parts."""
    if not _is_zip_local_file_header(content) and not (
        len(content) >= 2 and content[:2] == b"PK"
    ):
        return False
    try:
        import zipfile

        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            names = [n.replace("\\", "/") for n in zf.namelist()]
        has_ctypes = any(n.endswith("[Content_Types].xml") for n in names)
        has_word = any(n.startswith("word/") for n in names)
        return has_ctypes and has_word
    except Exception:
        return False


_DOCX_MEDIA_IMAGE_EXTS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".jpe",
    ".tif",
    ".tiff",
    ".bmp",
    ".gif",
    ".webp",
)


def _image_blob_area(blob: bytes) -> int:
    """Pixel area for ranking media (icons last; main scan first)."""
    dims = _image_blob_dims(blob)
    if not dims:
        return 0
    return int(dims[0]) * int(dims[1])


def _image_blob_dims(blob: bytes) -> tuple[int, int] | None:
    """Return (width, height) or None if undecodable."""
    try:
        from PIL import Image

        with Image.open(io.BytesIO(blob)) as im:
            w, h = im.size
            if w > 0 and h > 0:
                return int(w), int(h)
    except Exception:
        return None
    return None


def is_scan_watermark_banner(blob: bytes) -> bool:
    """True for CamScanner-style stamp strips / tiny logos (not a full page).

    Typical CamScanner XObject: ~813×92 ``Scanned with CamScanner`` banner.
    """
    dims = _image_blob_dims(blob)
    if not dims:
        return False
    w, h = dims
    short_side = min(w, h)
    long_side = max(w, h)
    if short_side <= 0:
        return False
    ratio = long_side / float(short_side)
    # Wide/tall thin banner.
    if ratio >= 4.0 and short_side < 280:
        return True
    if ratio >= 6.0 and short_side < 360:
        return True
    # Tiny square/rect logo stamp.
    if long_side < 420 and short_side < 220:
        return True
    if w * h < 40_000:
        return True
    return False


def pick_largest_content_image(images: list[bytes]) -> bytes | None:
    """Largest non-watermark frame — used for Enhanced DPI counsellor preview."""
    best: tuple[int, bytes] | None = None
    for blob in images:
        if not blob or is_scan_watermark_banner(blob):
            continue
        area = _image_blob_area(blob) or len(blob)
        if best is None or area > best[0]:
            best = (area, blob)
    if best:
        return best[1]
    if not images:
        return None
    return max(images, key=lambda b: _image_blob_area(b) or len(b or b""))


def pdf_raw_embedded_image_blobs(content: bytes) -> list[bytes]:
    """All page XObject image payloads (unfiltered) for stamp detection."""
    if not looks_like_pdf(content):
        return []
    try:
        reader = _open_pdf_reader(content)
    except Exception:
        return []
    out: list[bytes] = []
    try:
        page_limit = max(1, max_pages())
        for page in list(reader.pages)[:page_limit]:
            try:
                for img in getattr(page, "images", None) or []:
                    blob = getattr(img, "data", None)
                    if isinstance(blob, (bytes, bytearray)) and blob:
                        out.append(bytes(blob))
            except Exception:
                continue
    except Exception:
        return out
    return out


def pdf_has_scan_app_stamp(content: bytes) -> bool:
    """CamScanner (etc.) left a logo/banner XObject — prefer full-page render."""
    for blob in pdf_raw_embedded_image_blobs(content):
        if is_scan_watermark_banner(blob):
            return True
        sample = blob[:12_000].lower() if blob else b""
        if b"camscanner" in sample or b"cam scanner" in sample:
            return True
    return False


def extract_docx_embedded_images(content: bytes) -> list[bytes]:
    """Return image payloads under word/media/ (largest / content page first).

    Tiny icons and logos are deprioritized so OCR matches PDF/JPG of the same
    marksheet instead of concatenating stamp noise into the extract.
    """
    import zipfile

    if len(content) < 2 or content[:2] != b"PK":
        return []
    images: list[tuple[int, int, bytes]] = []
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            names = sorted(
                n.replace("\\", "/")
                for n in zf.namelist()
                if n.replace("\\", "/").startswith("word/media/")
                and not n.endswith("/")
            )
            for name in names:
                lower = name.lower()
                if not any(lower.endswith(ext) for ext in _DOCX_MEDIA_IMAGE_EXTS):
                    continue
                try:
                    blob = zf.read(name)
                except Exception:
                    continue
                if not blob or len(blob) < 2_000:
                    # Skip tiny media (bullets / 1x1 / icons).
                    continue
                area = _image_blob_area(blob)
                if area and area < 40_000:
                    # < ~200×200 — unlikely to be the certificate page.
                    continue
                images.append((area or len(blob), len(blob), blob))
    except zipfile.BadZipFile:
        return []
    except Exception:
        logger.debug("DOCX media enumerate failed", exc_info=True)
        return []
    images.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [blob for _area, _nbytes, blob in images]


def _xml_local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _xml_gather_t(el) -> str:
    """Join ``w:t`` runs under an element (preserve internal spaces)."""
    parts: list[str] = []
    for node in el.iter():
        if _xml_local_tag(node.tag) != "t":
            continue
        val = node.text or ""
        if val:
            parts.append(val)
    return "".join(parts).strip()


def _format_table_row_cells(cells: list[str]) -> str:
    """Join non-empty cell texts for a readable marksheet / table line."""
    return " | ".join(c for c in cells if c)


def _dedupe_row_cell_texts(cells: list[str]) -> list[str]:
    """Drop consecutive duplicate cells (python-docx expands horizontal merges)."""
    out: list[str] = []
    for text in cells:
        if out and out[-1] == text:
            continue
        out.append(text)
    return out


def _table_rows_from_python_docx(table) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in table.rows:
        seen: set[int] = set()
        cells: list[str] = []
        for cell in row.cells:
            # Prefer element identity so true distinct empty cells are kept.
            cid = id(getattr(cell, "_tc", cell))
            if cid in seen:
                continue
            seen.add(cid)
            cells.append((cell.text or "").strip())
        rows.append(_dedupe_row_cell_texts(cells))
    return rows


def _collect_docx_table_batches(table) -> list[list[list[str]]]:
    """Parent table rows plus nested cell tables (Mathematics often nested)."""
    batches: list[list[list[str]]] = []
    try:
        rows = _table_rows_from_python_docx(table)
    except Exception:
        logger.debug("DOCX table extract partial failure", exc_info=True)
        rows = []
    if rows:
        batches.append(rows)
    try:
        for row in table.rows:
            seen_tc: set[int] = set()
            for cell in row.cells:
                cid = id(getattr(cell, "_tc", cell))
                if cid in seen_tc:
                    continue
                seen_tc.add(cid)
                for nested in getattr(cell, "tables", []) or []:
                    batches.extend(_collect_docx_table_batches(nested))
    except Exception:
        logger.debug("DOCX nested table walk failed", exc_info=True)
    return batches


def _iter_docx_block_items(document):
    """Yield paragraphs and tables in document-body order."""
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    body = document.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _iter_docx_header_footer_tables(document):
    """Yield tables from headers/footers (some marksheets put grids there)."""
    try:
        sections = document.sections
    except Exception:
        return
    for section in sections:
        for part in (
            getattr(section, "header", None),
            getattr(section, "footer", None),
            getattr(section, "first_page_header", None),
            getattr(section, "first_page_footer", None),
        ):
            if part is None:
                continue
            try:
                for table in part.tables:
                    yield table
            except Exception:
                continue


def _xml_body_lines(root) -> list[str]:
    """Extract paragraph + table lines from a WordprocessingML root in order.

    Also walks text boxes (``w:txbxContent``) and content controls (``w:sdt``)
    which python-docx body iteration often misses — common after PDF→DOCX
    conversion or when marksheet grids sit in floating frames.
    """
    lines: list[str] = []
    body = None
    for el in root.iter():
        if _xml_local_tag(el.tag) == "body":
            body = el
            break
    parent = body if body is not None else root

    def _emit_p(p_el) -> None:
        text = _xml_gather_t(p_el)
        if text:
            lines.append(text)

    def _emit_tbl(tbl_el) -> None:
        for tr in tbl_el:
            if _xml_local_tag(tr.tag) != "tr":
                continue
            cells: list[str] = []
            for tc in tr:
                if _xml_local_tag(tc.tag) != "tc":
                    continue
                cells.append(_xml_gather_t(tc))
            line = _format_table_row_cells(_dedupe_row_cell_texts(cells))
            if line:
                lines.append(line)

    def _walk(el, *, in_textbox: bool = False) -> None:
        tag = _xml_local_tag(el.tag)
        if tag == "p":
            _emit_p(el)
            return
        if tag == "tbl":
            _emit_tbl(el)
            return
        if tag == "txbxContent":
            for child in list(el):
                _walk(child, in_textbox=True)
            return
        if tag == "sdt":
            # Structured document tag — content lives under sdtContent.
            for child in list(el):
                if _xml_local_tag(child.tag) == "sdtContent":
                    for nested in list(child):
                        _walk(nested, in_textbox=in_textbox)
            return
        # Drawings / shapes may nest txbxContent deeper — recurse selectively.
        if tag in {"r", "drawing", "pict", "txbx", "textbox", "graphic", "graphicData", "sdtContent"}:
            for child in list(el):
                _walk(child, in_textbox=in_textbox)

    for child in list(parent):
        _walk(child)
    if lines:
        return lines
    # No body children matched (unusual package): flat ``w:t`` join with spaces.
    flat = _xml_gather_t(root)
    return [flat] if flat else []


def _extract_docx_textbox_lines_via_zip(content: bytes) -> list[str]:
    """Collect text-box / content-control lines missed by python-docx body walk."""
    import zipfile
    from xml.etree import ElementTree as ET

    if len(content) < 2 or content[:2] != b"PK":
        return []
    extra: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            for name in zf.namelist():
                n = name.replace("\\", "/")
                if n != "word/document.xml" and not (
                    n.startswith("word/header") or n.startswith("word/footer")
                ):
                    continue
                if not n.endswith(".xml"):
                    continue
                try:
                    root = ET.fromstring(zf.read(name))
                except Exception:
                    continue
                # Prefer dedicated textbox nodes even when body walk already ran.
                for el in root.iter():
                    if _xml_local_tag(el.tag) != "txbxContent":
                        continue
                    chunk = _xml_body_lines(el)
                    for line in chunk:
                        if line and line not in extra:
                            extra.append(line)
    except Exception:
        logger.debug("DOCX textbox zip extract failed", exc_info=True)
        return []
    return extra


def _extract_docx_via_zip(content: bytes) -> str | None:
    """Fallback text extract from word/*.xml when python-docx fails on a valid package.

    Preserves table row/cell structure as ``cell | cell`` lines so marksheets
    remain readable when python-docx is missing or cannot open the package.
    """
    import zipfile
    from xml.etree import ElementTree as ET

    if len(content) < 2 or content[:2] != b"PK":
        return None
    texts: list[str] = []
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            names = [n.replace("\\", "/") for n in zf.namelist()]
            if not any(n.endswith("[Content_Types].xml") for n in names):
                return None
            xml_names = [
                n
                for n in names
                if n.startswith("word/")
                and n.endswith(".xml")
                and (
                    n == "word/document.xml"
                    or n.startswith("word/header")
                    or n.startswith("word/footer")
                    or "footnotes" in n
                    or "endnotes" in n
                    or "comments" in n
                    or n.startswith("word/glossary/")
                )
            ]
            xml_names.sort(key=lambda n: (0 if n == "word/document.xml" else 1, n))
            for name in xml_names:
                try:
                    raw = zf.read(name)
                    root = ET.fromstring(raw)
                except Exception:
                    continue
                chunk_lines = _xml_body_lines(root)
                if chunk_lines:
                    texts.extend(chunk_lines)
    except zipfile.BadZipFile:
        return None
    except Exception:
        logger.debug("DOCX zip fallback failed", exc_info=True)
        return None
    joined = "\n".join(texts).strip()
    return joined or None


def extract_docx_text(content: bytes) -> tuple[str | None, list[dict[str, str]]]:
    """Extract DOCX body text including tables, plus structured subjects when detected.

    Returns ``(joined_text_or_none, subjects)`` where each subject is
    ``{"name": ..., "marks": ..., "grade": ...}`` (grade optional / may be "").

    Tables are emitted as readable ``cell | cell`` lines. Paragraphs and tables
    are walked in document order so marksheet grids are not lost (paragraph-only
    extract would miss subject/marks cells).
    """
    from app.services.scanx_academic_parse import (
        merge_subjects,
        parse_subjects_from_table_rows,
        parse_subjects_from_text,
    )

    if not content or not _looks_like_docx(content):
        return None, []

    parts: list[str] = []
    table_row_batches: list[list[list[str]]] = []

    try:
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        try:
            document = Document(io.BytesIO(content))
            for block in _iter_docx_block_items(document):
                if isinstance(block, Paragraph):
                    text = (block.text or "").strip()
                    if text:
                        parts.append(text)
                elif isinstance(block, Table):
                    for rows in _collect_docx_table_batches(block):
                        if rows:
                            table_row_batches.append(rows)
                        for row_cells in rows:
                            line = _format_table_row_cells(row_cells)
                            if line:
                                parts.append(line)
            # Headers/footers may hold marksheet grids missed in body walk.
            for hf_table in _iter_docx_header_footer_tables(document):
                for rows in _collect_docx_table_batches(hf_table):
                    if rows:
                        table_row_batches.append(rows)
                    for row_cells in rows:
                        line = _format_table_row_cells(row_cells)
                        if line and line not in parts:
                            parts.append(line)
        except Exception as exc:
            logger.info(
                "DOCX python-docx open/extract failed on valid OOXML, trying zip fallback: %s",
                exc,
            )
            parts = []
            table_row_batches = []
    except ImportError:
        logger.error(
            "python-docx is not installed; using zip XML fallback "
            "(pip install python-docx)"
        )
        parts = []
        table_row_batches = []

    joined = "\n".join(parts).strip() or None
    if not joined:
        joined = _extract_docx_via_zip(content)
    else:
        # Append text-box / floating-frame lines python-docx body walk missed.
        for line in _extract_docx_textbox_lines_via_zip(content):
            if line and line not in parts:
                parts.append(line)
        joined = "\n".join(parts).strip() or joined

    table_subjects: list[dict[str, str]] = []
    for rows in table_row_batches:
        table_subjects.extend(parse_subjects_from_table_rows(rows))

    text_subjects = parse_subjects_from_text(joined) if joined else []
    subjects = merge_subjects(table_subjects, text_subjects)
    return joined, subjects


def _pdf_header_offset(content: bytes, *, probe: int = 1024) -> int:
    """Return index of ``%PDF`` within the first ``probe`` bytes, or -1."""
    if not content:
        return -1
    window = content[: max(5, int(probe))]
    return window.find(b"%PDF")


def looks_like_pdf(content: bytes) -> bool:
    """True when bytes look like a PDF (optional leading junk before ``%PDF``)."""
    return _pdf_header_offset(content) >= 0


def sniff_content_type(filename: str, declared: str | None, content: bytes) -> str:
    declared_norm = (declared or "").split(";")[0].strip().lower()
    ext = Path(filename or "").suffix.lower()
    # Magic always wins for PDF — browsers sometimes send image/* or octet-stream.
    if looks_like_pdf(content):
        return "application/pdf"
    # Prefer extension + magic over a declared OOXML MIME that might be wrong,
    # and always sniff when the browser only sent a generic ZIP/octet type.
    trust_declared = (
        declared_norm in ALLOWED_MIME_TYPES and declared_norm not in _GENERIC_UPLOAD_MIME
    )
    if trust_declared and declared_norm == DOCX_MIME_TYPE:
        # Confirm OOXML when possible; generic ZIP declared as DOCX is fine if structure matches.
        if _looks_like_docx(content) or ext == ".docx" or not content:
            return DOCX_MIME_TYPE
        # Declared DOCX but bytes are not OOXML — fall through to magic/ext.
    elif trust_declared and declared_norm == "application/pdf":
        # Declared PDF but no %PDF magic — still allow by extension; open decides M7.
        if ext == ".pdf" or not content:
            return "application/pdf"
        # Fall through so a mislabeled image/DOCX is sniffed correctly.
    elif trust_declared:
        if declared_norm == "image/jpg":
            return "image/jpeg"
        if declared_norm == "image/tif":
            return "image/tiff"
        return declared_norm
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content[:2] == b"\xff\xd8":
        return "image/jpeg"
    if content[:2] in (b"II", b"MM") and ext in {".tif", ".tiff"}:
        return "image/tiff"
    # DOCX: accept by .docx extension and/or OOXML ZIP sniff (even when MIME is zip/octet-stream).
    if ext == ".docx" or _looks_like_docx(content):
        if ext == ".docx" and content and not _looks_like_docx(content):
            # Extension claims DOCX but package is not readable OOXML.
            if _is_zip_local_file_header(content) or content[:2] == b"PK":
                # ZIP that isn't Word OOXML — wrong type, not "damaged PDF-style".
                raise scanx_error("M3")
            raise scanx_error("M7")
        return DOCX_MIME_TYPE
    if ext == ".pdf":
        return "application/pdf"
    if ext == ".png":
        return "image/png"
    if ext in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if ext in {".tif", ".tiff"}:
        return "image/tiff"
    raise scanx_error("M3")


def validate_mime_and_size(*, filename: str, content_type: str | None, content: bytes) -> str:
    if not content:
        raise scanx_error("M7")
    if len(content) > max_file_size_bytes():
        raise scanx_error("M4")
    resolved = sniff_content_type(filename, content_type, content)
    if resolved not in ALLOWED_MIME_TYPES:
        raise scanx_error("M3")
    ext = Path(filename or "").suffix.lower()
    if ext and ext not in ALLOWED_EXTENSIONS:
        raise scanx_error("M3")
    # Extra guard: DOCX must look like OOXML. Prefer M3 (wrong type) over M7
    # (damaged) when extension/MIME claimed Word but package is a non-Word ZIP.
    if resolved == DOCX_MIME_TYPE and content and not _looks_like_docx(content):
        if content[:2] == b"PK":
            raise scanx_error("M3")
        raise scanx_error("M7")
    return resolved


def _is_pdf_password_error(exc: BaseException) -> bool:
    name = type(exc).__name__
    if name in {"FileNotDecryptedError", "PasswordError", "PdfReadError"}:
        msg = str(exc).lower()
        if name == "FileNotDecryptedError":
            return True
        if "decrypt" in msg or "password" in msg or "encrypted" in msg:
            return True
    return False


def _pdf_decrypt_ok(reader: object) -> bool:
    """Return True when the reader is usable (not encrypted, or empty password works)."""
    if not getattr(reader, "is_encrypted", False):
        return True
    decrypt = getattr(reader, "decrypt", None)
    if not callable(decrypt):
        return False
    try:
        unlocked = decrypt("")
    except Exception as exc:
        if _is_pdf_password_error(exc):
            return False
        logger.info("PDF decrypt('') raised: %s", exc)
        return False
    # pypdf PasswordType: NOT_DECRYPTED=0 is falsy; USER/OWNER are truthy.
    return bool(unlocked)


def _open_pdf_reader(content: bytes):
    """Open a PdfReader with junk-prefix trim + empty-password retry. Raises on failure."""
    from pypdf import PdfReader

    offset = _pdf_header_offset(content)
    payload = content[offset:] if offset > 0 else content
    last_exc: BaseException | None = None

    for attempt_payload in dict.fromkeys((payload, content)):
        # 1) Normal open (strict=False is pypdf default; pass explicitly for older pins).
        try:
            reader = PdfReader(io.BytesIO(attempt_payload), strict=False)
        except TypeError:
            try:
                reader = PdfReader(io.BytesIO(attempt_payload))
            except Exception as exc:
                last_exc = exc
                continue
        except Exception as exc:
            last_exc = exc
            # 2) Some encrypted PDFs want password at construction time (pypdf 5+/6+).
            try:
                reader = PdfReader(io.BytesIO(attempt_payload), strict=False, password="")
            except TypeError:
                try:
                    reader = PdfReader(io.BytesIO(attempt_payload), password="")
                except Exception as exc2:
                    last_exc = exc2
                    continue
            except Exception as exc2:
                last_exc = exc2
                continue

        if not _pdf_decrypt_ok(reader):
            raise scanx_error("M6")
        return reader

    if last_exc and _is_pdf_password_error(last_exc):
        raise scanx_error("M6") from last_exc
    logger.info("PDF open failed: %s", last_exc)
    raise scanx_error("M7") from last_exc


def extract_pdf_embedded_images(content: bytes) -> list[bytes]:
    """Return embedded image bytes from PDF pages (largest / content page first).

    CamScanner and similar apps often embed a tiny ``Scanned with CamScanner``
    logo XObject alongside (or instead of) the full page raster. Without a
    size filter, OCR/enhance runs on the watermark only — producing a preview
    that is literally just that stamp. Tiny logos/icons are dropped; remaining
    images are ranked by pixel area (same policy as DOCX media).
    """
    if not looks_like_pdf(content):
        return []

    ranked: list[tuple[int, int, bytes]] = []
    for raw in pdf_raw_embedded_image_blobs(content):
        if len(raw) < 2_000:
            continue
        if is_scan_watermark_banner(raw):
            continue
        area = _image_blob_area(raw)
        ranked.append((area or len(raw), len(raw), raw))

    ranked.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [blob for _area, _nbytes, blob in ranked]


def pdf_embedded_images_usable_for_ocr(images: list[bytes]) -> bool:
    """True when the largest embedded image looks like a full page, not a stamp."""
    if not images:
        return False
    candidate = pick_largest_content_image(images)
    if candidate is None or is_scan_watermark_banner(candidate):
        return False
    area = _image_blob_area(candidate)
    # ~700×900 ≈ 630k — below this prefer full-page rasterization.
    return bool(area and area >= 300_000)


def pdf_page_count(content: bytes) -> int:
    """Return PDF page count (0 when not a PDF / unreadable)."""
    if not looks_like_pdf(content):
        return 0
    try:
        reader = _open_pdf_reader(content)
        return max(0, len(getattr(reader, "pages", []) or []))
    except Exception:
        try:
            import pypdfium2 as pdfium

            offset = _pdf_header_offset(content)
            payload = content[offset:] if offset > 0 else content
            doc = pdfium.PdfDocument(payload)
            try:
                return max(0, len(doc))
            finally:
                doc.close()
        except Exception:
            return 0


def render_pdf_pages_as_png(content: bytes, *, scale: float = 2.0) -> list[bytes]:
    """Rasterize PDF pages to PNG for OCR when native text / XObject images are empty.

    Uses pypdfium2 (wheel, no Poppler). Returns [] if unavailable or render fails.
    """
    if not looks_like_pdf(content):
        return []
    try:
        import pypdfium2 as pdfium
    except ImportError:
        logger.info("pypdfium2 not installed; cannot render PDF pages for OCR")
        return []

    out: list[bytes] = []
    try:
        offset = _pdf_header_offset(content)
        payload = content[offset:] if offset > 0 else content
        doc = pdfium.PdfDocument(payload)
        try:
            page_limit = min(len(doc), max(1, max_pages()))
            for i in range(page_limit):
                page = doc[i]
                try:
                    bitmap = page.render(scale=scale)
                    pil = bitmap.to_pil()
                    buf = io.BytesIO()
                    pil.convert("RGB").save(buf, format="PNG")
                    out.append(buf.getvalue())
                except Exception:
                    logger.debug("PDF page render failed idx=%s", i, exc_info=True)
                finally:
                    page.close()
        finally:
            doc.close()
    except Exception:
        logger.debug("PDF page rasterize failed", exc_info=True)
        return []
    return out


def _extract_pdf_via_pdfplumber(
    content: bytes,
) -> tuple[int | None, str | None, list[list[list[str]]]]:
    """Extract text + table cell grids with pdfplumber. Returns (pages, text, tables)."""
    try:
        import pdfplumber
    except ImportError:
        return None, None, []

    offset = _pdf_header_offset(content)
    payload = content[offset:] if offset > 0 else content
    page_texts: list[str] = []
    table_batches: list[list[list[str]]] = []
    page_count: int | None = None
    try:
        with pdfplumber.open(io.BytesIO(payload)) as pdf:
            page_count = len(pdf.pages)
            if page_count > max_pages():
                raise scanx_error("M5", max_pages=max_pages())
            for page in pdf.pages[: max(1, max_pages())]:
                page_lines: list[str] = []
                try:
                    tables = page.extract_tables() or []
                except Exception:
                    tables = []
                for table in tables:
                    rows: list[list[str]] = []
                    for raw_row in table or []:
                        cells = [
                            (c or "").replace("\n", " ").strip()
                            for c in (raw_row or [])
                        ]
                        # Keep empty cells for column alignment; strip trailing blanks later.
                        while cells and not cells[-1]:
                            cells.pop()
                        if any(cells):
                            rows.append(cells)
                            line = _format_table_row_cells(cells)
                            if line:
                                page_lines.append(line)
                    if rows:
                        table_batches.append(rows)
                try:
                    # layout=True keeps multi-space columns for heuristic parse.
                    plain = page.extract_text(layout=True) or page.extract_text() or ""
                except TypeError:
                    plain = page.extract_text() or ""
                except Exception:
                    plain = ""
                if plain.strip():
                    # Avoid duplicating table lines already emitted as pipes.
                    for ln in plain.splitlines():
                        cleaned = ln.strip()
                        if not cleaned:
                            continue
                        if cleaned in page_lines:
                            continue
                        page_lines.append(cleaned)
                if page_lines:
                    page_texts.append("\n".join(page_lines))
    except HTTPException:
        raise
    except Exception as exc:
        if _is_pdf_password_error(exc):
            raise scanx_error("M6") from exc
        logger.info("pdfplumber extract failed, falling back to pypdf: %s", exc)
        return None, None, []

    joined = "\n\n".join(page_texts).strip() or None
    return page_count, joined, table_batches


def _extract_pdf_via_pypdf(content: bytes) -> tuple[int, str | None]:
    """Legacy pypdf text extract (no table structure)."""
    try:
        from pypdf import PdfReader  # noqa: F401 — import gate
    except ImportError as exc:
        logger.warning("pypdf not installed; cannot inspect PDF")
        raise HTTPException(
            status_code=500,
            detail={"error_code": "M7", "message": format_message("M7")},
        ) from exc

    if not content:
        raise scanx_error("M7")

    try:
        reader = _open_pdf_reader(content)
    except HTTPException:
        raise
    except Exception as exc:
        if _is_pdf_password_error(exc):
            raise scanx_error("M6") from exc
        logger.info("PDF open failed: %s", exc)
        raise scanx_error("M7") from exc

    try:
        pages = len(reader.pages)
    except Exception as exc:
        if _is_pdf_password_error(exc):
            raise scanx_error("M6") from exc
        logger.info("PDF page count failed: %s", exc)
        raise scanx_error("M7") from exc

    if pages > max_pages():
        raise scanx_error("M5", max_pages=max_pages())

    texts: list[str] = []
    for idx in range(pages):
        try:
            page = reader.pages[idx]
        except Exception as exc:
            if _is_pdf_password_error(exc):
                raise scanx_error("M6") from exc
            texts.append("")
            continue
        try:
            try:
                page_text = page.extract_text(extraction_mode="layout") or ""
            except TypeError:
                page_text = page.extract_text() or ""
            texts.append(page_text)
        except Exception:
            texts.append("")
    joined = "\n".join(texts).strip() or None
    return pages, joined


def extract_pdf_text(content: bytes) -> tuple[int, str | None, list[dict[str, str]]]:
    """Extract PDF text with table-aware pdfplumber when available.

    Returns ``(page_count, text, subjects)``. Subjects come from detected
    marksheet tables plus line heuristics (same shape as DOCX extract).
    """
    from app.services.scanx_academic_parse import (
        merge_subjects,
        parse_subjects_from_table_rows,
        parse_subjects_from_text,
    )

    if not content or not looks_like_pdf(content):
        raise scanx_error("M7")

    pages: int | None = None
    joined: str | None = None
    table_batches: list[list[list[str]]] = []

    try:
        pages, joined, table_batches = _extract_pdf_via_pdfplumber(content)
    except HTTPException:
        raise
    except Exception:
        logger.debug("pdfplumber path unexpected failure", exc_info=True)
        pages, joined, table_batches = None, None, []

    if pages is None:
        pages, joined = _extract_pdf_via_pypdf(content)
    elif not (joined or "").strip():
        # pdfplumber opened but found no text — try pypdf layout as supplement.
        try:
            pypdf_pages, pypdf_text = _extract_pdf_via_pypdf(content)
            pages = pages or pypdf_pages
            if pypdf_text:
                joined = pypdf_text
        except HTTPException:
            raise
        except Exception:
            logger.debug("pypdf supplement failed", exc_info=True)

    assert pages is not None
    table_subjects: list[dict[str, str]] = []
    for rows in table_batches:
        table_subjects.extend(parse_subjects_from_table_rows(rows))
    text_subjects = parse_subjects_from_text(joined) if joined else []
    subjects = merge_subjects(table_subjects, text_subjects)
    return pages, joined, subjects


def inspect_pdf(content: bytes) -> tuple[int, str | None]:
    """Return (page_count, extracted_text_or_none).

    Raises scanx_error M6 (password), M5 (too many pages), or M7 (unreadable).
    Empty / scanned PDFs return ``(pages, None)`` — never M7 for text-empty.

    Prefers pdfplumber so marksheet tables become ``cell | cell`` lines that the
    academic parser can turn into structured subjects.
    """
    pages, joined, _subjects = extract_pdf_text(content)
    return pages, joined


def inspect_pdf_pages_only(content: bytes) -> tuple[int, None]:
    """Upload-path PDF check: encryption + page cap only (no pdfplumber/OCR).

    Full native-text extract belongs on the ScanX worker so POST /documents can
    return 202 without blocking on table parsing.
    """
    if not content or not looks_like_pdf(content):
        raise scanx_error("M7")
    reader = _open_pdf_reader(content)
    pages = max(0, len(getattr(reader, "pages", []) or []))
    if pages < 1:
        raise scanx_error("M7")
    if pages > max_pages():
        raise scanx_error("M5", max_pages=max_pages())
    return pages, None


def inspect_docx(content: bytes) -> tuple[int | None, str | None]:
    """Extract native DOCX text (python-docx, then zip/XML fallback).

    Page count is not enforced (DOCX limited by file size). Image-only Word
    files (scanned pages pasted as media) return empty here; the ScanX worker
    OCRs ``word/media/*`` afterward.

    Raises M7 only when the bytes are not a readable Word OOXML package.
    Missing python-docx or extract quirks on a valid OOXML file fall back to
    zip XML extraction, then empty text (Action Required) — never a false M7.

    Tables are included (see :func:`extract_docx_text`).
    """
    if not content or not _looks_like_docx(content):
        raise scanx_error("M7")

    joined, _subjects = extract_docx_text(content)
    # Valid OOXML with no body text → empty extract (worker may OCR media; else M14).
    return None, joined


def validate_pages_for_content(content_type: str, content: bytes) -> tuple[int | None, str | None]:
    """Validate page caps for HTTP upload; return (page_count, early_text).

    PDF: encryption + SCANX_MAX_PAGES only (worker extracts text/OCR).
    DOCX: confirm OOXML; no page check (size limit only). Worker extracts text.
    Images: treat as 1 page for cap purposes.
    """
    if content_type == "application/pdf":
        return inspect_pdf_pages_only(content)
    if content_type == DOCX_MIME_TYPE:
        if not content or not _looks_like_docx(content):
            raise scanx_error("M7")
        return None, None
    # Images: treat as 1 page for cap purposes.
    return 1, None
