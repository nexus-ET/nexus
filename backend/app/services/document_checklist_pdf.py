"""Generate Document Checklist PDFs for academia program levels."""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_PAGE_SIZE = A4
_PAGE_WIDTH, _PAGE_HEIGHT = _PAGE_SIZE
_MARGIN = 0.7 * inch
_FOOTER_BAND = 0.55 * inch
_EM_DASH = "\u2014"
_LOGO_MAX_W = 1.15 * inch
_LOGO_MAX_H = 0.45 * inch
_PDF_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

_FONT_REGULAR = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"
_FONTS_READY = False


def _ensure_fonts() -> tuple[str, str]:
    """Prefer a Unicode TTF so em dashes render; fall back to Helvetica."""
    global _FONT_REGULAR, _FONT_BOLD, _FONTS_READY
    if _FONTS_READY:
        return _FONT_REGULAR, _FONT_BOLD

    candidates = [
        (
            Path(r"C:\Windows\Fonts\arial.ttf"),
            Path(r"C:\Windows\Fonts\arialbd.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ),
        (
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"),
            Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        ),
    ]
    for regular, bold in candidates:
        if regular.is_file() and bold.is_file():
            try:
                pdfmetrics.registerFont(TTFont("ChecklistSans", str(regular)))
                pdfmetrics.registerFont(TTFont("ChecklistSans-Bold", str(bold)))
                _FONT_REGULAR = "ChecklistSans"
                _FONT_BOLD = "ChecklistSans-Bold"
                break
            except Exception:
                continue

    _FONTS_READY = True
    return _FONT_REGULAR, _FONT_BOLD


class _ChecklistFooterCanvas(canvas.Canvas):
    """Two-pass canvas that stamps CONFIDENTIAL / LAST UPDATE / Page x of y."""

    def __init__(self, *args: Any, last_update_label: str, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._page_states: list[dict] = []
        self._last_update_label = last_update_label
        self._font_regular, _ = _ensure_fonts()

    def showPage(self) -> None:
        self._page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total_pages = len(self._page_states)
        for state in self._page_states:
            self.__dict__.update(state)
            self._draw_footer(total_pages)
            super().showPage()
        super().save()

    def _draw_footer(self, total_pages: int) -> None:
        self.saveState()
        left = _MARGIN
        right = _PAGE_WIDTH - _MARGIN
        y = _MARGIN - 4

        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(left, y + 14, right, y + 14)

        self.setFont(self._font_regular, 8)
        self.setFillColor(colors.HexColor("#475569"))
        self.drawString(left, y, "CONFIDENTIAL")

        center = f"LAST UPDATE: {self._last_update_label}"
        self.drawCentredString(_PAGE_WIDTH / 2, y, center)

        page_label = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(right, y, page_label)
        self.restoreState()


def _escape(text: str) -> str:
    return (
        (text or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def format_checklist_last_update(generated_at: datetime) -> str:
    """Uppercase month + year from checklist generation time, e.g. SEPTEMBER 2026."""
    return generated_at.strftime("%B %Y").upper()


def _try_logo_image(logo_path: str | None) -> Image | None:
    """Load a modest header logo; return None if missing or unloadable."""
    if not logo_path:
        return None
    path = Path(logo_path)
    if path.suffix.lower() not in _PDF_LOGO_EXTENSIONS or not path.is_file():
        return None
    try:
        reader = ImageReader(str(path))
        iw, ih = reader.getSize()
        if iw <= 0 or ih <= 0:
            return None
        scale = min(_LOGO_MAX_W / iw, _LOGO_MAX_H / ih)
        return Image(str(path), width=iw * scale, height=ih * scale)
    except Exception:
        return None


def _brand_header_flowables(
    *,
    business_name: str,
    logo_path: str | None,
    font_bold: str,
) -> list[Any]:
    """Logo (left) + business name beside it, above the checklist heading."""
    display_name = (business_name or "").strip()
    if not display_name:
        return []

    name_style = ParagraphStyle(
        "ChecklistBusinessName",
        fontName=font_bold,
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#0f172a"),
        alignment=TA_LEFT,
    )
    name_para = Paragraph(_escape(display_name), name_style)
    logo = _try_logo_image(logo_path)

    if logo is not None:
        usable_width = _PAGE_WIDTH - (2 * _MARGIN)
        logo_col = float(logo.drawWidth) + 8
        brand_table = Table(
            [[logo, name_para]],
            colWidths=[logo_col, max(usable_width - logo_col, 1)],
        )
        brand_table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (0, 0), 8),
                    ("RIGHTPADDING", (1, 0), (1, 0), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        return [brand_table, Spacer(1, 10)]

    return [name_para, Spacer(1, 10)]


def build_document_checklist_pdf(
    *,
    level_name: str,
    rows: Sequence[dict[str, Any]],
    generated_at: datetime | None = None,
    business_name: str | None = None,
    logo_path: str | None = None,
    country_name: str | None = None,
) -> bytes:
    """Build a portrait A4 Document Checklist PDF for one program level."""
    font_regular, font_bold = _ensure_fonts()
    when = generated_at or datetime.now()
    last_update = format_checklist_last_update(when)
    display_level = (level_name or "").strip() or "Program"
    display_country = (country_name or "").strip()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=_PAGE_SIZE,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=_MARGIN,
        bottomMargin=_MARGIN + _FOOTER_BAND,
        title=f"Document Checklist for {display_level} Studies",
        author=(business_name or "").strip() or None,
    )

    styles = getSampleStyleSheet()
    heading_style = ParagraphStyle(
        "ChecklistHeading",
        parent=styles["Heading1"],
        fontName=font_bold,
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=10,
        alignment=TA_LEFT,
    )
    body_style = ParagraphStyle(
        "ChecklistBody",
        parent=styles["Normal"],
        fontName=font_regular,
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#1e293b"),
        spaceAfter=8,
    )
    level_applied_style = ParagraphStyle(
        "ChecklistLevelApplied",
        parent=styles["Normal"],
        fontName=font_bold,
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=6 if display_country else 14,
    )
    country_style = ParagraphStyle(
        "ChecklistCountry",
        parent=styles["Normal"],
        fontName=font_bold,
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=14,
    )
    cell_style = ParagraphStyle(
        "ChecklistCell",
        parent=styles["Normal"],
        fontName=font_regular,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#1e293b"),
    )
    header_cell_style = ParagraphStyle(
        "ChecklistHeaderCell",
        parent=styles["Normal"],
        fontName=font_bold,
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#0f172a"),
    )

    story: list[Any] = []
    story.extend(
        _brand_header_flowables(
            business_name=business_name or "",
            logo_path=logo_path,
            font_bold=font_bold,
        )
    )
    story.extend(
        [
            Paragraph(
                _escape(f"Document Checklist for {display_level} Studies"),
                heading_style,
            ),
            Paragraph("Please provide the documents listed below.", body_style),
            Paragraph(
                _escape(
                    f"Level Applied: {display_level} {_EM_DASH} these documents are applicable "
                    "for the applied program level."
                ),
                level_applied_style,
            ),
        ]
    )
    if display_country:
        story.append(
            Paragraph(
                _escape(f"Country: {display_country}"),
                country_style,
            )
        )

    usable_width = _PAGE_WIDTH - (2 * _MARGIN)
    col_widths = [
        0.45 * inch,
        usable_width * 0.28,
        usable_width * 0.42,
        usable_width * 0.22,
    ]
    col_widths[1] = usable_width - col_widths[0] - col_widths[2] - col_widths[3]

    table_data: list[list[Any]] = [
        [
            Paragraph("#", header_cell_style),
            Paragraph("Document Title", header_cell_style),
            Paragraph("Document Description", header_cell_style),
            Paragraph("Document Format", header_cell_style),
        ]
    ]

    for index, row in enumerate(rows, start=1):
        title = str(row.get("document_name") or "").strip() or _EM_DASH
        description = str(row.get("description") or "").strip() or _EM_DASH
        raw_format = row.get("accepted_format")
        doc_format = (
            str(raw_format).strip()
            if raw_format is not None and str(raw_format).strip()
            else _EM_DASH
        )
        table_data.append(
            [
                Paragraph(str(index), cell_style),
                Paragraph(_escape(title), cell_style),
                Paragraph(_escape(description), cell_style),
                Paragraph(_escape(doc_format), cell_style),
            ]
        )

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 4 * mm))

    def _make_canvas(filename_or_buffer: Any, **kwargs: Any) -> _ChecklistFooterCanvas:
        return _ChecklistFooterCanvas(
            filename_or_buffer,
            last_update_label=last_update,
            **kwargs,
        )

    doc.build(story, canvasmaker=_make_canvas)
    return buffer.getvalue()
