from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.schemas.exception_log import ExceptionLogOut
from app.schemas.sync_log import SyncLogOut
from app.services.audit_context import format_audit_details_for_display
from app.services.business_profile_service import get_business_pdf_branding
from app.services.settings_service import get_setting
from app.utils.timezone import utc_now

_PAGE_SIZE = landscape(A4)
_PAGE_WIDTH, _PAGE_HEIGHT = _PAGE_SIZE
_MARGIN = 0.55 * inch
_LOGO_MAX_H = 0.38 * inch
_LOGO_MAX_W = 1.1 * inch
_HEADER_CONTENT_GAP = 0.12 * inch
_PDF_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif"}


def _estimate_footer_band(address_lines: list[str]) -> float:
    line_count = max(1, len(address_lines)) if address_lines else 1
    # top border padding + address lines + bottom padding
    return 0.18 * inch + (line_count * 10) + 0.12 * inch


def _estimate_header_band(has_logo: bool) -> float:
    # logo/name row + divider + gap under divider
    return (0.42 * inch if has_logo else 0.32 * inch) + _HEADER_CONTENT_GAP


class _BrandedReportCanvas(canvas.Canvas):
    """Two-pass canvas: header (logo + business name) and footer (address + Page X of Y)."""

    def __init__(self, *args: Any, branding: dict | None = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self._page_states: list[dict] = []
        self._branding = branding or {}
        self._business_name = (self._branding.get("business_name") or "NEXUS").strip() or "NEXUS"
        self._address_lines = [
            line.strip()
            for line in (self._branding.get("address_lines") or [])
            if (line or "").strip()
        ]
        self._logo_path = self._branding.get("logo_path")

    def showPage(self) -> None:
        self._page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total_pages = len(self._page_states)
        for state in self._page_states:
            self.__dict__.update(state)
            self._draw_header()
            self._draw_footer(total_pages)
            super().showPage()
        super().save()

    def _draw_header(self) -> None:
        self.saveState()
        left = _MARGIN
        right = _PAGE_WIDTH - _MARGIN
        top = _PAGE_HEIGHT - _MARGIN

        text_x = left
        name_baseline = top - 14

        if self._logo_path:
            drawn = self._draw_logo(left, top)
            if drawn:
                logo_w, _logo_h = drawn
                text_x = left + logo_w + 10
                name_baseline = top - (_LOGO_MAX_H / 2) - 4

        self.setFont("Helvetica-Bold", 12)
        self.setFillColor(colors.HexColor("#0f172a"))
        self.drawString(text_x, name_baseline, self._business_name)

        divider_y = top - (_LOGO_MAX_H if self._logo_path else 0.28 * inch) - 6
        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.6)
        self.line(left, divider_y, right, divider_y)
        self.restoreState()

    def _draw_logo(self, left: float, top: float) -> tuple[float, float] | None:
        path = Path(str(self._logo_path))
        if path.suffix.lower() not in _PDF_LOGO_EXTENSIONS or not path.is_file():
            return None
        try:
            reader = ImageReader(str(path))
            iw, ih = reader.getSize()
            if iw <= 0 or ih <= 0:
                return None
            scale = min(_LOGO_MAX_W / iw, _LOGO_MAX_H / ih)
            width = iw * scale
            height = ih * scale
            self.drawImage(
                reader,
                left,
                top - height,
                width=width,
                height=height,
                mask="auto",
                preserveAspectRatio=True,
            )
            return width, height
        except Exception:
            return None

    def _draw_footer(self, total_pages: int) -> None:
        self.saveState()
        left = _MARGIN
        right = _PAGE_WIDTH - _MARGIN
        footer_band = _estimate_footer_band(self._address_lines)
        footer_top = _MARGIN + footer_band

        self.setStrokeColor(colors.HexColor("#cbd5e1"))
        self.setLineWidth(0.5)
        self.line(left, footer_top, right, footer_top)

        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748b"))

        address_y = footer_top - 11
        max_width = _PAGE_WIDTH - (2 * _MARGIN) - 90
        for line in self._address_lines:
            text = line
            while self.stringWidth(text, "Helvetica", 8) > max_width and len(text) > 4:
                text = text[:-2]
            if text != line:
                text = text.rstrip() + "…"
            self.drawString(left, address_y, text)
            address_y -= 10

        page_label = f"Page {self._pageNumber} of {total_pages}"
        self.drawRightString(right, _MARGIN + 4, page_label)
        self.restoreState()


def _canvas_maker_for_branding(branding: dict):
    def _maker(*args: Any, **kwargs: Any):
        return _BrandedReportCanvas(*args, branding=branding, **kwargs)

    return _maker


def _build_report_doc(
    buffer: io.BytesIO,
    *,
    branding: dict,
    title: str,
) -> SimpleDocTemplate:
    has_logo = bool(branding.get("logo_path"))
    top_margin = _MARGIN + _estimate_header_band(has_logo)
    bottom_margin = _MARGIN + _estimate_footer_band(branding.get("address_lines") or [])
    return SimpleDocTemplate(
        buffer,
        pagesize=_PAGE_SIZE,
        leftMargin=_MARGIN,
        rightMargin=_MARGIN,
        topMargin=top_margin,
        bottomMargin=bottom_margin,
        title=title,
        author=branding.get("business_name") or "NEXUS",
        canvasmaker=_canvas_maker_for_branding(branding),
    )


def _format_range_label(start_date: datetime | None, end_date: datetime | None) -> str:
    if start_date and end_date:
        return f"{start_date.date().isoformat()} to {end_date.date().isoformat()}"
    if start_date:
        return f"From {start_date.date().isoformat()}"
    if end_date:
        return f"Through {end_date.date().isoformat()}"
    return "All available records"


def _business_timezone_name(db: Session) -> str:
    return (get_setting("BUSINESS_TIMEZONE", "UTC", db=db) or "UTC").strip() or "UTC"


def _format_timestamp(value: datetime | None, db: Session | None = None) -> str:
    if value is None:
        return "—"
    tz_name = _business_timezone_name(db) if db is not None else "UTC"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")
        tz_name = "UTC"
    aware = value.replace(tzinfo=ZoneInfo("UTC")) if value.tzinfo is None else value.astimezone(ZoneInfo("UTC"))
    return aware.astimezone(tz).strftime("%Y-%m-%d %H:%M:%S") + f" ({tz_name})"


def _format_audit_timestamp(value: datetime | None, db: Session | None = None) -> str:
    """Audit rows store wall-clock time in the business timezone (naive datetime)."""
    if value is None:
        return "—"
    tz_name = _business_timezone_name(db) if db is not None else "UTC"
    fraction = f"{value.microsecond:06d}"
    return value.strftime("%Y-%m-%d %H:%M:%S") + f".{fraction} ({tz_name})"


def _escape_pdf_text(value: str) -> str:
    return (value or "—").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _pdf_paragraph(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(_escape_pdf_text(text), style)


def _pdf_table_cell_style(base: ParagraphStyle) -> ParagraphStyle:
    return ParagraphStyle(
        "PdfTableCell",
        parent=base,
        fontName="Helvetica",
        fontSize=7,
        leading=9,
        wordWrap="CJK",
    )


def _pdf_table_header_style(base: ParagraphStyle) -> ParagraphStyle:
    return ParagraphStyle(
        "PdfTableHeader",
        parent=base,
        fontName="Helvetica-Bold",
        fontSize=7,
        leading=9,
        textColor=colors.white,
    )


def _report_title_styles():
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=4,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10,
        textColor=colors.HexColor("#475569"),
        leading=14,
        spaceAfter=6,
    )
    meta_style = ParagraphStyle(
        "ReportMeta",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=colors.HexColor("#64748b"),
        leading=12,
    )
    return styles, title_style, subtitle_style, meta_style


def _format_sync_mode(mode: str) -> str:
    normalized = (mode or "").strip().upper()
    if normalized == "AUTOMATED":
        return "Scheduled"
    if normalized == "MANUAL":
        return "Manual"
    return mode or "—"


def _format_source(source: str) -> str:
    normalized = (source or "").strip().lower()
    mapping = {
        "scheduled": "Scheduler",
        "manual_api": "Settings",
        "webhook": "Webhook",
        "backfill": "Backfill",
    }
    return mapping.get(normalized, source or "—")


def _truncate(text: str | None, *, max_len: int = 120) -> str:
    value = (text or "—").strip() or "—"
    if len(value) <= max_len:
        return value
    return value[: max_len - 1] + "…"


def _build_table_rows(logs: list[SyncLogOut], db: Session) -> list[list[str]]:
    rows: list[list[str]] = []
    for log in logs:
        rows.append(
            [
                _format_timestamp(log.attempt_timestamp, db),
                _format_sync_mode(log.sync_mode),
                _format_source(log.source),
                _truncate(log.triggered_by_user, max_len=28),
                (log.status or "—").upper(),
                str(log.leads_created),
                str(log.leads_seen),
                _truncate(log.message, max_len=90),
            ]
        )
    return rows


def generate_sync_logs_pdf(
    db: Session,
    *,
    logs: list[SyncLogOut],
    start_date: datetime | None,
    end_date: datetime | None,
    sort_by: str,
    sort_order: Literal["asc", "desc"],
    generated_at: datetime | None = None,
) -> bytes:
    """Build a professional PDF export for the full filtered sync-log dataset."""
    branding = get_business_pdf_branding(db)
    generated = generated_at or utc_now()
    range_label = _format_range_label(start_date, end_date)
    sort_label = f"{sort_by.replace('_', ' ')} ({sort_order.upper()})"

    buffer = io.BytesIO()
    doc = _build_report_doc(buffer, branding=branding, title="Meta Lead Sync Logs")
    _styles, title_style, subtitle_style, meta_style = _report_title_styles()

    story = [
        Paragraph("Meta Lead Sync Logs — Full Report", title_style),
        Paragraph(f"Report period: {range_label}", subtitle_style),
        Paragraph(
            f"Generated {_format_timestamp(generated, db)} · "
            f"{len(logs):,} record{'s' if len(logs) != 1 else ''} · "
            f"Sorted by {sort_label}",
            meta_style,
        ),
        Spacer(1, 0.18 * inch),
    ]

    headers = [
        "Attempted",
        "Mode",
        "Source",
        "Triggered By",
        "Status",
        "New Leads",
        "Seen",
        "Message",
    ]
    table_data = [headers] + _build_table_rows(logs, db)

    col_widths = [
        1.05 * inch,
        0.72 * inch,
        0.72 * inch,
        1.05 * inch,
        0.68 * inch,
        0.58 * inch,
        0.48 * inch,
        3.35 * inch,
    ]

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#18181b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("FONTSIZE", (0, 1), (-1, -1), 7),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("ALIGN", (0, 0), (-1, 0), "LEFT"),
                ("ALIGN", (5, 1), (6, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)

    doc.build(story)
    return buffer.getvalue()


def _format_exception_source(source: str | None) -> str:
    mapping = {
        "meta_lead_sync": "Meta Sync",
        "api_client": "Browser",
        "backend": "Backend",
        "scheduler": "Scheduler",
        "webhook": "Webhook",
        "proxy_timeout": "Proxy/Timeout",
    }
    key = (source or "").strip().lower()
    return mapping.get(key, source or "—")


def _build_exception_table_rows(logs: list[ExceptionLogOut], db: Session) -> list[list[str]]:
    rows: list[list[str]] = []
    for log in logs:
        message = log.message or "—"
        if log.resolution_comment:
            message = f"{message}\nResolution: {log.resolution_comment}"
        rows.append(
            [
                _format_timestamp(log.attempt_timestamp, db),
                (log.severity or "—").upper(),
                _format_exception_source(log.source),
                _truncate(log.triggered_by_user, max_len=28),
                (log.status or "—").upper(),
                _truncate(log.category, max_len=24),
                _truncate(log.related_id, max_len=16),
                _truncate(message, max_len=90),
            ]
        )
    return rows


def generate_exception_logs_pdf(
    db: Session,
    *,
    logs: list[ExceptionLogOut],
    start_date: datetime | None,
    end_date: datetime | None,
    sort_by: str,
    sort_order: Literal["asc", "desc"],
    generated_at: datetime | None = None,
) -> bytes:
    """Build a professional PDF export for the Exception Report dataset."""
    branding = get_business_pdf_branding(db)
    generated = generated_at or utc_now()
    range_label = _format_range_label(start_date, end_date)
    sort_label = f"{sort_by.replace('_', ' ')} ({sort_order.upper()})"

    buffer = io.BytesIO()
    doc = _build_report_doc(buffer, branding=branding, title="Exception Report")
    _styles, title_style, subtitle_style, meta_style = _report_title_styles()

    story = [
        Paragraph("Exception Report — Full Export", title_style),
        Paragraph(f"Report period: {range_label}", subtitle_style),
        Paragraph(
            f"Generated {_format_timestamp(generated, db)} · "
            f"{len(logs):,} record{'s' if len(logs) != 1 else ''} · "
            f"Sorted by {sort_label}",
            meta_style,
        ),
        Spacer(1, 0.18 * inch),
    ]

    headers = [
        "Occurred",
        "Severity",
        "Source",
        "Triggered By",
        "Status",
        "Category",
        "Related",
        "Message",
    ]
    table_data = [headers] + _build_exception_table_rows(logs, db)

    col_widths = [
        1.05 * inch,
        0.72 * inch,
        0.72 * inch,
        1.05 * inch,
        0.68 * inch,
        0.78 * inch,
        0.58 * inch,
        3.05 * inch,
    ]

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#18181b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 8),
                ("FONTSIZE", (0, 1), (-1, -1), 7),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("ALIGN", (0, 0), (-1, 0), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(table)

    doc.build(story)
    return buffer.getvalue()


def _format_details_cell(details: dict | None) -> str:
    return format_audit_details_for_display(details)


def _build_audit_table_rows(logs: list, db: Session) -> list[list[str]]:
    rows: list[list[str]] = []
    for log in logs:
        rows.append(
            [
                _format_audit_timestamp(log.timestamp, db),
                log.user_email or "—",
                log.action_type or "—",
                log.target_resource or "—",
                log.resource_id or "—",
                (log.sync_mode or "—").upper(),
                (log.status or "—").upper(),
                log.ip_address or "—",
                _format_details_cell(log.details),
            ]
        )
    return rows


def generate_audit_logs_pdf(
    db: Session,
    *,
    logs: list,
    start_date: datetime | None,
    end_date: datetime | None,
    sort_by: str,
    sort_order: Literal["asc", "desc"],
    generated_at: datetime | None = None,
) -> bytes:
    branding = get_business_pdf_branding(db)
    generated = generated_at or utc_now()
    range_label = _format_range_label(start_date, end_date)
    sort_label = f"{sort_by.replace('_', ' ')} ({sort_order.upper()})"

    buffer = io.BytesIO()
    doc = _build_report_doc(buffer, branding=branding, title="Audit Logs")
    styles, title_style, subtitle_style, meta_style = _report_title_styles()

    story = [
        Paragraph("NEXUS Audit Log Report", title_style),
        Paragraph(f"Report period: {range_label}", subtitle_style),
        Paragraph(
            f"Generated {_format_timestamp(generated, db)} · "
            f"{len(logs):,} record{'s' if len(logs) != 1 else ''} · "
            f"Sorted by {sort_label}",
            meta_style,
        ),
        Spacer(1, 0.18 * inch),
    ]

    headers = [
        "Timestamp",
        "User",
        "Action",
        "Resource",
        "Resource ID",
        "Mode",
        "Status",
        "IP",
        "Details",
    ]
    cell_style = _pdf_table_cell_style(styles["Normal"])
    header_style = _pdf_table_header_style(styles["Normal"])
    raw_rows = _build_audit_table_rows(logs, db)
    table_data: list[list[Paragraph]] = [[_pdf_paragraph(header, header_style) for header in headers]]
    for row in raw_rows:
        table_data.append([_pdf_paragraph(cell, cell_style) for cell in row])
    col_widths = [
        1.45 * inch,
        1.05 * inch,
        0.85 * inch,
        0.85 * inch,
        0.75 * inch,
        0.6 * inch,
        0.6 * inch,
        0.8 * inch,
        2.0 * inch,
    ]

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#18181b")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e2e8f0")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("WORDWRAP", (0, 0), (-1, -1), True),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    story.append(table)

    doc.build(story)
    return buffer.getvalue()
